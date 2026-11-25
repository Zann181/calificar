"""Europe PMC: metadatos, resumen y enlaces de texto completo abierto. API pública, con lógica booleana y por campos."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes._comun import (
    IDIOMA_ISO,
    IDIOMA_LARGO,
    entero_o_none,
    quitar_etiquetas,
)
from app.contextos.descubrimiento.dominio.busqueda import ConsultaDeBusqueda
from app.contextos.descubrimiento.dominio.candidato import Autor, RegistroBibliografico

URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def consulta_europepmc(consulta: ConsultaDeBusqueda, hoy: date) -> str:
    def termino(t: str) -> str:
        t = t.replace('"', " ").strip()
        return f'TITLE_ABS:"{t}"' if " " in t or "-" in t else f"TITLE_ABS:{t}"
    bloques = ["(" + " OR ".join(termino(t) for t in c.terminos) + ")" for c in consulta.obligatorios]
    f = consulta.filtros
    idiomas = " OR ".join(f"LANG:{IDIOMA_LARGO[i]}" for i in f.idiomas if i in IDIOMA_LARGO)
    partes = [*bloques, f"PUB_YEAR:[{f.desde} TO {f.hasta_efectivo(hoy)}]"]
    if idiomas:
        partes.append(f"({idiomas})")
    return " AND ".join(partes)


class EuropePMC:
    nombre = "europepmc"
    etiqueta = "Europe PMC"
    sitio_id: str | None = None

    def __init__(self, cliente: ClienteCortes) -> None:
        self._cliente = cliente

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]:
        cursor = "*"
        entregados = 0
        q = consulta_europepmc(consulta, hoy)
        while cursor and entregados < limite:
            datos = self._cliente.get_json(self.nombre, URL, {
                "query": q, "format": "json", "resultType": "core", "pageSize": min(100, limite - entregados),
                "cursorMark": cursor})
            resultados = (datos.get("resultList") or {}).get("result", [])
            for r in resultados:
                entregados += 1
                yield self._registro(r, entregados)
            siguiente = datos.get("nextCursorMark")
            cursor = siguiente if resultados and siguiente and siguiente != cursor else ""

    def _registro(self, r: dict[str, Any], posicion: int) -> RegistroBibliografico:
        autores = [Autor(nombre=str(a.get("fullName") or ""), apellido=str(a.get("lastName") or ""))
                   for a in (r.get("authorList") or {}).get("author", []) if a.get("fullName")]
        tipos = (r.get("pubTypeList") or {}).get("pubType", [])
        preprint = r.get("source") == "PPR"
        enlaces = (r.get("fullTextUrlList") or {}).get("fullTextUrl", [])
        gratis = [e for e in enlaces if e.get("availabilityCode") in ("OA", "F") and e.get("url")]
        pdf = next((e["url"] for e in gratis if e.get("documentStyle") == "pdf"), None)
        titulo = quitar_etiquetas(r.get("title")).rstrip(".")  # llegan con «&lt;i&gt;…» de la fuente
        return RegistroBibliografico(
            fuente=self.nombre, id_externo=f"{r.get('source')}:{r.get('id')}", posicion=posicion, titulo=titulo,
            doi=r.get("doi"), autores=tuple(autores), anio=entero_o_none(r.get("pubYear")),
            revista=str((((r.get("journalInfo") or {}).get("journal")) or {}).get("title") or ""),
            resumen=quitar_etiquetas(r.get("abstractText")),
            palabras_clave=tuple(str(k) for k in (r.get("keywordList") or {}).get("keyword", [])),
            idioma=IDIOMA_ISO.get(str(r.get("language") or ""), str(r.get("language") or "")),
            tipo="preprint" if preprint else ("review" if any("Review" in str(t) for t in tipos) else "article"),
            url_oa=pdf or (gratis[0]["url"] if gratis else None), es_preprint=preprint)

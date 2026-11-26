"""Crossref: metadatos y DOI. Su búsqueda es por relevancia, sin lógica booleana, y casi nunca trae resumen.

Por eso se hacen unas pocas consultas de texto libre (pares de términos de los dos primeros conceptos) y **cada resultado se
vuelve a evaluar en local** con la cadena completa (`ConsultaDeBusqueda.coincide`) sobre título y resumen. Como los títulos
rara vez nombran el contexto laboral, la evaluación local exige solo los dos primeros conceptos (felicidad y desempeño).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from itertools import product
from typing import Any

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes._comun import quitar_etiquetas
from app.contextos.descubrimiento.dominio.busqueda import ConsultaDeBusqueda
from app.contextos.descubrimiento.dominio.candidato import Autor, RegistroBibliografico

URL = "https://api.crossref.org/works"
CAMPOS = "DOI,title,author,issued,abstract,container-title,URL,subject,type,link,license"
MAX_PARES = 6
TERMINOS_POR_CONCEPTO = 3


def pares_de_consulta(consulta: ConsultaDeBusqueda) -> list[str]:
    conceptos = consulta.obligatorios[:2]
    if len(conceptos) < 2:
        return [" ".join(t.rstrip("*") for t in conceptos[0].terminos[:MAX_PARES])]
    a, b = (c.terminos[:TERMINOS_POR_CONCEPTO] for c in conceptos)
    return [f"{x.rstrip('*')} {y.rstrip('*')}" for x, y in product(a, b)][:MAX_PARES]


def _vigente(licencia: dict[str, Any], hoy: date) -> bool:
    partes = ((licencia.get("start") or {}).get("date-parts") or [[]])[0]
    if not partes or partes[0] is None:
        return True
    anio, mes, dia = (*partes, 1, 1)[:3]
    return date(int(anio), int(mes), int(dia)) <= hoy


def pdfs_abiertos(it: dict[str, Any], hoy: date) -> tuple[str, ...]:
    """Crossref enlaza PDF que a menudo son de pago: solo valen si el trabajo tiene ya una licencia Creative Commons."""
    libre = any("creativecommons.org" in str(x.get("URL") or "") and _vigente(x, hoy) for x in it.get("license") or [])
    if not libre:
        return ()
    return tuple(dict.fromkeys(str(x["URL"]) for x in it.get("link") or []
                               if x.get("content-type") == "application/pdf" and x.get("URL")))


class Crossref:
    nombre = "crossref"
    etiqueta = "Crossref"
    sitio_id: str | None = None

    def __init__(self, cliente: ClienteCortes, *, contacto: str = "") -> None:
        self._cliente, self._contacto = cliente, contacto.strip()

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]:
        f = consulta.filtros
        tipos = ["type:journal-article"] + (["type:posted-content"] if f.incluir_preprints else [])
        filtro = ",".join([f"from-pub-date:{f.desde}-01-01", f"until-pub-date:{f.hasta_efectivo(hoy)}-12-31",
                           "has-license:true", "has-full-text:true", *tipos])
        locales = ConsultaDeBusqueda(conceptos=consulta.obligatorios[:2], filtros=f)
        por_consulta = max(10, min(100, limite // max(1, len(pares_de_consulta(consulta))) + 10))
        vistos: set[str] = set()
        entregados = 0
        for q in pares_de_consulta(consulta):
            datos = self._cliente.get_json(self.nombre, URL, {
                "query": q, "filter": filtro, "rows": por_consulta, "select": CAMPOS,
                "mailto": self._contacto or None})
            for it in (datos.get("message") or {}).get("items", []):
                doi = str(it.get("DOI") or "").lower()
                titulo = quitar_etiquetas((it.get("title") or [""])[0])
                resumen = quitar_etiquetas(it.get("abstract"))
                if not doi or doi in vistos or not titulo or not locales.coincide(f"{titulo} {resumen}"):
                    continue
                vistos.add(doi)
                entregados += 1
                yield self._registro(it, titulo, resumen, entregados, pdfs_abiertos(it, hoy))
                if entregados >= limite:
                    return

    def _registro(self, it: dict[str, Any], titulo: str, resumen: str, posicion: int,
                  pdfs: tuple[str, ...]) -> RegistroBibliografico:
        autores = tuple(Autor(nombre=f"{a.get('given', '')} {a.get('family', '')}".strip(), apellido=str(a.get("family") or ""))
                        for a in it.get("author", []) if a.get("family") or a.get("given"))
        partes = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        tipo = str(it.get("type") or "")
        return RegistroBibliografico(
            fuente=self.nombre, id_externo=str(it.get("DOI")), posicion=posicion, titulo=titulo, doi=it.get("DOI"),
            autores=autores, anio=partes[0] if partes else None, revista=((it.get("container-title") or [""])[0] or ""),
            resumen=resumen, palabras_clave=tuple(str(s) for s in it.get("subject", [])),
            tipo="preprint" if tipo == "posted-content" else "article", es_preprint=tipo == "posted-content", pdfs=pdfs)

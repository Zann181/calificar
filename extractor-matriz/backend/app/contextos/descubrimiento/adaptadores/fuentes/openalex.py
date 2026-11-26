"""OpenAlex: metadatos, resumen (índice invertido), país de cada autor y copia abierta. API pública.

Sin llave comparte un presupuesto diario con todos los que salen por la misma IP; con `OPENALEX_API_KEY` (gratuita, la crea
la persona en openalex.org) tiene el suyo. El agotamiento llega como HTTP 429 y queda registrado como ERROR.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes._comun import apellido_de, quitar_etiquetas
from app.contextos.descubrimiento.dominio.busqueda import ConsultaDeBusqueda
from app.contextos.descubrimiento.dominio.candidato import Autor, RegistroBibliografico

URL = "https://api.openalex.org/works"
CAMPOS = ("id,doi,title,publication_year,language,type,authorships,abstract_inverted_index,primary_location,"
          "open_access,keywords,best_oa_location,locations")


def resumen_de(indice: dict[str, list[int]] | None) -> str:
    """OpenAlex guarda el resumen como {palabra: [posiciones]}; se reconstruye en orden."""
    if not indice:
        return ""
    palabras: dict[int, str] = {}
    for palabra, posiciones in indice.items():
        for p in posiciones:
            palabras[p] = palabra
    return " ".join(palabras[i] for i in sorted(palabras))


def pdfs_abiertos(r: dict[str, Any]) -> tuple[str, ...]:
    """Los PDF de ubicaciones de acceso abierto: primero la que OpenAlex considera mejor."""
    lugares = [r.get("best_oa_location") or {}, *(r.get("locations") or [])]
    return tuple(dict.fromkeys(str(x["pdf_url"]) for x in lugares if x.get("is_oa") and x.get("pdf_url")))


class OpenAlex:
    nombre = "openalex"
    etiqueta = "OpenAlex"
    sitio_id: str | None = None

    def __init__(self, cliente: ClienteCortes, *, api_key: str = "", contacto: str = "") -> None:
        self._cliente, self._api_key, self._contacto = cliente, api_key.strip(), contacto.strip()

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]:
        f = consulta.filtros
        tipos = ["article", "review"] + (["preprint"] if f.incluir_preprints else [])
        filtro = ",".join([
            f"from_publication_date:{f.desde}-01-01", f"to_publication_date:{f.hasta_efectivo(hoy)}-12-31",
            "type:" + "|".join(tipos), "language:" + "|".join(f.idiomas), "open_access.is_oa:true",
            "title_and_abstract.search:" + consulta.booleana(comodines=False)])
        cursor: str | None = "*"
        entregados = 0
        while cursor and entregados < limite:
            params: dict[str, Any] = {"filter": filtro, "per-page": min(100, limite - entregados), "cursor": cursor,
                                      "select": CAMPOS, "api_key": self._api_key or None, "mailto": self._contacto or None}
            datos = self._cliente.get_json(self.nombre, URL, params)
            resultados = datos.get("results", [])
            for r in resultados:
                entregados += 1
                yield self._registro(r, entregados)
            cursor = (datos.get("meta") or {}).get("next_cursor") if resultados else None

    def _registro(self, r: dict[str, Any], posicion: int) -> RegistroBibliografico:
        autores = []
        for a in r.get("authorships") or []:
            nombre = (a.get("author") or {}).get("display_name") or ""
            if nombre:
                paises = tuple(dict.fromkeys(str(p) for p in (a.get("countries") or [])))
                autores.append(Autor(nombre=nombre, apellido=apellido_de(nombre), paises=paises))
        fuente = ((r.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        tipo = str(r.get("type") or "article")
        return RegistroBibliografico(
            fuente=self.nombre, id_externo=str(r.get("id") or ""), posicion=posicion, titulo=quitar_etiquetas(r.get("title")),
            doi=r.get("doi"), autores=tuple(autores), anio=r.get("publication_year"), revista=fuente,
            resumen=resumen_de(r.get("abstract_inverted_index")),
            palabras_clave=tuple(str(k.get("display_name")) for k in (r.get("keywords") or []) if k.get("display_name")),
            idioma=str(r.get("language") or ""), tipo=tipo, url_oa=(r.get("open_access") or {}).get("oa_url"),
            es_preprint=tipo == "preprint", pdfs=pdfs_abiertos(r))

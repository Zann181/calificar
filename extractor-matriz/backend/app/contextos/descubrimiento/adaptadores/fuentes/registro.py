"""Las fuentes que se ofrecen en la pestaña. Añadir una: escribir su adaptador y sumarla aquí."""

from __future__ import annotations

from app.config import Settings
from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes.crossref import Crossref
from app.contextos.descubrimiento.adaptadores.fuentes.europepmc import EuropePMC
from app.contextos.descubrimiento.adaptadores.fuentes.openalex import OpenAlex
from app.contextos.descubrimiento.adaptadores.fuentes.redalyc import Redalyc
from app.contextos.descubrimiento.puertos import FuenteDeLiteratura


def construir_fuentes(cliente: ClienteCortes, ajustes: Settings) -> dict[str, FuenteDeLiteratura]:
    fuentes: list[FuenteDeLiteratura] = [
        OpenAlex(cliente, api_key=ajustes.openalex_api_key, contacto=ajustes.contacto_api),
        EuropePMC(cliente),
        Crossref(cliente, contacto=ajustes.contacto_api),
        Redalyc(cliente),
    ]
    return {f.nombre: f for f in fuentes}

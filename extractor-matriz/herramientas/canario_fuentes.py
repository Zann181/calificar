"""Canario de las fuentes de la pestaña «Buscar»: ¿siguen respondiendo con la forma que los adaptadores entienden?

Se corre a mano (no en el CI: sale a internet) cuando una fuente empieza a fallar o de vez en cuando:

    .venv/Scripts/python.exe ../herramientas/canario_fuentes.py [--fuente redalyc]

Hace UNA búsqueda mínima por fuente (3 resultados) con los adaptadores reales y el cliente cortés, sin correo de contacto y sin
llaves. Para cada una dice «bien» (devolvió registros con título y año) o «falla» (con la causa). Sale con código 1 si alguna
falla. Una fuente que dé «cambió» (error de estructura) es la que el programa desactivaría sola tras tres fallos seguidos.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.config import Settings  # noqa: E402
from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes  # noqa: E402
from app.contextos.descubrimiento.adaptadores.fuentes.registro import construir_fuentes  # noqa: E402
from app.contextos.descubrimiento.dominio.busqueda import Concepto, ConsultaDeBusqueda, Filtros  # noqa: E402
from app.contextos.descubrimiento.dominio.errores import ErrorDeEstructura, ErrorDeFuente  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", help="solo esta fuente (p. ej. redalyc)")
    args = ap.parse_args()
    ajustes = Settings(_env_file=None, contacto_api="", openalex_api_key="")
    fuentes = construir_fuentes(ClienteCortes(pausa_min_s=1.0), ajustes)
    consulta = ConsultaDeBusqueda(
        conceptos=(Concepto("Felicidad", ("happiness", "felicidad", "bienestar subjetivo")),
                   Concepto("Desempeño", ("job performance", "desempeño laboral"))),
        filtros=Filtros(desde=2015))
    mal = 0
    print(f"{'Fuente':14} {'estado':8} detalle")
    for nombre, fuente in fuentes.items():
        if args.fuente and nombre != args.fuente:
            continue
        try:
            registros = list(fuente.buscar(consulta, 3, date.today()))
            utiles = [r for r in registros if r.titulo and r.anio]
            if utiles:
                print(f"{nombre:14} {'bien':8} {len(registros)} resultados; ej.: {utiles[0].titulo[:60]} ({utiles[0].anio})")
            else:
                mal += 1
                print(f"{nombre:14} {'falla':8} respondió, pero sin resultados con título y año (¿cambió el formato?)")
        except ErrorDeEstructura as e:
            mal += 1
            print(f"{nombre:14} {'cambió':8} {e.causa}")
        except ErrorDeFuente as e:
            mal += 1
            print(f"{nombre:14} {'falla':8} {e.causa}")
    return 1 if mal else 0


if __name__ == "__main__":
    raise SystemExit(main())

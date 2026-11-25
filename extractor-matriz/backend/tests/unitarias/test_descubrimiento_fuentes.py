"""Descubrimiento · adaptadores de fuentes, contra respuestas reales grabadas (sin tocar la red)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes.crossref import Crossref, pares_de_consulta
from app.contextos.descubrimiento.adaptadores.fuentes.europepmc import EuropePMC, consulta_europepmc
from app.contextos.descubrimiento.adaptadores.fuentes.openalex import OpenAlex, resumen_de
from app.contextos.descubrimiento.dominio.busqueda import consulta_inicial

GRABADAS = Path(__file__).resolve().parents[1] / "fixtures" / "descubrimiento"
HOY = date(2026, 11, 25)


def servir(nombre: str, visto: list[httpx.Request]) -> ClienteCortes:
    datos = json.loads((GRABADAS / nombre).read_text(encoding="utf-8"))

    def manejador(r: httpx.Request) -> httpx.Response:
        visto.append(r)
        # una sola página: el cursor/nextCursorMark de lo grabado se ignora devolviendo la segunda vez una lista vacía
        if len(visto) > 1:
            return httpx.Response(200, json={"meta": {}, "results": [], "resultList": {"result": []},
                                             "message": {"items": []}})
        return httpx.Response(200, json=datos)

    return ClienteCortes(transporte=httpx.MockTransport(manejador), pausa_min_s=0, dormir=lambda s: None)


def test_openalex_arma_el_filtro_y_lee_lo_grabado() -> None:
    visto: list[httpx.Request] = []
    fuente = OpenAlex(servir("openalex.json", visto), api_key="LLAVE", contacto="")
    registros = list(fuente.buscar(consulta_inicial(), 50, HOY))
    filtro = visto[0].url.params["filter"]
    assert "from_publication_date:2020-01-01" in filtro and "to_publication_date:2026-12-31" in filtro
    assert "language:en|es|pt" in filtro and "type:article|review|preprint" in filtro
    assert "title_and_abstract.search:" in filtro and "*" not in filtro  # sin comodines: OpenAlex los rechaza ahí
    assert visto[0].url.params["api_key"] == "LLAVE" and "mailto" not in visto[0].url.params
    assert len(registros) == 3
    primero = registros[0]
    assert primero.fuente == "openalex" and primero.doi and primero.doi.startswith("https://doi.org/")
    assert primero.anio and primero.anio >= 2020 and primero.autores and primero.revista
    assert any(r.resumen for r in registros)  # el índice invertido se reconstruye como texto
    assert any(a.paises for r in registros for a in r.autores)  # país por afiliación (ADR 0010)


def test_resumen_de_indice_invertido() -> None:
    assert resumen_de({"hola": [0, 2], "mundo": [1]}) == "hola mundo hola"
    assert resumen_de(None) == ""


def test_openalex_manda_el_correo_solo_si_se_configuro() -> None:
    visto: list[httpx.Request] = []
    list(OpenAlex(servir("openalex.json", visto), contacto="persona@ejemplo.test").buscar(consulta_inicial(), 5, HOY))
    assert visto[0].url.params["mailto"] == "persona@ejemplo.test"


def test_europepmc_consulta_con_campos_anios_e_idiomas() -> None:
    q = consulta_europepmc(consulta_inicial(), HOY)
    assert 'TITLE_ABS:"subjective well-being"' in q and "TITLE_ABS:employee*" in q
    assert "PUB_YEAR:[2020 TO 2026]" in q and "LANG:eng" in q and "LANG:spa" in q and "LANG:por" in q


def test_europepmc_lee_lo_grabado() -> None:
    visto: list[httpx.Request] = []
    registros = list(EuropePMC(servir("europepmc.json", visto)).buscar(consulta_inicial(), 50, HOY))
    assert len(registros) == 2 and registros[0].fuente == "europepmc"
    r = registros[0]
    assert r.doi and r.anio and r.titulo and not r.titulo.endswith(".")
    assert r.idioma == "en" and r.resumen and "p < .001" in r.resumen  # la estadística no se confunde con una etiqueta
    assert r.autores and r.palabras_clave


def test_crossref_hace_pocas_consultas_y_filtra_en_local() -> None:
    assert 1 <= len(pares_de_consulta(consulta_inicial())) <= 6
    visto: list[httpx.Request] = []
    registros = list(Crossref(servir("crossref.json", visto)).buscar(consulta_inicial(), 50, HOY))
    assert visto and "type:journal-article" in visto[0].url.params["filter"]
    assert "from-pub-date:2020-01-01" in visto[0].url.params["filter"]
    # Lo grabado trae un trabajo sobre «job happiness» y desempeño: solo pasa lo que cumple los dos primeros conceptos.
    assert registros and all(r.doi for r in registros)
    assert len({r.doi for r in registros}) == len(registros)

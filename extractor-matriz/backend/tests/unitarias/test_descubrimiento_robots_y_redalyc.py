"""Descubrimiento · Fase 4: robots.txt, Redalyc (servicio JSON sin documentar) y salud de las fuentes frágiles."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes.redalyc import Redalyc, consultas_de
from app.contextos.descubrimiento.adaptadores.robots import PERMITE_TODO, PROHIBE_TODO, ReglasDeRobots
from app.contextos.descubrimiento.adaptadores.salud_fuentes import SaludDeFuentes
from app.contextos.descubrimiento.dominio.busqueda import Concepto, ConsultaDeBusqueda, consulta_inicial
from app.contextos.descubrimiento.dominio.errores import ErrorDeEstructura, ErrorDeFuente

GRABADAS = Path(__file__).resolve().parents[1] / "fixtures" / "descubrimiento"
HOY = date(2026, 11, 25)


def robots(nombre: str) -> ReglasDeRobots:
    return ReglasDeRobots((GRABADAS / nombre).read_text(encoding="utf-8"))


# ---- el lector de robots.txt ---------------------------------------------------------------------------------------------
def test_dialnet_prohibe_buscar_pero_no_sus_fichas() -> None:
    r = robots("robots_dialnet.txt")  # lo que publica Dialnet hoy
    assert not r.permite("https://dialnet.unirioja.es/buscar/documentos?querysDismax.DOCUMENTAL_TODO=felicidad")
    assert not r.permite("https://dialnet.unirioja.es/servlet/login")
    assert r.permite("https://dialnet.unirioja.es/servlet/articulo?codigo=123")


def test_scielo_search_prohibe_todo_a_los_agentes_genericos() -> None:
    r = robots("robots_scielo_search.txt")
    assert not r.permite("https://search.scielo.org/?q=felicidad&lang=es")
    assert not r.permite("https://search.scielo.org/")


def test_redalyc_permite_su_servicio_y_prohibe_sus_indices() -> None:
    r = robots("robots_redalyc.txt")
    assert r.permite("https://www.redalyc.org/service/r2020/getArticles/felicidad/1/25/1/default/")
    assert not r.permite("https://www.redalyc.org/redalyc/lib/algo")
    assert not r.permite("https://www.redalyc.org/indicador/x")


def test_reglas_comodin_final_mas_larga_y_agente_propio() -> None:
    r = ReglasDeRobots("User-agent: *\nDisallow: /a/*/privado\nDisallow: /fin$\nAllow: /a/publico/privado\n"
                       "Disallow: /a/publico\n")
    assert not r.permite("https://x.test/a/1/privado") and r.permite("https://x.test/a/1/otro")
    assert not r.permite("https://x.test/fin") and r.permite("https://x.test/fin/mas")
    assert r.permite("https://x.test/a/publico/privado")  # la regla más larga gana (Allow)
    propio = ReglasDeRobots("User-agent: *\nDisallow: /\n\nUser-agent: ExtractorMatriz\nDisallow: /solo-esto\n")
    assert propio.permite("https://x.test/cualquier") and not propio.permite("https://x.test/solo-esto/x")
    assert PERMITE_TODO.permite("https://x.test/") and not PROHIBE_TODO.permite("https://x.test/")
    assert ReglasDeRobots("User-agent: *\nDisallow:\n").permite("https://x.test/x")  # «Disallow:» vacío no prohíbe


# ---- el cliente respeta robots.txt ------------------------------------------------------------------------------------------
def cliente(rutas: dict[str, httpx.Response], visto: list[str] | None = None) -> ClienteCortes:
    def manejador(r: httpx.Request) -> httpx.Response:
        if visto is not None:
            visto.append(str(r.url))
        return rutas.get(str(r.url).split("?")[0], httpx.Response(404))

    return ClienteCortes(transporte=httpx.MockTransport(manejador), pausa_min_s=0, dormir=lambda s: None)


def texto(contenido: str) -> httpx.Response:
    return httpx.Response(200, text=contenido, headers={"content-type": "text/plain"})


def test_lo_que_robots_prohibe_no_se_lee_y_no_se_pide(caplog: pytest.LogCaptureFixture) -> None:
    visto: list[str] = []
    c = cliente({"https://sitio.test/robots.txt": texto("User-agent: *\nDisallow: /buscar/*\n"),
                 "https://sitio.test/buscar/x": httpx.Response(200, json={"a": 1})}, visto)
    with caplog.at_level(logging.INFO, logger="descubrimiento"), pytest.raises(ErrorDeFuente, match="robots.txt"):
        c.get_json("sitio", "https://sitio.test/buscar/x", robots=True)
    assert visto == ["https://sitio.test/robots.txt"]  # nunca llegó a pedir la página prohibida
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_lo_permitido_se_lee_y_robots_se_pide_una_sola_vez() -> None:
    visto: list[str] = []
    c = cliente({"https://sitio.test/robots.txt": texto("User-agent: *\nDisallow: /privado\n"),
                 "https://sitio.test/datos": httpx.Response(200, json={"ok": True})}, visto)
    assert c.get_json("sitio", "https://sitio.test/datos", {"q": "1"}, robots=True) == {"ok": True}
    assert c.get_json("sitio", "https://sitio.test/datos", {"q": "2"}, robots=True) == {"ok": True}
    assert visto.count("https://sitio.test/robots.txt") == 1


def test_sin_robots_404_no_hay_restricciones_pero_si_falla_el_servidor_se_detiene() -> None:
    sin = cliente({"https://a.test/datos": httpx.Response(200, json={"ok": 1})})
    assert sin.get_json("a", "https://a.test/datos", robots=True) == {"ok": 1}
    roto = cliente({"https://b.test/robots.txt": httpx.Response(503), "https://b.test/datos": httpx.Response(200, json={})})
    with pytest.raises(ErrorDeFuente, match="robots.txt"):
        roto.get_json("b", "https://b.test/datos", robots=True)


def test_sin_pedir_robots_el_comportamiento_de_siempre() -> None:
    visto: list[str] = []
    c = cliente({"https://api.test/x": httpx.Response(200, json={"v": 1})}, visto)
    assert c.get_json("api", "https://api.test/x") == {"v": 1} and visto == ["https://api.test/x"]


# ---- Redalyc ------------------------------------------------------------------------------------------------------------------
def servir_redalyc(datos: object, visto: list[str] | None = None, robots_txt: str | None = None) -> Redalyc:
    permitir = robots_txt if robots_txt is not None else (GRABADAS / "robots_redalyc.txt").read_text(encoding="utf-8")

    def manejador(r: httpx.Request) -> httpx.Response:
        if visto is not None:
            visto.append(str(r.url))
        if r.url.path == "/robots.txt":
            return texto(permitir)
        if "/1/25/1/default/" in str(r.url):
            if "text/plain" not in r.headers.get("accept", ""):
                return httpx.Response(406)  # así responde el servicio real si se pide solo JSON (lo detectó el canario)
            return httpx.Response(200, json=datos)
        return httpx.Response(200, json={"resultados": None, "filtros": None, "totalResultados": 0})  # páginas siguientes

    return Redalyc(ClienteCortes(transporte=httpx.MockTransport(manejador), pausa_min_s=0, dormir=lambda s: None))


def grabado() -> dict:  # type: ignore[type-arg]
    return json.loads((GRABADAS / "redalyc.json").read_text(encoding="utf-8"))


def test_lee_lo_grabado_de_redalyc_y_lo_traduce() -> None:
    registros = list(servir_redalyc(grabado()).buscar(consulta_inicial(), 50, HOY))
    assert registros and all(r.fuente == "redalyc" for r in registros)
    primero = next(r for r in registros if r.id_externo == "194267200010")
    assert primero.titulo.startswith("Relación entre felicidad en el trabajo y desempeño laboral")
    assert primero.doi == "https://doi.org/10.35575/rvucn.n64a10" and primero.anio == 2021 and primero.idioma == "es"
    assert [a.apellido for a in primero.autores] == ["Erazo Muñoz", "Riaño Casallas"]
    assert primero.autores[0].nombre == "Pablo Andrés Erazo Muñoz"
    assert primero.url_oa == "https://www.redalyc.org/journal/1942/194267200010/194267200010.pdf"
    assert "Felicidad en el trabajo" in primero.palabras_clave and "Happiness at work" in primero.palabras_clave
    assert primero.resumen.startswith("El propósito de este artículo") and "es:" not in primero.resumen[:5]
    assert primero.revista and not primero.es_preprint


def test_filtra_por_anio_y_por_la_cadena_en_local() -> None:
    datos = grabado()
    desde_2020 = list(servir_redalyc(datos).buscar(consulta_inicial(), 50, HOY))
    assert desde_2020 and all((r.anio or 0) >= 2020 for r in desde_2020)  # el de 2016 y el de 2019 quedan fuera
    ajena = ConsultaDeBusqueda((Concepto("a", ("criptomonedas",)), Concepto("b", ("blockchain",))))
    assert list(servir_redalyc(datos).buscar(ajena, 50, HOY)) == []


def test_pide_robots_y_sus_consultas_llevan_barra_final_y_comillas() -> None:
    visto: list[str] = []
    list(servir_redalyc(grabado(), visto).buscar(consulta_inicial(), 5, HOY))
    assert visto[0] == "https://www.redalyc.org/robots.txt"
    assert any(u.endswith("/1/25/1/default/") and "%22" in u and "%20AND%20" in u for u in visto)


def test_las_consultas_van_en_pares_y_con_el_espanol_primero() -> None:
    qs = consultas_de(consulta_inicial())
    assert 1 <= len(qs) <= 8 and all(" AND " in q for q in qs)
    assert qs[0].startswith('"felicidad"') or "bienestar" in qs[0] or "eudaimon" in qs[0]
    assert "desempeño laboral" in qs[0] or "rendimiento" in qs[0] or "desempeño" in qs[0]


def test_si_robots_lo_prohibe_no_se_lee_nada() -> None:
    r = servir_redalyc(grabado(), robots_txt="User-agent: *\nDisallow: /service/\n")
    with pytest.raises(ErrorDeFuente, match="robots.txt"):
        list(r.buscar(consulta_inicial(), 5, HOY))


@pytest.mark.parametrize("cambiado", [{"otra": "forma"}, [], {"resultados": [{"sin": "titulo"}], "totalResultados": 1},
                                      {"resultados": [{"titulo": "x"}], "totalResultados": 1}])
def test_si_el_sitio_cambia_de_forma_es_un_error_de_estructura(cambiado: object) -> None:
    with pytest.raises(ErrorDeEstructura):
        list(servir_redalyc(cambiado).buscar(consulta_inicial(), 5, HOY))


# ---- salud de las fuentes frágiles ------------------------------------------------------------------------------------------------
def test_tres_fallos_de_estructura_seguidos_la_desactivan_y_un_exito_reinicia_la_cuenta() -> None:
    s = SaludDeFuentes()
    assert not s.fallo_de_estructura("redalyc", "cambió") and not s.fallo_de_estructura("redalyc", "cambió")
    s.exito("redalyc")  # un éxito en medio: la cuenta vuelve a cero
    assert not s.fallo_de_estructura("redalyc", "cambió") and not s.fallo_de_estructura("redalyc", "cambió")
    assert s.desactivada("redalyc") is None
    assert s.fallo_de_estructura("redalyc", "cambió") is True  # el tercero seguido
    assert "3 fallos seguidos" in (s.desactivada("redalyc") or "")
    assert s.fallo_de_estructura("redalyc", "otra vez") is False  # ya estaba apagada: no se avisa dos veces
    s.reactivar("redalyc")
    assert s.desactivada("redalyc") is None


def test_el_estado_sobrevive_al_reinicio(tmp_path: Path) -> None:
    ruta = tmp_path / "datos" / "estado_fuentes.json"
    s = SaludDeFuentes(ruta)
    for _ in range(3):
        s.fallo_de_estructura("redalyc", "cambió")
    assert SaludDeFuentes(ruta).desactivada("redalyc")  # otra instancia (otro arranque) lo sabe
    SaludDeFuentes(ruta).reactivar("redalyc")
    assert SaludDeFuentes(ruta).desactivada("redalyc") is None
    ruta.write_text("{ esto no es json", encoding="utf-8")
    assert SaludDeFuentes(ruta).desactivada("redalyc") is None  # un archivo dañado no rompe nada

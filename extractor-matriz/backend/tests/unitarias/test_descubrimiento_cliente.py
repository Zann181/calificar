"""Descubrimiento · cliente HTTP cortés: ritmo, reintentos, circuito, caché, presupuesto de bytes y registro sin secretos."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.contextos.descubrimiento.dominio.sitios import LimiteDeUso, SitioConCredenciales

CONTACTO = "persona@ejemplo.test"
SITIO = SitioConCredenciales(id="s", nombre="Sitio", hosts=("proxy.ejemplo.test",), portal_url="", acceso=(),
                             limite=LimiteDeUso(bytes_por_ventana=1000, ventana_s=900, pausa_min_s=8))


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0
        self.dormido: list[float] = []

    def __call__(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.dormido.append(s)
        self.t += s


def cliente(manejador: httpx.MockTransport, reloj: Reloj, **kw: object) -> ClienteCortes:
    return ClienteCortes(transporte=manejador, reloj=reloj, dormir=reloj.dormir, ahora_epoch=reloj,
                         sitios=[SITIO], **kw)  # type: ignore[arg-type]


def test_devuelve_el_json_y_pausa_entre_peticiones_al_mismo_servidor() -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(200, json={"n": 1})), reloj, pausa_min_s=1.0)
    assert c.get_json("f", "https://api.ejemplo.test/a", {"q": "1"}) == {"n": 1}
    c.get_json("f", "https://api.ejemplo.test/a", {"q": "2"})
    assert reloj.dormido and reloj.dormido[0] == pytest.approx(1.0)


def test_reintenta_un_429_respetando_retry_after_con_tope() -> None:
    reloj = Reloj()
    respuestas = iter([httpx.Response(429, headers={"Retry-After": "500"}), httpx.Response(200, json={"ok": True})])
    c = cliente(httpx.MockTransport(lambda r: next(respuestas)), reloj, espera_max_s=60)
    assert c.get_json("f", "https://api.ejemplo.test/a") == {"ok": True}
    assert 60 in reloj.dormido and max(reloj.dormido) <= 60


def test_un_429_que_no_cede_es_un_error_de_fuente_registrado_sin_secretos(caplog: pytest.LogCaptureFixture) -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(429)), reloj, max_reintentos=2)
    with caplog.at_level(logging.INFO, logger="descubrimiento"), pytest.raises(ErrorDeFuente) as e:
        c.get_json("openalex", "https://api.ejemplo.test/works", {"api_key": "SECRETA123", "mailto": CONTACTO, "q": "x"})
    assert e.value.estado_http == 429 and "429" in e.value.causa
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errores and all(r.name == "descubrimiento" for r in errores)
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRETA123" not in texto and CONTACTO not in texto and "api.ejemplo.test/works" in texto


def test_un_404_no_se_reintenta() -> None:
    reloj = Reloj()
    llamadas: list[int] = []
    c = cliente(httpx.MockTransport(lambda r: (llamadas.append(1), httpx.Response(404))[1]), reloj)
    with pytest.raises(ErrorDeFuente):
        c.get_json("f", "https://api.ejemplo.test/a")
    assert len(llamadas) == 1


def test_circuito_abierto_tras_fallos_seguidos_y_se_cierra_con_el_tiempo() -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(500)), reloj, max_reintentos=0, fallos_para_abrir=2,
                abierto_s=300)
    for _ in range(2):
        with pytest.raises(ErrorDeFuente):
            c.get_json("f", "https://api.ejemplo.test/a")
    with pytest.raises(ErrorDeFuente, match="circuito abierto"):
        c.get_json("f", "https://api.ejemplo.test/a")
    reloj.t += 301
    with pytest.raises(ErrorDeFuente) as e:  # ya no está abierto: intenta de nuevo (y el servidor sigue fallando)
        c.get_json("f", "https://api.ejemplo.test/a")
    assert "circuito" not in e.value.causa


def test_cache_en_disco_evita_repetir_la_peticion_y_vence(tmp_path: Path) -> None:
    reloj = Reloj()
    llamadas: list[int] = []
    c = cliente(httpx.MockTransport(lambda r: (llamadas.append(1), httpx.Response(200, json={"v": len(llamadas)}))[1]),
                reloj, cache_dir=tmp_path, cache_vigencia_s=100)
    assert c.get_json("f", "https://api.ejemplo.test/a", {"q": "x", "mailto": "a@b.c"}) == {"v": 1}
    assert c.get_json("f", "https://api.ejemplo.test/a", {"q": "x", "mailto": "otro@b.c"}) == {"v": 1}  # el correo no cuenta
    assert len(llamadas) == 1
    reloj.t += 101
    assert c.get_json("f", "https://api.ejemplo.test/a", {"q": "x"}) == {"v": 2}


def test_respuesta_que_no_es_json_es_error_y_se_registra(caplog: pytest.LogCaptureFixture) -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(200, text="<html>verifique que es humano</html>")), reloj)
    with caplog.at_level(logging.ERROR, logger="descubrimiento"), pytest.raises(ErrorDeFuente, match="no es JSON"):
        c.get_json("f", "https://api.ejemplo.test/a")
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_el_presupuesto_de_bytes_corta_antes_de_bloquear_la_cuenta(caplog: pytest.LogCaptureFixture) -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(200, content=b'{"x":"' + b"a" * 700 + b'"}')), reloj)
    c.get_json("f", "https://base.proxy.ejemplo.test/uno")
    assert c.bytes_en_ventana("s") > 700
    c.get_json("f", "https://base.proxy.ejemplo.test/dos")  # aún no llega al tope al decidir; ahora se pasa
    with caplog.at_level(logging.ERROR, logger="descubrimiento"), pytest.raises(ErrorDeFuente, match="tope de descarga"):
        c.get_json("f", "https://base.proxy.ejemplo.test/tres")
    assert any("tope de descarga" in r.getMessage() for r in caplog.records)
    reloj.t += 901  # pasada la ventana, vuelve a haber presupuesto
    assert c.get_json("f", "https://base.proxy.ejemplo.test/cuatro")


def test_el_sitio_con_credenciales_usa_su_pausa_larga() -> None:
    reloj = Reloj()
    c = cliente(httpx.MockTransport(lambda r: httpx.Response(200, json={})), reloj, pausa_min_s=1.0)
    c.get_json("f", "https://a.proxy.ejemplo.test/x")
    c.get_json("f", "https://a.proxy.ejemplo.test/y")
    assert reloj.dormido[0] == pytest.approx(8.0)


def test_el_correo_de_contacto_viaja_solo_a_fuentes_abiertas() -> None:
    vistos: dict[str, str] = {}

    def manejador(r: httpx.Request) -> httpx.Response:
        vistos[r.url.host] = r.headers["User-Agent"]
        return httpx.Response(200, json={})

    reloj = Reloj()
    c = ClienteCortes(contacto=CONTACTO, sitios=[SITIO], transporte=httpx.MockTransport(manejador), reloj=reloj,
                      dormir=reloj.dormir, ahora_epoch=reloj)
    c.get_json("f", "https://api.ejemplo.test/a")
    c.get_json("f", "https://base.proxy.ejemplo.test/a")
    assert CONTACTO in vistos["api.ejemplo.test"]
    assert CONTACTO not in vistos["base.proxy.ejemplo.test"] and vistos["base.proxy.ejemplo.test"].startswith("ExtractorMatriz")

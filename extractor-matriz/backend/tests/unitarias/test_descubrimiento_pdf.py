"""Descubrimiento · Fase 3: descarga de PDF abiertos (cliente cortés y resolución de direcciones), sin tocar la red."""

from __future__ import annotations

import logging
import uuid

import httpx
import pytest

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.obtencion_pdf import ObtenerPdfAbierto
from app.contextos.descubrimiento.aplicacion.importar import nombre_de_archivo
from app.contextos.descubrimiento.dominio.candidato import Autor, Candidato, RegistroBibliografico
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente

PDF = b"%PDF-1.4\n" + b"x" * 200
CONTACTO = "persona@ejemplo.test"


def servir(rutas: dict[str, httpx.Response], visto: list[httpx.Request] | None = None) -> ClienteCortes:
    def manejador(r: httpx.Request) -> httpx.Response:
        if visto is not None:
            visto.append(r)
        return rutas.get(str(r.url).split("?")[0], httpx.Response(404))

    return ClienteCortes(transporte=httpx.MockTransport(manejador), pausa_min_s=0, dormir=lambda s: None)


def pagina(meta: str = "") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                          content=f"<html><head>{meta}</head><body>landing</body></html>".encode())


def pdf(contenido: bytes = PDF) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/pdf"}, content=contenido)


def test_baja_un_pdf_directo() -> None:
    o = ObtenerPdfAbierto(servir({"https://repo.ejemplo.test/a.pdf": pdf()}))
    assert o.descargar("https://repo.ejemplo.test/a.pdf") == PDF


def test_una_pagina_con_citation_pdf_url_da_un_salto_y_resuelve_rutas_relativas() -> None:
    o = ObtenerPdfAbierto(servir({
        "https://rev.ejemplo.test/articulo/1": pagina('<meta name="citation_pdf_url" content="/descarga/1.pdf">'),
        "https://rev.ejemplo.test/descarga/1.pdf": pdf()}))
    assert o.descargar("https://rev.ejemplo.test/articulo/1") == PDF


def test_una_pagina_sin_pdf_o_que_pide_sesion_es_un_error_claro() -> None:
    o = ObtenerPdfAbierto(servir({"https://rev.ejemplo.test/x": pagina(), "https://rev.ejemplo.test/y": pagina(
        '<meta name="citation_pdf_url" content="https://rev.ejemplo.test/y">')}))
    for url in ("https://rev.ejemplo.test/x", "https://rev.ejemplo.test/y"):  # la segunda apunta a sí misma
        with pytest.raises(ErrorDeFuente, match="no entrega un PDF"):
            o.descargar(url)


def test_un_archivo_que_dice_ser_pdf_pero_no_lo_es_se_rechaza() -> None:
    o = ObtenerPdfAbierto(servir({"https://x.ejemplo.test/a.pdf": pdf(b"<html>error</html>")}))
    with pytest.raises(ErrorDeFuente, match="no entrega un PDF"):
        o.descargar("https://x.ejemplo.test/a.pdf")


def test_un_archivo_demasiado_grande_no_se_acepta() -> None:
    o = ObtenerPdfAbierto(servir({"https://x.ejemplo.test/a.pdf": pdf(PDF + b"0" * 5000)}), max_bytes=1000)
    with pytest.raises(ErrorDeFuente, match="pesa más de"):
        o.descargar("https://x.ejemplo.test/a.pdf")


def test_los_errores_http_son_errores_de_fuente(caplog: pytest.LogCaptureFixture) -> None:
    o = ObtenerPdfAbierto(servir({}))
    with caplog.at_level(logging.INFO, logger="descubrimiento"), pytest.raises(ErrorDeFuente, match="404"):
        o.descargar("https://x.ejemplo.test/no-existe.pdf")
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_urls_usa_la_de_la_fuente_primero_y_unpaywall_solo_con_correo() -> None:
    visto: list[httpx.Request] = []
    unpaywall = httpx.Response(200, json={
        "best_oa_location": {"url_for_pdf": "https://oa.ejemplo.test/mejor.pdf", "url": "https://oa.ejemplo.test/mejor"},
        "oa_locations": [{"url_for_pdf": "https://oa.ejemplo.test/mejor.pdf"}, {"url": "https://oa.ejemplo.test/otra"}]})
    cliente = servir({"https://api.unpaywall.org/v2/10.1000/abc": unpaywall}, visto)
    sin_correo = ObtenerPdfAbierto(cliente)
    assert sin_correo.urls("https://doi.org/10.1000/ABC", "https://propia.ejemplo.test/a.pdf") == [
        "https://propia.ejemplo.test/a.pdf"] and not visto  # sin correo, ni siquiera se consulta
    con_correo = ObtenerPdfAbierto(cliente, contacto=CONTACTO)
    urls = con_correo.urls("10.1000/abc", "https://propia.ejemplo.test/a.pdf")
    assert urls == ["https://propia.ejemplo.test/a.pdf", "https://oa.ejemplo.test/mejor.pdf",
                    "https://oa.ejemplo.test/mejor"]  # sin repetir y con tope de 3
    assert visto[0].url.params["email"] == CONTACTO
    assert con_correo.urls(None, None) == []


def test_si_unpaywall_falla_se_sigue_con_lo_que_habia(caplog: pytest.LogCaptureFixture) -> None:
    o = ObtenerPdfAbierto(servir({}), contacto=CONTACTO)
    with caplog.at_level(logging.INFO, logger="descubrimiento"):
        assert o.urls("10.1000/abc", "https://propia.ejemplo.test/a.pdf") == ["https://propia.ejemplo.test/a.pdf"]
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records) and CONTACTO not in texto


def test_nombre_de_archivo_legible_y_sin_caracteres_raros() -> None:
    def c(titulo: str, autores: tuple[Autor, ...], anio: int | None) -> Candidato:
        return Candidato.desde(uuid.uuid4(), RegistroBibliografico(
            fuente="x", id_externo="x", posicion=1, titulo=titulo, anio=anio, autores=autores))
    assert nombre_de_archivo(c("Felicidad: ¿y el desempeño?", (Autor("Ana Pérez", "Pérez"),), 2023)) == \
        "Perez_2023_Felicidad-y-el-desempeno.pdf"
    assert nombre_de_archivo(c("A" * 200, (), None)) == "sin-autor_s-f_" + "A" * 60 + ".pdf"

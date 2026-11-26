"""Qué cuenta como PDF gratuito y legal (ADR 0013): lo que declaran las fuentes y la comprobación del enlace. Sin red."""

from __future__ import annotations

from datetime import date

import httpx

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.comprobar_pdf import ComprobadorDePdfEnLinea
from app.contextos.descubrimiento.adaptadores.fuentes.crossref import pdfs_abiertos as de_crossref
from app.contextos.descubrimiento.adaptadores.fuentes.europepmc import EuropePMC
from app.contextos.descubrimiento.adaptadores.fuentes.openalex import pdfs_abiertos as de_openalex
from app.contextos.descubrimiento.dominio.sitios import LimiteDeUso, SitioConCredenciales

HOY = date(2026, 11, 25)


def test_openalex_solo_toma_pdf_de_ubicaciones_abiertas() -> None:
    r = {"best_oa_location": {"is_oa": True, "pdf_url": "https://a/1.pdf"},
         "locations": [{"is_oa": False, "pdf_url": "https://pago/2.pdf"}, {"is_oa": True, "pdf_url": None},
                       {"is_oa": True, "pdf_url": "https://a/1.pdf"}, {"is_oa": True, "pdf_url": "https://b/3.pdf"}]}
    assert de_openalex(r) == ("https://a/1.pdf", "https://b/3.pdf")
    assert de_openalex({"best_oa_location": None, "locations": None}) == ()


def test_crossref_solo_con_licencia_creative_commons_vigente() -> None:
    enlace = {"content-type": "application/pdf", "URL": "https://r/x.pdf"}
    cc = {"URL": "http://creativecommons.org/licenses/by/4.0/", "start": {"date-parts": [[2024, 1, 1]]}}
    assert de_crossref({"license": [cc], "link": [enlace, {"content-type": "text/xml", "URL": "https://r/x.xml"}]},
                       HOY) == ("https://r/x.pdf",)
    editorial = {"URL": "https://www.elsevier.com/tdm/userlicense/1.0/"}
    assert de_crossref({"license": [editorial], "link": [enlace]}, HOY) == ()
    futura = {**cc, "start": {"date-parts": [[2027, 6]]}}  # abre tras un embargo: todavía no
    assert de_crossref({"license": [futura], "link": [enlace]}, HOY) == ()
    assert de_crossref({"link": [enlace]}, HOY) == ()


def test_europepmc_deja_para_el_final_sus_propios_pdf_que_niega_a_programas() -> None:
    enlaces = [{"availabilityCode": "OA", "documentStyle": "pdf", "url": "https://europepmc.org/articles/PMC1?pdf=render"},
               {"availabilityCode": "S", "documentStyle": "pdf", "url": "https://pago.test/a.pdf"},
               {"availabilityCode": "F", "documentStyle": "pdf", "url": "https://revista.test/a.pdf"},
               {"availabilityCode": "OA", "documentStyle": "html", "url": "https://europepmc.org/articles/PMC1"}]
    registro = EuropePMC(ClienteCortes())._registro(
        {"id": "1", "source": "MED", "title": "Happiness", "fullTextUrlList": {"fullTextUrl": enlaces}}, 1)
    assert registro.pdfs == ("https://revista.test/a.pdf", "https://europepmc.org/articles/PMC1?pdf=render")


class Internet:
    def __init__(self, robots: str = "") -> None:
        self.pedidas: list[httpx.Request] = []
        self.robots = robots

    def __call__(self, r: httpx.Request) -> httpx.Response:
        self.pedidas.append(r)
        ruta, host = r.url.path, r.url.host
        if ruta == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        if host == "niega.test":
            return httpx.Response(403, text="<!DOCTYPE html>")
        if ruta.endswith("no-esta.pdf"):
            return httpx.Response(404)
        if ruta.endswith("pagina.pdf"):
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>inicie sesión</html>")
        if ruta.endswith("salta.pdf"):
            return httpx.Response(302, headers={"location": "https://cerrado.test/privado/a.pdf"})
        return httpx.Response(206, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7")


def comprobador(internet: Internet, **kw: object) -> ComprobadorDePdfEnLinea:
    cliente = ClienteCortes(transporte=httpx.MockTransport(internet), pausa_min_s=0, contacto="x@ejemplo.invalid",
                            **kw)  # type: ignore[arg-type]
    return ComprobadorDePdfEnLinea(cliente)


def test_pide_solo_el_comienzo_y_exige_que_sea_un_pdf() -> None:
    internet = Internet()
    c = comprobador(internet)
    assert c.entrega("https://abierto.test/a.pdf") is True
    pedido = internet.pedidas[-1]
    assert pedido.headers["range"] == "bytes=0-7"
    for malo in ("https://abierto.test/no-esta.pdf", "https://abierto.test/pagina.pdf", "ftp://abierto.test/a.pdf", "x"):
        assert c.entrega(malo) is False, malo


def test_deja_de_preguntar_a_quien_rechaza_a_los_programas() -> None:
    internet = Internet()
    c = comprobador(internet)
    assert not any(c.entrega(f"https://niega.test/{i}.pdf") for i in range(10))
    assert sum(1 for p in internet.pedidas if p.url.path.endswith(".pdf")) == 3
    assert c.entrega("https://abierto.test/a.pdf") is True  # los demás sitios siguen


def test_respeta_robots_tambien_tras_una_redireccion() -> None:
    internet = Internet(robots="User-agent: *\nDisallow: /privado/")
    c = comprobador(internet)
    assert c.entrega("https://abierto.test/privado/a.pdf") is False
    assert [p.url.path for p in internet.pedidas] == ["/robots.txt"]  # ni se intentó
    assert c.entrega("https://abierto.test/salta.pdf") is False  # redirige a una ruta prohibida
    assert c.entrega("https://abierto.test/libre/a.pdf") is True


def test_nunca_toca_un_sitio_con_credenciales() -> None:
    internet = Internet()
    sitio = SitioConCredenciales(id="u", nombre="Biblioteca", portal_url="https://portal.test/", hosts=("proxy.test",),
                                 acceso=("usuario_y_clave",),
                                 limite=LimiteDeUso(bytes_por_ventana=1, ventana_s=1, pausa_min_s=1))
    c = comprobador(internet, sitios=[sitio])
    assert c.entrega("https://x.proxy.test/a.pdf") is False and internet.pedidas == []


def test_varios_enlaces_a_la_vez_dan_cada_uno_su_respuesta() -> None:
    internet = Internet()
    c = comprobador(internet)
    urls = [f"https://s{i}.test/a.pdf" for i in range(12)] + ["https://abierto.test/pagina.pdf"] * 2
    respuesta = c.entregan(urls)
    assert len(respuesta) == 13 and sum(respuesta.values()) == 12
    assert sum(1 for p in internet.pedidas if p.url.path == "/pagina.pdf") == 1  # repetido: se pide una vez
    assert not any(c.entregan([f"https://niega.test/{i}.pdf" for i in range(20)]).values())
    assert sum(1 for p in internet.pedidas if p.url.host == "niega.test" and p.url.path != "/robots.txt") == 3


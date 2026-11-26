"""Descubrimiento · Fase 3 con adaptadores reales: importar el PDF abierto de un candidato al flujo de Biblioteca."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.main import crear_app
from tests.conftest import FIXTURES, MATRIZ
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_descubrimiento import FuenteFalsa, PdfsQueResponden, buscar, reg

KUMAR = (FIXTURES / "kumar_2022.pdf").read_bytes()
SINGH = (FIXTURES / "singh_2023.pdf").read_bytes()


class PdfFalso:
    """Un descargador que no sale a internet: sirve lo que se le indique según la dirección."""

    def __init__(self) -> None:
        self.pedidas: list[str] = []

    def urls(self, doi: str | None, url_oa: str | None) -> list[str]:
        # «sin-copia»: el enlace que había al buscar ya no ofrece nada que bajar.
        return [url_oa] if url_oa and "sin-copia" not in url_oa else []

    def descargar(self, url: str) -> bytes:
        self.pedidas.append(url)
        if "falla" in url:
            raise ErrorDeFuente("descarga", "acceso denegado (HTTP 403)")
        return SINGH if "singh" in url else KUMAR


CON_PDF = reg("a", "Happiness and job performance in nurses", "10.1000/uno", anio=2023, url_oa="https://oa.test/kumar.pdf")
OTRO_PDF = reg("a", "Subjective well-being and task performance", "10.1000/dos", anio=2022, url_oa="https://oa.test/singh.pdf")
IGUAL = reg("a", "Employee happiness and productivity", "10.1000/tres", anio=2021, url_oa="https://oa.test/kumar-otra-url.pdf")
SIN_COPIA = reg("a", "Work well-being and performance in teachers", "10.1000/cuatro", anio=2020,
                pdfs=("https://oa.test/sin-copia.pdf",))
FALLA = reg("a", "Positive affect and sales performance", "10.1000/cinco", anio=2024, url_oa="https://oa.test/falla.pdf")


@pytest.fixture
def descargador() -> PdfFalso:
    return PdfFalso()


@pytest.fixture
def ctx(fabrica, descargador: PdfFalso) -> Contenedor:  # type: ignore[no-untyped-def]
    logging.getLogger("descubrimiento").disabled = False
    fuentes = {"a": FuenteFalsa("a", [CON_PDF, OTRO_PDF, IGUAL, SIN_COPIA, FALLA])}
    return construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica,
                     almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda=fuentes, lanzar_busqueda=lanzar_aqui, comprobador_pdf=PdfsQueResponden(),
                     obtener_pdf=descargador)


@pytest.fixture
def pid(ctx: Contenedor, libro_json: dict) -> uuid.UUID:  # type: ignore[type-arg]
    p = nuevo_proyecto(ctx, "Felicidad y desempeño")
    ctx.normas.publicar.ejecutar(p, libro_json)
    buscar(ctx, p, ("a",))
    return p


@pytest.fixture
def cliente(ctx: Contenedor, pid: uuid.UUID) -> Iterator[TestClient]:
    with TestClient(crear_app(Settings(_env_file=None, despachador_en_servidor=False), ctx)) as c:
        yield c


def id_de(ctx: Contenedor, pid: uuid.UUID, doi: str) -> uuid.UUID:
    return next(c.id for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos if c.doi == doi)


def importar(cliente: TestClient, pid: uuid.UUID, *ids: uuid.UUID) -> dict[str, dict]:  # type: ignore[type-arg]
    r = cliente.post(f"/api/v1/proyectos/{pid}/candidatos/importar", json={"ids": [str(i) for i in ids]})
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()["resultados"]}


def test_importar_deja_el_pdf_en_nuevo_y_marca_el_candidato(cliente: TestClient, ctx: Contenedor,
                                                             pid: uuid.UUID, descargador: PdfFalso) -> None:
    cid = id_de(ctx, pid, "10.1000/uno")
    r = importar(cliente, pid, cid)[str(cid)]
    assert r["estado"] == "IMPORTADO" and r["articulo_id"] and "No se extrajo nada" in r["mensaje"]
    assert descargador.pedidas == ["https://oa.test/kumar.pdf"]
    articulo = ctx.biblioteca.consultas.articulo(pid, uuid.UUID(r["articulo_id"]))
    assert articulo.estado.value == "NUEVO" and articulo.nombre_archivo == "Perez_2023_Happiness-and-job-performance-in-nurses.pdf"
    c = ctx.descubrimiento.consultas.candidatos(pid).candidatos
    marcado = next(x for x in c if x.id == cid)
    assert marcado.estado.value == "IMPORTADO" and marcado.articulo_id == articulo.id


def test_no_lanza_extraccion_ni_convierte_ni_toca_la_matriz(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID) -> None:
    ctx.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    filas = len(ctx.matriz.consultas.todas(pid))
    articulos_antes = ctx.biblioteca.consultas.listar(pid).contadores
    importar(cliente, pid, id_de(ctx, pid, "10.1000/uno"), id_de(ctx, pid, "10.1000/dos"))
    listado = ctx.biblioteca.consultas.listar(pid)
    nuevos = [a for a in listado.articulos if a.estado.value == "NUEVO"]
    assert len(nuevos) == 2 and all(a.estado.value == "NUEVO" for a in listado.articulos if a.nombre_archivo.startswith("Perez_"))
    assert len(ctx.matriz.consultas.todas(pid)) == filas  # la matriz sigue igual
    assert sum(listado.contadores.values()) == sum(articulos_antes.values()) + 2
    assert listado.contadores.get("EN_COLA", 0) == 0 and listado.contadores.get("CONVIRTIENDO", 0) == 0


def test_repetir_la_importacion_no_duplica(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID,
                                            descargador: PdfFalso) -> None:
    cid = id_de(ctx, pid, "10.1000/uno")
    importar(cliente, pid, cid)
    r = importar(cliente, pid, cid)[str(cid)]
    assert r["estado"] == "YA_ESTABA" and r["mensaje"] == "Ya se había importado"
    assert len(descargador.pedidas) == 1  # ni siquiera vuelve a descargar


def test_el_mismo_pdf_en_otro_candidato_se_reconoce_por_su_huella(cliente: TestClient, ctx: Contenedor,
                                                                   pid: uuid.UUID) -> None:
    a, b = id_de(ctx, pid, "10.1000/uno"), id_de(ctx, pid, "10.1000/tres")
    primero = importar(cliente, pid, a)[str(a)]
    segundo = importar(cliente, pid, b)[str(b)]  # otra dirección, mismos bytes
    assert segundo["estado"] == "YA_ESTABA" and "ya estaba en la biblioteca" in segundo["mensaje"]
    assert segundo["articulo_id"] == primero["articulo_id"]
    assert len([x for x in ctx.biblioteca.consultas.listar(pid).articulos]) == 1


def test_sin_copia_abierta_falla_o_descartado_no_se_importan(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID,
                                                              caplog: pytest.LogCaptureFixture) -> None:
    sin, falla, desc = id_de(ctx, pid, "10.1000/cuatro"), id_de(ctx, pid, "10.1000/cinco"), id_de(ctx, pid, "10.1000/dos")
    ctx.descubrimiento.decidir.ejecutar(pid, [desc], "descartar", "fuera de alcance")
    with caplog.at_level(logging.INFO, logger="descubrimiento"):
        r = importar(cliente, pid, sin, falla, desc)
    assert r[str(sin)]["estado"] == "SIN_COPIA_ABIERTA" and "suba el PDF a mano" in r[str(sin)]["mensaje"]
    assert r[str(falla)]["estado"] == "ERROR" and "403" in r[str(falla)]["mensaje"]
    assert r[str(desc)]["estado"] == "RECHAZADO" and "reactívelo" in r[str(desc)]["mensaje"]
    assert any(x.levelno == logging.ERROR and "Importar" in x.getMessage() for x in caplog.records)  # error marcado
    assert not ctx.biblioteca.consultas.listar(pid).articulos
    estados = {c.titulo: c.estado.value for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos}
    assert estados[SIN_COPIA.titulo] == "NUEVO" and estados[FALLA.titulo] == "NUEVO"  # siguen disponibles


def test_un_archivo_que_no_es_pdf_lo_rechaza_la_biblioteca(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID,
                                                            descargador: PdfFalso) -> None:
    descargador.descargar = lambda url: b"<html>no soy un pdf</html>"  # type: ignore[method-assign]
    cid = id_de(ctx, pid, "10.1000/uno")
    r = importar(cliente, pid, cid)[str(cid)]
    assert r["estado"] == "ERROR" and "no es un PDF" in r["mensaje"]


def test_hasta_diez_a_la_vez_y_nada_de_bajar_todo(cliente: TestClient, pid: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{pid}/candidatos/importar"
    r = cliente.post(base, json={"ids": [str(uuid.uuid4()) for _ in range(11)]})
    assert r.status_code == 409 and "hasta 10" in r.json()["detail"]
    assert cliente.post(base, json={"ids": []}).status_code == 422
    assert cliente.post(base, json={"ids": [str(uuid.uuid4())]}).json()["resultados"][0]["estado"] == "ERROR"

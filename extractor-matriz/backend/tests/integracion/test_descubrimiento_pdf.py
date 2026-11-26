"""«Buscar» solo trae artículos que entregan su PDF gratis y legalmente (ADR 0013), con adaptadores SQL reales."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.contextos.descubrimiento.dominio.candidato import Candidato
from app.main import crear_app
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_descubrimiento import FuenteFalsa, PdfsQueResponden, buscar, reg

BUENO = reg("a", "Happiness and job performance in nurses", "10.1000/bueno", pdfs=("https://oa.test/bueno.pdf",))
SEGUNDO = reg("a", "Subjective well-being and task performance", "10.1000/segundo",
              pdfs=("https://oa.test/caido-1.pdf", "https://oa.test/segundo.pdf"))
CAIDO = reg("a", "Employee happiness and productivity", "10.1000/caido", pdfs=("https://oa.test/caido-2.pdf",))
DE_PAGO = reg("a", "Positive affect and sales performance", "10.1000/pago", pdfs=())


@pytest.fixture
def comprobador() -> PdfsQueResponden:
    return PdfsQueResponden()


@pytest.fixture
def ctx(fabrica, comprobador: PdfsQueResponden) -> Contenedor:  # type: ignore[no-untyped-def]
    fuentes = {"a": FuenteFalsa("a", [BUENO, SEGUNDO, CAIDO, DE_PAGO]), "b": FuenteFalsa("b", [BUENO])}
    return construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica,
                     almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda=fuentes, lanzar_busqueda=lanzar_aqui, comprobador_pdf=comprobador)


@pytest.fixture
def pid(ctx: Contenedor, libro_json: dict[str, Any]) -> uuid.UUID:
    p = nuevo_proyecto(ctx, "Felicidad y desempeño")
    ctx.normas.publicar.ejecutar(p, libro_json)
    return p


def vistos(ctx: Contenedor, pid: uuid.UUID) -> dict[str, str | None]:
    return {c.titulo: c.url_pdf for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos}


def test_solo_entra_lo_que_entrega_un_pdf_y_lo_demas_queda_contado(ctx: Contenedor, pid: uuid.UUID) -> None:
    b = buscar(ctx, pid, ("a",))
    assert vistos(ctx, pid) == {BUENO.titulo: "https://oa.test/bueno.pdf", SEGUNDO.titulo: "https://oa.test/segundo.pdf"}
    p = b.progreso["a"]
    assert (p.encontrados, p.sin_pdf, p.errores, b.total_unicos) == (2, 2, 0, 2)  # no tener PDF no es un error


def test_cada_enlace_se_prueba_una_vez_y_lo_ya_comprobado_no_se_vuelve_a_pedir(
        ctx: Contenedor, pid: uuid.UUID, comprobador: PdfsQueResponden) -> None:
    primera = buscar(ctx, pid, ("a", "b"))
    assert primera.progreso["b"].encontrados == 1
    assert comprobador.pedidos.count("https://oa.test/bueno.pdf") == 1  # lo trajeron las dos fuentes
    comprobador.pedidos.clear()
    buscar(ctx, pid, ("a",))
    assert "https://oa.test/bueno.pdf" not in comprobador.pedidos
    assert "https://oa.test/segundo.pdf" not in comprobador.pedidos


def test_lo_de_antes_sin_pdf_se_oculta_hasta_que_una_busqueda_lo_compruebe(ctx: Contenedor, pid: uuid.UUID) -> None:
    repo = ctx.descubrimiento.buscar._candidatos
    viejo = Candidato.desde(pid, BUENO)  # como los guardados antes de esta regla: sin `url_pdf`
    decidido = Candidato.desde(pid, DE_PAGO)
    decidido.descartar("de pago")
    repo.guardar(viejo)
    repo.guardar(decidido)
    lista = ctx.descubrimiento.consultas.candidatos(pid)
    assert [c.titulo for c in lista.candidatos] == [DE_PAGO.titulo]  # lo que la persona decidió sigue a la vista
    assert lista.contadores["SIN_PDF"] == 1 and lista.contadores["NUEVO"] == 0
    buscar(ctx, pid, ("a",))
    lista = ctx.descubrimiento.consultas.candidatos(pid)
    assert lista.contadores["SIN_PDF"] == 0 and vistos(ctx, pid)[BUENO.titulo] == "https://oa.test/bueno.pdf"
    assert next(c for c in lista.candidatos if c.titulo == BUENO.titulo).id == viejo.id


def test_la_api_y_la_exportacion_dan_el_enlace_del_pdf(ctx: Contenedor, pid: uuid.UUID) -> None:
    buscar(ctx, pid, ("a",))
    web = TestClient(crear_app(Settings(_env_file=None, despachador_en_servidor=False), ctx))
    lista = web.get(f"/api/v1/proyectos/{pid}/candidatos").json()["candidatos"]
    assert all(c["url_pdf"].endswith(".pdf") for c in lista)
    ids = [c["id"] for c in lista]
    for formato, marca in (("csv", "PDF gratis"), ("ris", "L1  - https://oa.test/")):
        r = web.post(f"/api/v1/proyectos/{pid}/candidatos/exportar", json={"ids": ids, "formato": formato})
        assert marca in r.text and "https://oa.test/segundo.pdf" in r.text, formato
    progreso = web.get(f"/api/v1/proyectos/{pid}/busquedas").json()["busquedas"][0]["progreso"]["a"]
    assert progreso["sin_pdf"] == 2

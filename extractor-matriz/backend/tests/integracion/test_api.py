"""API: sesión, columnas desde el catálogo y carga de PDF duplicados."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor
from app.config import Settings
from app.main import crear_app
from tests.conftest import FIXTURES


@pytest.fixture
def cliente(contenedor: Contenedor, ajustes: Settings, proyecto: uuid.UUID) -> Iterator[TestClient]:
    with TestClient(crear_app(ajustes, contenedor)) as c:
        yield c


def test_no_hay_login_ni_sesion(cliente: TestClient, proyecto: uuid.UUID) -> None:
    assert cliente.get(f"/api/v1/proyectos/{proyecto}/normas/columnas").status_code == 200
    assert cliente.post("/api/v1/sesion", json={}).status_code in (404, 405)


def test_columnas_vienen_del_catalogo(cliente: TestClient, proyecto: uuid.UUID) -> None:
    columnas = cliente.get(f"/api/v1/proyectos/{proyecto}/normas/columnas").json()
    assert len(columnas) == 54
    assert columnas[0]["clave"] == "Documento"
    incluir = next(c for c in columnas if c["clave"] == "Incluir en meta análisi")
    assert "SEM latente" in incluir["valores_permitidos"]


def test_proyecto_inexistente(cliente: TestClient) -> None:
    assert cliente.get(f"/api/v1/proyectos/{uuid.uuid4()}/normas/columnas").status_code == 404


def test_cargar_pdf_repetido_por_la_api(cliente: TestClient, proyecto: uuid.UUID) -> None:
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    archivos = [("archivos", ("kumar_2022.pdf", pdf, "application/pdf")),
                ("archivos", ("copia.pdf", pdf, "application/pdf"))]
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/articulos", files=archivos)
    assert r.status_code == 200, r.text
    assert [x["duplicado"] for x in r.json()] == [False, True]


def test_descargar_pdf_sin_s3(cliente: TestClient, proyecto: uuid.UUID) -> None:
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/articulos",
                     files=[("archivos", ("kumar_2022.pdf", pdf, "application/pdf"))])
    articulo_id = r.json()[0]["articulo_id"]
    descarga = cliente.get(f"/api/v1/proyectos/{proyecto}/articulos/{articulo_id}/pdf")
    assert descarga.status_code == 200
    assert descarga.headers["content-type"] == "application/pdf"
    assert descarga.content == pdf

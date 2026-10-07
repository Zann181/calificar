"""API: sesión, columnas desde el catálogo y carga de PDF duplicados."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.compartido.seguridad import crear_usuario
from app.composicion import Contenedor
from app.config import Settings
from app.main import crear_app
from tests.conftest import FIXTURES

CORREO, CLAVE = "revisor@local.test", "clave-de-prueba-123"


@pytest.fixture
def cliente(contenedor: Contenedor, ajustes: Settings, proyecto: uuid.UUID) -> Iterator[TestClient]:
    with contenedor.fabrica() as s:
        crear_usuario(s, correo=CORREO, nombre="Revisor", rol="revisor", clave=CLAVE)
    with TestClient(crear_app(ajustes, contenedor)) as c:
        yield c


def entrar(c: TestClient) -> None:
    r = c.post("/api/v1/sesion", json={"correo": CORREO, "clave": CLAVE})
    assert r.status_code == 200, r.text


def test_sin_sesion_responde_401(cliente: TestClient, proyecto: uuid.UUID) -> None:
    assert cliente.get(f"/api/v1/proyectos/{proyecto}/normas/columnas").status_code == 401


def test_clave_incorrecta(cliente: TestClient) -> None:
    r = cliente.post("/api/v1/sesion", json={"correo": CORREO, "clave": "otra-clave-larga"})
    assert r.status_code == 401


def test_columnas_vienen_del_catalogo(cliente: TestClient, proyecto: uuid.UUID) -> None:
    entrar(cliente)
    columnas = cliente.get(f"/api/v1/proyectos/{proyecto}/normas/columnas").json()
    assert len(columnas) == 54
    assert columnas[0]["clave"] == "Documento"
    incluir = next(c for c in columnas if c["clave"] == "Incluir en meta análisi")
    assert "SEM latente" in incluir["valores_permitidos"]


def test_proyecto_inexistente(cliente: TestClient) -> None:
    entrar(cliente)
    assert cliente.get(f"/api/v1/proyectos/{uuid.uuid4()}/normas/columnas").status_code == 404


def test_cargar_pdf_repetido_por_la_api(cliente: TestClient, proyecto: uuid.UUID) -> None:
    entrar(cliente)
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    archivos = [("archivos", ("kumar_2022.pdf", pdf, "application/pdf")),
                ("archivos", ("copia.pdf", pdf, "application/pdf"))]
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/articulos", files=archivos)
    assert r.status_code == 200, r.text
    assert [x["duplicado"] for x in r.json()] == [False, True]


def test_descargar_pdf_sin_s3(cliente: TestClient, proyecto: uuid.UUID) -> None:
    entrar(cliente)
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/articulos",
                     files=[("archivos", ("kumar_2022.pdf", pdf, "application/pdf"))])
    articulo_id = r.json()[0]["articulo_id"]
    descarga = cliente.get(f"/api/v1/proyectos/{proyecto}/articulos/{articulo_id}/pdf")
    assert descarga.status_code == 200
    assert descarga.headers["content-type"] == "application/pdf"
    assert descarga.content == pdf

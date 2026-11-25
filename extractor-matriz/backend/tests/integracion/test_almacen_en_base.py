"""AlmacenEnBase (ADR 0009, compuerta 0.3): archivos como bytea en la misma base.

Corre sobre SQLite y, con PRUEBAS_POSTGRES_URL, sobre PostgreSQL.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnBase
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.biblioteca.adaptadores.tablas import RegistroArchivo
from app.main import crear_app
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto


def test_guardar_leer_y_sobrescribir(fabrica: Callable[[], Session]) -> None:
    a = AlmacenEnBase(fabrica)
    assert not a.existe("pdf/p/a.pdf")
    a.guardar("pdf/p/a.pdf", b"%PDF-uno", "application/pdf")
    assert a.existe("pdf/p/a.pdf")
    assert a.leer("pdf/p/a.pdf") == b"%PDF-uno"
    a.guardar("pdf/p/a.pdf", b"%PDF-dos", "application/pdf")  # misma clave: reemplaza, no duplica
    assert a.leer("pdf/p/a.pdf") == b"%PDF-dos"
    with fabrica() as s:
        filas = s.scalars(select(RegistroArchivo)).all()
        assert len(filas) == 1
        assert filas[0].tamano == 8 and filas[0].sha256 == hashlib.sha256(b"%PDF-dos").hexdigest()


def test_clave_inexistente(fabrica: Callable[[], Session]) -> None:
    with pytest.raises(FileNotFoundError):
        AlmacenEnBase(fabrica).leer("no/existe")


def test_sesenta_megas_de_archivos(fabrica: Callable[[], Session]) -> None:
    """El tamaño de hoy (35 MB de PDF + 24 MB de crudo): 53 PDF de hasta 3,4 MB y 54 zip de hasta 2 MB."""
    a = AlmacenEnBase(fabrica)
    pesados = {f"pdf/p/{i}.pdf": os.urandom(3_400_000 if i == 0 else 660_000) for i in range(53)}
    pesados.update({f"crudo/{i}.zip": os.urandom(2_000_000 if i == 0 else 420_000) for i in range(54)})
    inicio = time.monotonic()
    for clave, datos in pesados.items():
        a.guardar(clave, datos, "application/octet-stream")
    for clave, datos in pesados.items():
        assert a.leer(clave) == datos
    assert time.monotonic() - inicio < 60  # holgado: en la práctica son pocos segundos


@pytest.fixture
def cliente_nube(fabrica: Callable[[], Session]) -> Iterator[tuple[TestClient, Contenedor]]:
    ajustes = Settings(_env_file=None, modo="nube", despachador_en_servidor=True)
    c = construir(ajustes, fabrica=fabrica, conversor=ConversorFijo(FIXTURES / "mineru"))
    assert isinstance(c.almacen, AlmacenEnBase)  # en modo nube los archivos van a la base sin configurar nada más
    with TestClient(crear_app(ajustes, c)) as cliente:
        yield cliente, c


def test_modo_nube_no_arranca_hilos_de_fondo(cliente_nube: tuple[TestClient, Contenedor]) -> None:
    cliente, c = cliente_nube
    assert cliente.get("/api/v1/salud").json() == {"estado": "ok"}
    assert c.despachador._hilo is None  # ni aunque despachador_en_servidor sea True


def test_pdf_desde_la_base_con_range(cliente_nube: tuple[TestClient, Contenedor]) -> None:
    cliente, c = cliente_nube
    proyecto = nuevo_proyecto(c, "Nube")
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    r = c.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", pdf)
    assert r.articulo_id is not None
    ruta = f"/api/v1/proyectos/{proyecto}/articulos/{r.articulo_id}/pdf"
    completo = cliente.get(ruta)
    assert completo.status_code == 200 and completo.content == pdf
    assert completo.headers["accept-ranges"] == "bytes"
    parcial = cliente.get(ruta, headers={"Range": "bytes=0-1023"})
    assert parcial.status_code == 206
    assert parcial.content == pdf[:1024]
    assert parcial.headers["content-range"] == f"bytes 0-1023/{len(pdf)}"
    final = cliente.get(ruta, headers={"Range": "bytes=-100"})
    assert final.status_code == 206 and final.content == pdf[-100:]


def test_proyecto_distinto_no_ve_el_archivo(cliente_nube: tuple[TestClient, Contenedor]) -> None:
    cliente, c = cliente_nube
    otro = nuevo_proyecto(c, "Otro")
    assert cliente.get(f"/api/v1/proyectos/{otro}/articulos/{uuid.uuid4()}/pdf").status_code == 404

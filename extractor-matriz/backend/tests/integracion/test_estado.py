"""Estado de servicios, despachador en hilo y barrido de artículos Nuevo."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.biblioteca.puertos import Conversion
from app.main import crear_app
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_api import CLAVE, CORREO, cliente, entrar  # noqa: F401


def test_estado_lista_las_cinco_piezas(cliente: TestClient) -> None:  # noqa: F811
    entrar(cliente)
    piezas = {p["id"]: p for p in cliente.get("/api/v1/estado").json()["componentes"]}
    assert set(piezas) == {"servidor", "despachador", "mineru", "claude", "pdftotext"}
    assert piezas["servidor"]["estado"] == "ok"
    assert piezas["despachador"]["estado"] == "error"  # en las pruebas el servidor no lo arranca
    assert piezas["mineru"]["estado"] == "ok"  # el conversor de prueba no tiene servicio: siempre disponible


def test_el_servidor_arranca_el_despachador(contenedor: Contenedor, ajustes: Settings) -> None:
    ajustes = ajustes.model_copy(update={"despachador_en_servidor": True})
    with TestClient(crear_app(ajustes, contenedor)):
        for _ in range(50):
            if contenedor.despachador.activo:
                break
            time.sleep(0.1)
        assert contenedor.despachador.activo
    assert not contenedor.despachador.activo


def test_barrido_convierte_los_nuevos(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    r = contenedor.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", pdf)
    assert r.articulo_id is not None
    assert contenedor.convertir_nuevos() == 1
    assert contenedor.biblioteca.consultas.articulo(proyecto, r.articulo_id).estado == EstadoArticulo.LISTO
    assert contenedor.convertir_nuevos() == 0


class ConversorCaido:
    def salud(self) -> dict[str, str]:
        raise ConnectionError("MinerU apagado")

    def convertir(self, pdf: bytes, nombre: str) -> Conversion:
        raise AssertionError("no debe intentar convertir con MinerU caído")


def test_sin_mineru_el_articulo_sigue_nuevo(fabrica: Callable[[], Session], ajustes: Settings,
                                            libro_json: dict[str, Any]) -> None:
    c = construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorCaido())
    pid = nuevo_proyecto(c, "Sin MinerU")
    r = c.biblioteca.cargar.ejecutar(pid, "singh_2023.pdf", (FIXTURES / "singh_2023.pdf").read_bytes())
    assert r.articulo_id is not None
    assert c.mineru() is None
    assert c.convertir_nuevos() == 0
    assert c.biblioteca.consultas.articulo(pid, r.articulo_id).estado == EstadoArticulo.NUEVO


def test_mineru_ocupado_se_distingue_de_caido(contenedor: Contenedor, ajustes: Settings) -> None:
    import socket

    from app.estado import _mineru

    contenedor.mineru = lambda: None  # type: ignore[method-assign,assignment]
    with socket.socket() as servidor:  # escucha pero no contesta: como MinerU convirtiendo
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        ocupado = ajustes.model_copy(update={"mineru_url": f"http://127.0.0.1:{servidor.getsockname()[1]}"})
        assert _mineru(contenedor, ocupado)["estado"] == "aviso"
    caido = ajustes.model_copy(update={"mineru_url": "http://127.0.0.1:9"})
    assert _mineru(contenedor, caido)["estado"] == "error"

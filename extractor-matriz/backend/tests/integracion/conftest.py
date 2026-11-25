"""Adaptadores reales sobre SQLite, sin Docker (ADR 0003).

El esquema se crea con la migración de Alembic, no con create_all: así cada corrida prueba
también la migración. MinIO se reemplaza por AlmacenEnMemoria y MinerU por ConversorFijo.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.compartido.db import RegistroProyecto, crear_motor, fabrica_de_sesiones
from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from tests.conftest import FIXTURES, LIBRO

BACKEND = Path(__file__).resolve().parents[2]


def migrar(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    command.upgrade(cfg, "head")


def _fabrica_nueva(tmp_path: Path, nombre: str) -> Iterator[Callable[[], Session]]:
    """SQLite por defecto. Con PRUEBAS_POSTGRES_URL corre sobre PostgreSQL (ADR 0009, compuerta 0.1):
    cada base usa un esquema propio, migrado con Alembic y borrado al terminar."""
    base = os.environ.get("PRUEBAS_POSTGRES_URL")
    if not base:
        url = f"sqlite:///{(tmp_path / (nombre + '.db')).as_posix()}"
        migrar(url)
        motor = crear_motor(url)
        yield fabrica_de_sesiones(motor)
        motor.dispose()
        return
    esquema = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE SCHEMA "{esquema}"'))
    url = f"{base}{'&' if '?' in base else '?'}options=-csearch_path%3D{esquema}"
    try:
        migrar(url)
        motor = crear_motor(url)
        yield fabrica_de_sesiones(motor)
        motor.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def fabrica(tmp_path: Path) -> Iterator[Callable[[], Session]]:
    yield from _fabrica_nueva(tmp_path, "prueba")


@pytest.fixture
def fabrica_nube(tmp_path: Path) -> Iterator[Callable[[], Session]]:
    """Segunda base, vacía: la de la nube en las pruebas de sincronización."""
    yield from _fabrica_nueva(tmp_path, "nube")


@pytest.fixture
def fabrica_nuevo(tmp_path: Path) -> Iterator[Callable[[], Session]]:
    """Tercera base, vacía: un equipo nuevo que se restaura desde la nube."""
    yield from _fabrica_nueva(tmp_path, "nuevo")


@pytest.fixture
def ajustes() -> Settings:
    return Settings(_env_file=None, despachador_en_servidor=False)


@pytest.fixture
def contenedor(fabrica: Callable[[], Session], ajustes: Settings) -> Contenedor:
    return construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(),
                     conversor=ConversorFijo(FIXTURES / "mineru"))


def nuevo_proyecto(c: Contenedor, nombre: str) -> uuid.UUID:
    pid = uuid.uuid4()
    with c.fabrica() as s:
        s.add(RegistroProyecto(id=pid, nombre=nombre))
        s.commit()
    return pid


@pytest.fixture
def libro_json() -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(LIBRO.read_text(encoding="utf-8"))
    return datos


@pytest.fixture
def proyecto(contenedor: Contenedor, libro_json: dict[str, Any]) -> uuid.UUID:
    """Proyecto con el libro de códigos publicado."""
    pid = nuevo_proyecto(contenedor, "Felicidad y desempeño")
    contenedor.normas.publicar.ejecutar(pid, libro_json)
    return pid


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integracion" in str(item.fspath):
            item.add_marker(pytest.mark.integracion)

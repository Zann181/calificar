"""Fixtures comunes: rutas de recursos y el libro de códigos vigente."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.compartido.columnas import DefinicionDeColumna
from app.contextos.normas.dominio.catalogo import derivar_columnas

RAIZ = Path(__file__).resolve().parents[2]
RECURSOS = RAIZ / "recursos"
FIXTURES = RECURSOS / "fixtures"
LIBRO = RECURSOS / "Libro_de_codigos_extraccion_v2.json"
MATRIZ = RECURSOS / "Matriz_de_sintesis_con_notas.xlsx"


@pytest.fixture(scope="session")
def _libro_original() -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(LIBRO.read_text(encoding="utf-8"))
    return datos


@pytest.fixture
def libro(_libro_original: dict[str, Any]) -> dict[str, Any]:
    """Copia propia por prueba: se puede modificar sin afectar a las demás."""
    return copy.deepcopy(_libro_original)


@pytest.fixture(scope="session")
def columnas(_libro_original: dict[str, Any]) -> list[DefinicionDeColumna]:
    return derivar_columnas(_libro_original)


@pytest.fixture(scope="session")
def por_clave(columnas: list[DefinicionDeColumna]) -> dict[str, DefinicionDeColumna]:
    return {c.clave: c for c in columnas}

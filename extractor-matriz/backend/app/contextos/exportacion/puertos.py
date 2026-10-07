"""Puertos de Exportación (contexto de solo lectura, sin agregado)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.compartido.columnas import DefinicionDeColumna


@dataclass(frozen=True)
class FilaExportable:
    estudio: int
    origen: str  # HEREDADA | EXTRAIDA
    valores: dict[str, Any]  # clave → valor (fechas como {"$fecha": ...})
    notas_heredadas: dict[str, dict[str, Any]] = field(default_factory=dict)
    fila_excel_origen: int | None = None
    salida: dict[str, Any] | None = None  # {fila, trazabilidad} con el formato de esquema_de_salida
    auditoria: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MatrizBase:
    datos: bytes
    hoja: str


class FuenteDeMatriz(Protocol):
    """Lo implementa la composición con las consultas de Matriz y Normas."""

    def columnas(self, proyecto_id: uuid.UUID) -> list[DefinicionDeColumna]: ...
    def libro(self, proyecto_id: uuid.UUID) -> dict[str, Any]: ...
    def base(self, proyecto_id: uuid.UUID) -> MatrizBase: ...
    def filas(self, proyecto_id: uuid.UUID) -> list[FilaExportable]: ...


class EscritorDeHeredadas(Protocol):
    def escribir(self, base: MatrizBase, filas: list[FilaExportable], columnas: list[DefinicionDeColumna]) -> bytes: ...


class EscritorDeMatriz(Protocol):
    def escribir(self, salida: list[dict[str, Any]], libro: dict[str, Any], matriz_base: bytes,
                 auditoria: list[dict[str, Any]]) -> bytes: ...


class AlmacenDeExportaciones(Protocol):
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...
    def leer(self, clave: str) -> bytes: ...

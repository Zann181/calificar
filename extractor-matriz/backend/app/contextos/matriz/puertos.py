"""Puertos del contexto Matriz."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.unidad_de_trabajo import UnidadDeTrabajo
from app.contextos.matriz.dominio.fila import FilaDeEfecto


class ConsultaDeColumnas(Protocol):
    """Lo implementa la composición llamando al caso de uso de Normas."""

    def columnas(self, proyecto_id: uuid.UUID) -> list[DefinicionDeColumna]: ...
    def version_activa_id(self, proyecto_id: uuid.UUID) -> uuid.UUID: ...


@dataclass(frozen=True)
class NotaDeCelda:
    autor: str | None
    texto: str


@dataclass
class FilaLeida:
    fila_excel: int
    valores: dict[int, Any]  # posición de columna → valor tal como está en el Excel
    notas: dict[int, NotaDeCelda] = field(default_factory=dict)


@dataclass
class MatrizLeida:
    hoja: str
    filas: list[FilaLeida]


class LectorDeMatriz(Protocol):
    def leer(self, datos: bytes, columnas: list[DefinicionDeColumna]) -> MatrizLeida: ...


class AlmacenDeMatrices(Protocol):
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...
    def leer(self, clave: str) -> bytes: ...


@dataclass(frozen=True)
class BaseDeMatriz:
    clave_almacen: str
    nombre_archivo: str
    huella_sha256: str
    hoja: str


class RepositorioDeFilas(Protocol):
    def agregar(self, fila: FilaDeEfecto) -> None: ...
    def por_estudio(self, proyecto_id: uuid.UUID, estudio: int) -> FilaDeEfecto: ...
    def todas(self, proyecto_id: uuid.UUID) -> list[FilaDeEfecto]: ...
    def pagina(self, proyecto_id: uuid.UUID, *, desde: int, cuantas: int,
               documento: int | None = None) -> tuple[list[FilaDeEfecto], int]: ...
    def cuantas(self, proyecto_id: uuid.UUID) -> int: ...
    def borrar_heredadas(self, proyecto_id: uuid.UUID) -> int: ...
    def quitar(self, proyecto_id: uuid.UUID, estudio: int) -> bool: ...
    def hay_extraidas(self, proyecto_id: uuid.UUID) -> bool: ...
    def ajustar_secuencia(self, proyecto_id: uuid.UUID, siguiente: int) -> None: ...
    def siguiente_estudio(self, proyecto_id: uuid.UUID) -> int: ...
    def guardar_base(self, proyecto_id: uuid.UUID, base: BaseDeMatriz) -> None: ...
    def base(self, proyecto_id: uuid.UUID) -> BaseDeMatriz | None: ...


class UnidadDeTrabajoMatriz(UnidadDeTrabajo, Protocol):
    # Propiedad de solo lectura: el adaptador puede exponer un subtipo del repositorio.
    @property
    def filas(self) -> RepositorioDeFilas: ...

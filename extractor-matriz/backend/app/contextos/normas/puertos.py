"""Puertos del contexto Normas."""

from __future__ import annotations

import uuid
from typing import Protocol

from app.compartido.unidad_de_trabajo import UnidadDeTrabajo
from app.contextos.normas.dominio.modelos import VersionDelLibro


class RepositorioDeLibros(Protocol):
    def agregar(self, libro: VersionDelLibro) -> None: ...
    def activa(self, proyecto_id: uuid.UUID) -> VersionDelLibro | None: ...
    def por_hash(self, proyecto_id: uuid.UUID, hash_: str) -> VersionDelLibro | None: ...
    def listar(self, proyecto_id: uuid.UUID) -> list[VersionDelLibro]: ...


class UnidadDeTrabajoNormas(UnidadDeTrabajo, Protocol):
    # Propiedad de solo lectura: el adaptador puede exponer un subtipo del repositorio.
    @property
    def libros(self) -> RepositorioDeLibros: ...

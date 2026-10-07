"""Núcleo compartido del dominio: Entidad, ObjetoDeValor, EventoDeDominio y ErrorDeDominio.

Sin dependencias de infraestructura (lo verifica import-linter).
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def ahora() -> datetime:
    return datetime.now(UTC)


class ErrorDeDominio(Exception):
    """Violación de una regla del dominio."""


class NoEncontrado(ErrorDeDominio):
    """El agregado pedido no existe en el proyecto."""


@dataclass(frozen=True)
class ObjetoDeValor:
    """Marca de los objetos de valor: inmutables y comparados por sus campos."""


def _a_json(valor: Any) -> Any:
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return {f.name: _a_json(getattr(valor, f.name)) for f in dataclasses.fields(valor)}
    if isinstance(valor, dict):
        return {str(k): _a_json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_a_json(v) for v in valor]
    return valor


@dataclass(frozen=True, kw_only=True)
class EventoDeDominio:
    """Hecho del dominio. Se publica en la outbox al confirmar la unidad de trabajo."""

    proyecto_id: uuid.UUID
    ocurrido_en: datetime = field(default_factory=ahora)

    @property
    def nombre(self) -> str:
        return type(self).__name__

    def datos(self) -> dict[str, Any]:
        resultado: dict[str, Any] = _a_json(self)
        return resultado


@dataclass(kw_only=True, eq=False)
class Entidad:
    """Base de agregados y entidades: identidad por id y registro de eventos."""

    proyecto_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    creado_en: datetime = field(default_factory=ahora)
    actualizado_en: datetime = field(default_factory=ahora)
    _eventos: list[EventoDeDominio] = field(default_factory=list, init=False, repr=False, compare=False)

    def __eq__(self, otro: object) -> bool:
        return isinstance(otro, Entidad) and type(self) is type(otro) and self.id == otro.id

    def __hash__(self) -> int:
        return hash(self.id)

    def registrar(self, evento: EventoDeDominio) -> None:
        self._eventos.append(evento)
        self.actualizado_en = ahora()

    def extraer_eventos(self) -> list[EventoDeDominio]:
        eventos, self._eventos = self._eventos, []
        return eventos

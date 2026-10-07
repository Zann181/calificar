"""Eventos públicos del contexto Matriz."""

import uuid
from dataclasses import dataclass

from app.compartido.dominio import EventoDeDominio


@dataclass(frozen=True, kw_only=True)
class FilaEscrita(EventoDeDominio):
    fila_id: uuid.UUID
    estudio: int
    origen: str


@dataclass(frozen=True, kw_only=True)
class CeldaAprobada(EventoDeDominio):
    fila_id: uuid.UUID
    estudio: int
    clave: str
    autor: str


@dataclass(frozen=True, kw_only=True)
class CeldaCorregida(EventoDeDominio):
    fila_id: uuid.UUID
    estudio: int
    clave: str
    autor: str
    motivo: str


@dataclass(frozen=True, kw_only=True)
class CeldaRechazada(EventoDeDominio):
    fila_id: uuid.UUID
    estudio: int
    clave: str
    autor: str
    motivo: str


@dataclass(frozen=True, kw_only=True)
class FilaAprobada(EventoDeDominio):
    fila_id: uuid.UUID
    estudio: int
    autor: str

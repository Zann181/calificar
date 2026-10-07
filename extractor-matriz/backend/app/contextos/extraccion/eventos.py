"""Eventos públicos del contexto Extracción."""

import uuid
from dataclasses import dataclass

from app.compartido.dominio import EventoDeDominio


@dataclass(frozen=True, kw_only=True)
class ExtraccionCompletada(EventoDeDominio):
    """Matriz escribe las filas al recibirlo (sección 8.3, paso 9)."""

    extraccion_id: uuid.UUID
    articulo_id: uuid.UUID
    estudios: list[int]
    acuerdo_campos_criticos: float | None


@dataclass(frozen=True, kw_only=True)
class ExtraccionFallida(EventoDeDominio):
    extraccion_id: uuid.UUID
    articulo_id: uuid.UUID
    paso: str
    mensaje: str


@dataclass(frozen=True, kw_only=True)
class CitaNoVerificable(EventoDeDominio):
    extraccion_id: uuid.UUID
    articulo_id: uuid.UUID
    estudio: int
    columna: str
    indice_evidencia: int

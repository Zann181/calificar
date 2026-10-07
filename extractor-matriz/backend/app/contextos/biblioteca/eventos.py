"""Eventos públicos del contexto Biblioteca."""

import uuid
from dataclasses import dataclass

from app.compartido.dominio import EventoDeDominio


@dataclass(frozen=True, kw_only=True)
class ArticuloCargado(EventoDeDominio):
    articulo_id: uuid.UUID
    nombre_archivo: str
    huella_sha256: str


@dataclass(frozen=True, kw_only=True)
class ArticuloConvertido(EventoDeDominio):
    articulo_id: uuid.UUID
    documento_estructurado_id: uuid.UUID
    paginas: int


@dataclass(frozen=True, kw_only=True)
class ConversionFallida(EventoDeDominio):
    articulo_id: uuid.UUID
    mensaje: str


@dataclass(frozen=True, kw_only=True)
class ArticuloExcluido(EventoDeDominio):
    articulo_id: uuid.UUID
    motivo: str


@dataclass(frozen=True, kw_only=True)
class EstadoDeArticuloCambiado(EventoDeDominio):
    """Notifica a la interfaz (WebSocket) cada transición."""

    articulo_id: uuid.UUID
    anterior: str
    nuevo: str

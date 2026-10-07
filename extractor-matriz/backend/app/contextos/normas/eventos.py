"""Eventos públicos del contexto Normas."""

import uuid
from dataclasses import dataclass

from app.compartido.dominio import EventoDeDominio


@dataclass(frozen=True, kw_only=True)
class LibroPublicado(EventoDeDominio):
    version_libro_id: uuid.UUID
    version: str
    hash: str

"""Tipos de identificador. Todos son UUID; los alias documentan a qué agregado apuntan."""

import uuid
from typing import NewType

ProyectoId = NewType("ProyectoId", uuid.UUID)
ArticuloId = NewType("ArticuloId", uuid.UUID)
VersionDelLibroId = NewType("VersionDelLibroId", uuid.UUID)
FilaId = NewType("FilaId", uuid.UUID)
UsuarioId = NewType("UsuarioId", uuid.UUID)


def nuevo_id() -> uuid.UUID:
    return uuid.uuid4()

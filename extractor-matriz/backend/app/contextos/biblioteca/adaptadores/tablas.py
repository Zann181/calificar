"""Tablas del contexto Biblioteca."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.compartido.db import Base


class RegistroArticulo(Base):
    __tablename__ = "biblioteca_articulos"
    __table_args__ = (UniqueConstraint("proyecto_id", "huella_sha256", name="uq_articulo_huella"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    nombre_archivo: Mapped[str] = mapped_column(String(500))
    huella_sha256: Mapped[str] = mapped_column(String(64))
    clave_almacen: Mapped[str] = mapped_column(String(500))
    paginas: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    documento_estructurado_id: Mapped[uuid.UUID | None]
    error: Mapped[dict[str, Any] | None]
    excluido_motivo: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Bloqueo optimista: dos procesos no pueden avanzar el mismo artículo a la vez.
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}


class RegistroDocumento(Base):
    """DocumentoEstructurado como JSONB. Una fila por conversión; el artículo apunta a la vigente."""

    __tablename__ = "biblioteca_documentos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    articulo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("biblioteca_articulos.id"), index=True)
    contenido: Mapped[dict[str, Any]]
    version_conversor: Mapped[str | None] = mapped_column(String(100))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))

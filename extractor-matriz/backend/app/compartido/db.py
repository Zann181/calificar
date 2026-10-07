"""Base de SQLAlchemy y tablas del núcleo compartido (proyectos, usuarios, outbox).

Cada contexto declara sus tablas en <contexto>/adaptadores/tablas.py con el prefijo del contexto.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import JSON, Uuid

# JSONB en PostgreSQL; JSON genérico en otros motores (solo pruebas unitarias de adaptadores).
JsonB = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JsonB, list[Any]: JsonB, uuid.UUID: Uuid(as_uuid=True)}


class RegistroProyecto(Base):
    __tablename__ = "proyectos"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistroUsuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    correo: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(30))  # extractor | revisor | administrador
    hash_clave: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistroOutbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100), index=True)
    datos: Mapped[dict[str, Any]]
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    despachado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    intentos: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)


def crear_motor(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def fabrica_de_sesiones(motor: Engine) -> sessionmaker[Any]:
    return sessionmaker(bind=motor, expire_on_commit=False, future=True)

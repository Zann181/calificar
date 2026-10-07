"""Tablas, repositorio SQL y unidad de trabajo de Normas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.compartido.dominio import Entidad
from app.compartido.unidad_de_trabajo_sql import UnidadDeTrabajoSql
from app.contextos.normas.dominio.modelos import VersionDelLibro


class RegistroVersionDelLibro(Base):
    __tablename__ = "normas_versiones_libro"
    __table_args__ = (
        # Solo una versión activa por proyecto.
        Index("uq_libro_activo", "proyecto_id", unique=True, postgresql_where=text("activa"),
              sqlite_where=text("activa")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    contenido: Mapped[dict[str, Any]]
    hash: Mapped[str] = mapped_column(String(64))
    activa: Mapped[bool]
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _a_dominio(r: RegistroVersionDelLibro) -> VersionDelLibro:
    return VersionDelLibro(id=r.id, proyecto_id=r.proyecto_id, version=r.version, contenido=r.contenido,
                           hash=r.hash, activa=r.activa, publicada_en=r.publicada_en,
                           creado_en=r.creado_en, actualizado_en=r.actualizado_en)


class RepositorioDeLibrosSql:
    def __init__(self, sesion: Session, udt: UnidadDeTrabajoSql) -> None:
        self._s, self._udt = sesion, udt

    def agregar(self, libro: VersionDelLibro) -> None:
        self._udt.seguir(libro)

    def activa(self, proyecto_id: uuid.UUID) -> VersionDelLibro | None:
        r = self._s.scalar(select(RegistroVersionDelLibro).where(
            RegistroVersionDelLibro.proyecto_id == proyecto_id, RegistroVersionDelLibro.activa.is_(True)))
        if r is None:
            return None
        libro = _a_dominio(r)
        self._udt.seguir(libro)
        return libro

    def por_hash(self, proyecto_id: uuid.UUID, hash_: str) -> VersionDelLibro | None:
        r = self._s.scalar(select(RegistroVersionDelLibro).where(
            RegistroVersionDelLibro.proyecto_id == proyecto_id, RegistroVersionDelLibro.hash == hash_))
        return None if r is None else _a_dominio(r)

    def listar(self, proyecto_id: uuid.UUID) -> list[VersionDelLibro]:
        q = select(RegistroVersionDelLibro).where(RegistroVersionDelLibro.proyecto_id == proyecto_id)
        return [_a_dominio(r) for r in self._s.scalars(q.order_by(RegistroVersionDelLibro.creado_en))]

    def volcar(self, libro: VersionDelLibro) -> None:
        r = self._s.get(RegistroVersionDelLibro, libro.id) or RegistroVersionDelLibro(id=libro.id)
        r.proyecto_id, r.version, r.contenido, r.hash = libro.proyecto_id, libro.version, libro.contenido, libro.hash
        r.activa, r.publicada_en = libro.activa, libro.publicada_en
        r.creado_en, r.actualizado_en = libro.creado_en, libro.actualizado_en
        self._s.add(r)


class UnidadDeTrabajoNormasSql(UnidadDeTrabajoSql):
    libros: RepositorioDeLibrosSql

    def _al_abrir(self) -> None:
        self.libros = RepositorioDeLibrosSql(self.sesion, self)

    def confirmar(self) -> None:
        # Primero se desactiva la versión anterior para no violar el índice único parcial.
        for agregado in sorted(self._seguidos, key=lambda a: getattr(a, "activa", False)):
            self._guardar(agregado)
            self.sesion.flush()
        super().confirmar()

    def _guardar(self, agregado: Entidad) -> None:
        if isinstance(agregado, VersionDelLibro):
            self.libros.volcar(agregado)

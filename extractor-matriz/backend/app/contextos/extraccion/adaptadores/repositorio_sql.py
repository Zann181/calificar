"""Tabla, repositorio SQL y unidad de trabajo de Extracción."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.compartido.dominio import Entidad, NoEncontrado
from app.compartido.unidad_de_trabajo_sql import UnidadDeTrabajoSql
from app.contextos.extraccion.dominio.anclaje import Ancla
from app.contextos.extraccion.dominio.extraccion import EstadoExtraccion, Extraccion, Hallazgo


class RegistroExtraccion(Base):
    __tablename__ = "extraccion_extracciones"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    articulo_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version_libro_id: Mapped[uuid.UUID]
    estado: Mapped[str] = mapped_column(String(20), index=True)
    estudios_reservados: Mapped[list[Any]]
    salida: Mapped[list[Any]]
    codificacion_ciega: Mapped[list[Any]]
    anclas: Mapped[list[Any]]
    hallazgos: Mapped[list[Any]]
    acuerdo_campos_criticos: Mapped[float | None] = mapped_column(Float)
    iteraciones_validador: Mapped[int] = mapped_column(Integer)
    errores_validador: Mapped[list[Any]]
    avisos_validador: Mapped[list[Any]]
    uso_tokens: Mapped[dict[str, Any]]
    paso_fallido: Mapped[str | None] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _a_dominio(r: RegistroExtraccion) -> Extraccion:
    return Extraccion(
        id=r.id, proyecto_id=r.proyecto_id, articulo_id=r.articulo_id, version_libro_id=r.version_libro_id,
        estado=EstadoExtraccion(r.estado), estudios_reservados=list(r.estudios_reservados), salida=list(r.salida),
        codificacion_ciega=list(r.codificacion_ciega), anclas=[Ancla.desde_dict(a) for a in r.anclas],
        hallazgos=[Hallazgo.desde_dict(h) for h in r.hallazgos], acuerdo_campos_criticos=r.acuerdo_campos_criticos,
        iteraciones_validador=r.iteraciones_validador, errores_validador=list(r.errores_validador),
        avisos_validador=list(r.avisos_validador), uso_tokens=dict(r.uso_tokens), paso_fallido=r.paso_fallido,
        error=r.error, iniciada_en=r.iniciada_en, terminada_en=r.terminada_en, creado_en=r.creado_en,
        actualizado_en=r.actualizado_en,
    )


def _volcar(e: Extraccion, r: RegistroExtraccion) -> None:
    r.id, r.proyecto_id, r.articulo_id, r.version_libro_id = e.id, e.proyecto_id, e.articulo_id, e.version_libro_id
    r.estado, r.estudios_reservados = e.estado.value, list(e.estudios_reservados)
    r.salida, r.codificacion_ciega = e.salida, e.codificacion_ciega
    r.anclas, r.hallazgos = [a.a_dict() for a in e.anclas], [h.a_dict() for h in e.hallazgos]
    r.acuerdo_campos_criticos, r.iteraciones_validador = e.acuerdo_campos_criticos, e.iteraciones_validador
    r.errores_validador, r.avisos_validador = list(e.errores_validador), list(e.avisos_validador)
    r.uso_tokens, r.paso_fallido, r.error = e.uso_tokens, e.paso_fallido, e.error
    r.iniciada_en, r.terminada_en = e.iniciada_en, e.terminada_en
    r.creado_en, r.actualizado_en = e.creado_en, e.actualizado_en


class RepositorioDeExtraccionesSql:
    def __init__(self, sesion: Session, udt: UnidadDeTrabajoSql) -> None:
        self._s, self._udt = sesion, udt

    def agregar(self, extraccion: Extraccion) -> None:
        self._udt.seguir(extraccion)

    def obtener(self, proyecto_id: uuid.UUID, extraccion_id: uuid.UUID) -> Extraccion:
        r = self._s.get(RegistroExtraccion, extraccion_id)
        if r is None or r.proyecto_id != proyecto_id:
            raise NoEncontrado(f"Extracción {extraccion_id} no existe en el proyecto")
        return _a_dominio(r)

    def de_articulo(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> list[Extraccion]:
        q = (select(RegistroExtraccion)
             .where(RegistroExtraccion.proyecto_id == proyecto_id, RegistroExtraccion.articulo_id == articulo_id)
             .order_by(RegistroExtraccion.iniciada_en))
        return [_a_dominio(r) for r in self._s.scalars(q)]

    def volcar(self, e: Extraccion) -> None:
        r = self._s.get(RegistroExtraccion, e.id) or RegistroExtraccion()
        _volcar(e, r)
        self._s.add(r)


class UnidadDeTrabajoExtraccionSql(UnidadDeTrabajoSql):
    extracciones: RepositorioDeExtraccionesSql

    def _al_abrir(self) -> None:
        self.extracciones = RepositorioDeExtraccionesSql(self.sesion, self)

    def _guardar(self, agregado: Entidad) -> None:
        if isinstance(agregado, Extraccion):
            self.extracciones.volcar(agregado)

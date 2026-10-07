"""Tablas, repositorio SQL y unidad de trabajo de Matriz."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, delete, exists, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base, JsonB
from app.compartido.dominio import Entidad, NoEncontrado, ahora
from app.compartido.unidad_de_trabajo_sql import UnidadDeTrabajoSql
from app.contextos.matriz.dominio.fila import (
    CambioDeCelda,
    Celda,
    EstadoRevision,
    Evidencia,
    FilaDeEfecto,
    Inferencia,
    Origen,
    TipoValor,
)
from app.contextos.matriz.puertos import BaseDeMatriz


class RegistroFila(Base):
    __tablename__ = "matriz_filas"
    __table_args__ = (UniqueConstraint("proyecto_id", "estudio", name="uq_fila_estudio"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    estudio: Mapped[int] = mapped_column(Integer)
    documento: Mapped[int] = mapped_column(Integer, index=True)
    articulo_id: Mapped[uuid.UUID | None]
    origen: Mapped[str] = mapped_column(String(10))
    version_libro_id: Mapped[uuid.UUID | None]
    version_desactualizada: Mapped[bool] = mapped_column(default=False)
    aprobada: Mapped[bool] = mapped_column(default=False)
    trazabilidad: Mapped[dict[str, Any]]
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistroCelda(Base):
    __tablename__ = "matriz_celdas"

    fila_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matriz_filas.id", ondelete="CASCADE"), primary_key=True)
    clave: Mapped[str] = mapped_column(String(120), primary_key=True)
    valor: Mapped[Any] = mapped_column(JsonB, nullable=True)
    estado_dato: Mapped[str | None] = mapped_column(String(40))
    tipo_valor: Mapped[str | None] = mapped_column(String(12))
    evidencias: Mapped[list[Any]]
    inferencia: Mapped[dict[str, Any] | None]
    estado_revision: Mapped[str] = mapped_column(String(20), index=True)
    historial: Mapped[list[Any]]


class RegistroSecuencia(Base):
    """Siguiente número de Estudio por proyecto. La reserva atómica (F3) bloquea esta fila."""

    __tablename__ = "matriz_secuencias"
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), primary_key=True)
    siguiente_estudio: Mapped[int] = mapped_column(Integer)


class RegistroBase(Base):
    """Excel importado que sirve de base (formato, notas de encabezado, hojas) para exportar."""

    __tablename__ = "matriz_bases"
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), primary_key=True)
    clave_almacen: Mapped[str] = mapped_column(String(500))
    nombre_archivo: Mapped[str] = mapped_column(String(500))
    huella_sha256: Mapped[str] = mapped_column(String(64))
    hoja: Mapped[str] = mapped_column(String(200))
    importado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _celda_a_dominio(r: RegistroCelda) -> Celda:
    return Celda(
        clave=r.clave, valor=r.valor, estado_dato=r.estado_dato,
        tipo_valor=TipoValor(r.tipo_valor) if r.tipo_valor else None,
        evidencias=[Evidencia(**e) for e in r.evidencias or []],
        inferencia=None if not r.inferencia else Inferencia(
            regla=r.inferencia["regla"], razonamiento=r.inferencia["razonamiento"],
            premisas=tuple(r.inferencia.get("premisas", ()))),
        estado_revision=EstadoRevision(r.estado_revision),
        historial=[CambioDeCelda(autor=h["autor"], fecha=datetime.fromisoformat(h["fecha"]), accion=h["accion"],
                                 valor_anterior=h["valor_anterior"], valor_nuevo=h["valor_nuevo"],
                                 motivo=h.get("motivo")) for h in r.historial or []],
    )


def _volcar_celda(fila_id: uuid.UUID, c: Celda, r: RegistroCelda) -> None:
    r.fila_id, r.clave, r.valor, r.estado_dato = fila_id, c.clave, c.valor, c.estado_dato
    r.tipo_valor = c.tipo_valor.value if c.tipo_valor else None
    r.evidencias = [asdict(e) for e in c.evidencias]
    r.inferencia = None if c.inferencia is None else {
        "regla": c.inferencia.regla, "razonamiento": c.inferencia.razonamiento,
        "premisas": list(c.inferencia.premisas)}
    r.estado_revision = c.estado_revision.value
    r.historial = [{"autor": h.autor, "fecha": h.fecha.isoformat(), "accion": h.accion,
                    "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo, "motivo": h.motivo}
                   for h in c.historial]


class RepositorioDeFilasSql:
    def __init__(self, sesion: Session, udt: UnidadDeTrabajoSql) -> None:
        self._s, self._udt = sesion, udt

    def _armar(self, registros: list[RegistroFila]) -> list[FilaDeEfecto]:
        if not registros:
            return []
        celdas: dict[uuid.UUID, dict[str, Celda]] = {r.id: {} for r in registros}
        for rc in self._s.scalars(select(RegistroCelda).where(RegistroCelda.fila_id.in_(list(celdas)))):
            celdas[rc.fila_id][rc.clave] = _celda_a_dominio(rc)
        filas = []
        for r in registros:
            f = FilaDeEfecto(id=r.id, proyecto_id=r.proyecto_id, estudio=r.estudio, documento=r.documento,
                             articulo_id=r.articulo_id, origen=Origen(r.origen), version_libro_id=r.version_libro_id,
                             version_desactualizada=r.version_desactualizada, aprobada=r.aprobada,
                             celdas=celdas[r.id], trazabilidad=r.trazabilidad or {},
                             creado_en=r.creado_en, actualizado_en=r.actualizado_en)
            self._udt.seguir(f)
            filas.append(f)
        return filas

    def agregar(self, fila: FilaDeEfecto) -> None:
        self._udt.seguir(fila)

    def por_estudio(self, proyecto_id: uuid.UUID, estudio: int) -> FilaDeEfecto:
        r = self._s.scalar(select(RegistroFila).where(RegistroFila.proyecto_id == proyecto_id,
                                                      RegistroFila.estudio == estudio))
        if r is None:
            raise NoEncontrado(f"No existe el Estudio {estudio}")
        return self._armar([r])[0]

    def todas(self, proyecto_id: uuid.UUID) -> list[FilaDeEfecto]:
        q = select(RegistroFila).where(RegistroFila.proyecto_id == proyecto_id).order_by(RegistroFila.estudio)
        return self._armar(list(self._s.scalars(q)))

    def pagina(self, proyecto_id: uuid.UUID, *, desde: int, cuantas: int,
               documento: int | None = None) -> tuple[list[FilaDeEfecto], int]:
        filtro = [RegistroFila.proyecto_id == proyecto_id]
        if documento is not None:
            filtro.append(RegistroFila.documento == documento)
        total = self._s.scalar(select(func.count()).select_from(RegistroFila).where(*filtro)) or 0
        q = select(RegistroFila).where(*filtro).order_by(RegistroFila.estudio).offset(desde).limit(cuantas)
        return self._armar(list(self._s.scalars(q))), total

    def cuantas(self, proyecto_id: uuid.UUID) -> int:
        return self._s.scalar(select(func.count()).select_from(RegistroFila).where(
            RegistroFila.proyecto_id == proyecto_id)) or 0

    def hay_extraidas(self, proyecto_id: uuid.UUID) -> bool:
        return bool(self._s.scalar(select(exists().where(RegistroFila.proyecto_id == proyecto_id,
                                                         RegistroFila.origen == Origen.EXTRAIDA.value))))

    def borrar_heredadas(self, proyecto_id: uuid.UUID) -> int:
        ids = list(self._s.scalars(select(RegistroFila.id).where(RegistroFila.proyecto_id == proyecto_id,
                                                                 RegistroFila.origen == Origen.HEREDADA.value)))
        if ids:
            self._s.execute(delete(RegistroCelda).where(RegistroCelda.fila_id.in_(ids)))
            self._s.execute(delete(RegistroFila).where(RegistroFila.id.in_(ids)))
            self._s.flush()
        return len(ids)

    def quitar(self, proyecto_id: uuid.UUID, estudio: int) -> bool:
        fila_id = self._s.scalar(select(RegistroFila.id).where(RegistroFila.proyecto_id == proyecto_id,
                                                               RegistroFila.estudio == estudio))
        if fila_id is None:
            return False
        self._s.execute(delete(RegistroCelda).where(RegistroCelda.fila_id == fila_id))
        self._s.execute(delete(RegistroFila).where(RegistroFila.id == fila_id))
        self._s.flush()
        return True

    def ajustar_secuencia(self, proyecto_id: uuid.UUID, siguiente: int) -> None:
        r = self._s.get(RegistroSecuencia, proyecto_id)
        if r is None:
            self._s.add(RegistroSecuencia(proyecto_id=proyecto_id, siguiente_estudio=siguiente))
        else:
            r.siguiente_estudio = max(r.siguiente_estudio, siguiente)

    def siguiente_estudio(self, proyecto_id: uuid.UUID) -> int:
        r = self._s.get(RegistroSecuencia, proyecto_id)
        mayor = self._s.scalar(select(func.max(RegistroFila.estudio)).where(RegistroFila.proyecto_id == proyecto_id))
        return max(r.siguiente_estudio if r else 1, (mayor or 0) + 1)

    def guardar_base(self, proyecto_id: uuid.UUID, base: BaseDeMatriz) -> None:
        r = self._s.get(RegistroBase, proyecto_id) or RegistroBase(proyecto_id=proyecto_id)
        r.clave_almacen, r.nombre_archivo, r.huella_sha256, r.hoja = (
            base.clave_almacen, base.nombre_archivo, base.huella_sha256, base.hoja)
        r.importado_en = ahora()
        self._s.add(r)

    def base(self, proyecto_id: uuid.UUID) -> BaseDeMatriz | None:
        r = self._s.get(RegistroBase, proyecto_id)
        return None if r is None else BaseDeMatriz(clave_almacen=r.clave_almacen, nombre_archivo=r.nombre_archivo,
                                                   huella_sha256=r.huella_sha256, hoja=r.hoja)

    def volcar(self, f: FilaDeEfecto) -> None:
        r = self._s.get(RegistroFila, f.id)
        if r is None:
            r = RegistroFila(id=f.id)
            self._s.add(r)
        r.proyecto_id, r.estudio, r.documento, r.articulo_id = f.proyecto_id, f.estudio, f.documento, f.articulo_id
        r.origen, r.version_libro_id = f.origen.value, f.version_libro_id
        r.version_desactualizada, r.aprobada = f.version_desactualizada, f.aprobada
        r.trazabilidad, r.creado_en, r.actualizado_en = f.trazabilidad, f.creado_en, f.actualizado_en
        self._s.flush()
        existentes = {rc.clave: rc for rc in self._s.scalars(select(RegistroCelda).where(RegistroCelda.fila_id == f.id))}
        for clave, celda in f.celdas.items():
            rc = existentes.get(clave) or RegistroCelda()
            _volcar_celda(f.id, celda, rc)
            self._s.add(rc)


class UnidadDeTrabajoMatrizSql(UnidadDeTrabajoSql):
    filas: RepositorioDeFilasSql

    def _al_abrir(self) -> None:
        self.filas = RepositorioDeFilasSql(self.sesion, self)

    def _guardar(self, agregado: Entidad) -> None:
        if isinstance(agregado, FilaDeEfecto):
            self.filas.volcar(agregado)

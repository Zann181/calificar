"""Tablas de Sincronización: ajustes por proyecto, corridas del agente local y estado de la nube."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.compartido.dominio import ahora
from app.contextos.sincronizacion.dominio.plan import ConflictoDeInstalacion, Opciones
from app.contextos.sincronizacion.puertos import Corrida, Destino


class RegistroDestino(Base):
    """Ajustes de la nube de cada proyecto (sección 7). El token NO está aquí: va al Administrador de credenciales."""

    __tablename__ = "sync_destinos"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), primary_key=True)
    url: Mapped[str] = mapped_column(String(500), server_default="")
    automatico: Mapped[bool] = mapped_column(default=True)
    pausado: Mapped[bool] = mapped_column(default=False)
    agrupar_s: Mapped[int] = mapped_column(Integer, default=5)
    reconciliar_s: Mapped[int] = mapped_column(Integer, default=600)
    opciones: Mapped[dict[str, Any]]
    instalacion_id: Mapped[str] = mapped_column(String(40))
    sede: Mapped[str] = mapped_column(String(10), server_default="local")  # Fase 4: solo «local»
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistroCorrida(Base):
    __tablename__ = "sync_corridas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20))
    sobres: Mapped[int] = mapped_column(Integer, default=0)
    eliminados: Mapped[int] = mapped_column(Integer, default=0)
    archivos: Mapped[int] = mapped_column(Integer, default=0)
    bytes_enviados: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[str] = mapped_column(Text, server_default="")


class RegistroEstadoNube(Base):
    """Una sola fila (id = 1), solo en la nube: contador de revisión e instalación que la sincroniza."""

    __tablename__ = "sync_estado_nube"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    instalacion_id: Mapped[str | None] = mapped_column(String(40))
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistroLector(Base):
    """Solo en la nube: lectores agregados desde el panel local (los fijos están en LECTORES_PERMITIDOS)."""

    __tablename__ = "sync_lectores"

    correo: Mapped[str] = mapped_column(String(200), primary_key=True)
    agregado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _destino(r: RegistroDestino) -> Destino:
    return Destino(proyecto_id=r.proyecto_id, url=r.url, automatico=r.automatico, pausado=r.pausado,
                   agrupar_s=r.agrupar_s, reconciliar_s=r.reconciliar_s, opciones=Opciones.desde_dict(r.opciones),
                   instalacion_id=r.instalacion_id, sede=r.sede)


class RepositorioDeDestinosSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def obtener(self, proyecto_id: uuid.UUID) -> Destino | None:
        with self._fabrica() as s:
            r = s.get(RegistroDestino, proyecto_id)
            return None if r is None else _destino(r)

    def guardar(self, d: Destino) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroDestino, d.proyecto_id)
            if r is None:
                r = RegistroDestino(proyecto_id=d.proyecto_id, creado_en=ahora())
                s.add(r)
            r.url, r.automatico, r.pausado = d.url, d.automatico, d.pausado
            r.agrupar_s, r.reconciliar_s, r.opciones = d.agrupar_s, d.reconciliar_s, d.opciones.a_dict()
            r.instalacion_id, r.sede, r.actualizado_en = d.instalacion_id, d.sede, ahora()
            s.commit()

    def activos(self) -> list[Destino]:
        with self._fabrica() as s:
            return [_destino(r) for r in s.scalars(select(RegistroDestino).where(RegistroDestino.url != ""))]

    def registrar(self, c: Corrida) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroCorrida, c.id) or RegistroCorrida(id=c.id)
            r.proyecto_id, r.iniciada_en, r.terminada_en, r.motivo, r.estado = (
                c.proyecto_id, c.iniciada_en, c.terminada_en, c.motivo[:20], c.estado)
            r.sobres, r.eliminados, r.archivos, r.bytes_enviados = c.sobres, c.eliminados, c.archivos, c.bytes_enviados
            r.revision, r.detalle = c.revision, c.detalle
            s.add(r)
            s.commit()

    def ultimas(self, proyecto_id: uuid.UUID, cuantas: int = 20) -> list[Corrida]:
        with self._fabrica() as s:
            q = (select(RegistroCorrida).where(RegistroCorrida.proyecto_id == proyecto_id)
                 .order_by(RegistroCorrida.iniciada_en.desc()).limit(cuantas))
            return [Corrida(id=r.id, proyecto_id=r.proyecto_id, iniciada_en=r.iniciada_en,
                            terminada_en=r.terminada_en, motivo=r.motivo, estado=r.estado, sobres=r.sobres,
                            eliminados=r.eliminados, archivos=r.archivos, bytes_enviados=r.bytes_enviados,
                            revision=r.revision, detalle=r.detalle) for r in s.scalars(q)]


class EstadoDeNubeSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def revision(self) -> int:
        with self._fabrica() as s:
            r = s.get(RegistroEstadoNube, 1)
            return 0 if r is None else r.revision

    def transaccion(self, trabajo: Callable[[Any], bool], *, instalacion: str | None, tomar_control: bool) -> int:
        with self._fabrica() as s:
            estado = s.get(RegistroEstadoNube, 1)
            if estado is None:
                estado = RegistroEstadoNube(id=1, revision=0)
                s.add(estado)
            if instalacion and estado.instalacion_id and estado.instalacion_id != instalacion and not tomar_control:
                raise ConflictoDeInstalacion(
                    "Otro equipo ya sincroniza esta nube. Si este es el equipo correcto, use «Reenviar todo» "
                    "para tomar el control")
            try:
                cambio = trabajo(s)
                if instalacion and estado.instalacion_id != instalacion:
                    estado.instalacion_id, cambio = instalacion, True
                if cambio:
                    estado.revision += 1
                    estado.actualizado_en = ahora()
                s.commit()
            except Exception:
                s.rollback()
                raise
            return estado.revision


class TransaccionLocalSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def ejecutar(self, trabajo: Callable[[Any], None]) -> None:
        with self._fabrica() as s:
            try:
                trabajo(s)
                s.commit()
            except Exception:
                s.rollback()
                raise


class LectoresSql:
    """Lectores de la nube. Se guarda en memoria `vigencia_s` segundos (el acceso se revisa en cada pedido y no debe
    despertar la base cada vez); cualquier alta o baja renueva la copia al instante."""

    def __init__(self, fabrica: Callable[[], Session], vigencia_s: float = 30.0,
                 reloj: Callable[[], float] | None = None) -> None:
        import time

        self._fabrica, self._vigencia = fabrica, vigencia_s
        self._reloj = reloj or time.monotonic
        self._copia: set[str] = set()
        self._desde = -1e18

    def agregados(self) -> list[tuple[str, datetime]]:
        with self._fabrica() as s:
            return [(r.correo, r.agregado_en) for r in s.scalars(select(RegistroLector).order_by(RegistroLector.correo))]

    def correos(self) -> set[str]:
        if self._reloj() - self._desde > self._vigencia:
            try:
                self._copia = {c for c, _ in self.agregados()}
                self._desde = self._reloj()
            except Exception:  # base dormida o caída: se sigue con la última copia conocida
                pass
        return set(self._copia)

    def agregar(self, correo: str) -> bool:
        with self._fabrica() as s:
            if s.get(RegistroLector, correo) is not None:
                return False
            s.add(RegistroLector(correo=correo, agregado_en=ahora()))
            s.commit()
        self._desde = -1e18
        return True

    def quitar(self, correo: str) -> bool:
        with self._fabrica() as s:
            r = s.get(RegistroLector, correo)
            if r is None:
                return False
            s.delete(r)
            s.commit()
        self._desde = -1e18
        return True

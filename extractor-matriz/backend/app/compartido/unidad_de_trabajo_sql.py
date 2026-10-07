"""Unidad de trabajo sobre SQLAlchemy con outbox transaccional."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from app.compartido.db import RegistroOutbox
from app.compartido.dominio import Entidad, EventoDeDominio


class BusOutbox:
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def publicar(self, evento: EventoDeDominio) -> None:
        self._sesion.add(RegistroOutbox(proyecto_id=evento.proyecto_id, nombre=evento.nombre, datos=evento.datos()))


class UnidadDeTrabajoSql:
    """Base de las unidades de trabajo SQL de cada contexto, que agregan sus repositorios en _al_abrir()."""

    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica
        self.sesion: Session
        self._seguidos: list[Entidad] = []

    def __enter__(self) -> Self:
        self.sesion = self._fabrica()
        self._seguidos = []
        self._al_abrir()
        return self

    def _al_abrir(self) -> None:
        """Los contextos crean aquí sus repositorios sobre self.sesion."""

    def __exit__(self, tipo: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        if tipo is not None:
            self.revertir()
        self.sesion.close()

    def seguir(self, agregado: Entidad) -> None:
        if all(a is not agregado for a in self._seguidos):
            self._seguidos.append(agregado)

    def confirmar(self) -> None:
        bus = BusOutbox(self.sesion)
        for agregado in self._seguidos:
            self._guardar(agregado)
            for evento in agregado.extraer_eventos():
                bus.publicar(evento)
        self.sesion.commit()

    def _guardar(self, agregado: Entidad) -> None:
        """Los contextos vuelcan aquí el estado del agregado a sus tablas."""

    def revertir(self) -> None:
        self.sesion.rollback()
        for agregado in self._seguidos:
            agregado.extraer_eventos()

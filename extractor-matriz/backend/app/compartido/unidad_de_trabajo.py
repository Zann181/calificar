"""Unidad de trabajo (puerto) y su versión en memoria para pruebas.

Al confirmar, los eventos de los agregados seguidos se publican en el BusDeEventos, que en
producción escribe en la outbox dentro de la misma transacción (ver unidad_de_trabajo_sql.py).
Así un evento nunca se pierde ni se publica sin que el cambio se haya guardado.
"""

from __future__ import annotations

from typing import Any, Protocol, Self

from app.compartido.dominio import Entidad, EventoDeDominio


class BusDeEventos(Protocol):
    def publicar(self, evento: EventoDeDominio) -> None: ...  # escribe en la outbox


class UnidadDeTrabajo(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: Any) -> None: ...
    def seguir(self, agregado: Entidad) -> None: ...
    def confirmar(self) -> None: ...
    def revertir(self) -> None: ...


class UnidadDeTrabajoEnMemoria:
    """Para pruebas de aplicación sin base de datos: guarda los eventos publicados en una lista."""

    def __init__(self) -> None:
        self.publicados: list[EventoDeDominio] = []
        self.confirmaciones = 0
        self._seguidos: list[Entidad] = []

    def __enter__(self) -> Self:
        self._seguidos = []
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def seguir(self, agregado: Entidad) -> None:
        if all(a is not agregado for a in self._seguidos):
            self._seguidos.append(agregado)

    def confirmar(self) -> None:
        for agregado in self._seguidos:
            self.publicados.extend(agregado.extraer_eventos())
        self.confirmaciones += 1

    def revertir(self) -> None:
        for agregado in self._seguidos:
            agregado.extraer_eventos()

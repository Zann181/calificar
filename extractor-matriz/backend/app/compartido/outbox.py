"""Despachador de la outbox.

Lee eventos no despachados en orden, los entrega a los manejadores suscritos por nombre y
los marca como despachados. Si un manejador falla, se registra el error y se reintenta en la
siguiente pasada hasta MAX_INTENTOS; después el evento queda con error para revisión.
Con FOR UPDATE SKIP LOCKED varios despachadores pueden correr a la vez sin repetir eventos.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.db import RegistroOutbox
from app.compartido.dominio import ahora

Manejador = Callable[[dict[str, Any]], None]
MAX_INTENTOS = 5
log = logging.getLogger("outbox")


class Despachador:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica
        self._manejadores: dict[str, list[Manejador]] = defaultdict(list)
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self.ultimo_latido: float | None = None  # time.monotonic() de la última pasada del hilo

    def suscribir(self, nombre_evento: str, manejador: Manejador) -> None:
        self._manejadores[nombre_evento].append(manejador)

    def despachar_pendientes(self, lote: int = 50) -> int:
        """Entrega un lote. Devuelve cuántos eventos quedaron despachados."""
        despachados = 0
        with self._fabrica() as sesion:
            consulta = (
                select(RegistroOutbox)
                .where(RegistroOutbox.despachado_en.is_(None), RegistroOutbox.intentos < MAX_INTENTOS)
                .order_by(RegistroOutbox.id)
                .limit(lote)
            )
            if sesion.get_bind().dialect.name == "postgresql":
                consulta = consulta.with_for_update(skip_locked=True)
            for registro in sesion.scalars(consulta).all():
                datos = dict(registro.datos, proyecto_id=str(registro.proyecto_id), _evento=registro.nombre)
                try:
                    for manejador in self._manejadores.get(registro.nombre, []):
                        manejador(datos)
                except Exception as e:  # el error queda en la fila y se reintenta
                    registro.intentos += 1
                    registro.error = f"{type(e).__name__}: {e}"[:2000]
                    log.exception("Manejador falló para %s #%s", registro.nombre, registro.id)
                else:
                    registro.despachado_en = ahora()
                    registro.error = None
                    despachados += 1
                sesion.commit()
        return despachados

    @property
    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar_en_hilo(self, intervalo: float = 1.0, periodica: Callable[[], None] | None = None,
                        cada: float = 15.0) -> None:
        """Corre el despachador dentro de este proceso. `periodica` se ejecuta cada `cada` segundos
        (barrido de lo que quedó pendiente aunque su evento ya se haya despachado)."""
        if self.activo:
            return
        self._parar.clear()

        def bucle() -> None:
            log.info("Despachador de eventos iniciado dentro del servidor")
            ultima = 0.0
            while not self._parar.is_set():
                try:
                    trabajo = self.despachar_pendientes()
                    if periodica is not None and time.monotonic() - ultima >= cada:
                        ultima = time.monotonic()
                        periodica()
                except Exception:
                    log.exception("El despachador falló en una pasada; reintenta en %s s", intervalo)
                    trabajo = 0
                self.ultimo_latido = time.monotonic()
                if trabajo == 0:
                    self._parar.wait(intervalo)

        self._hilo = threading.Thread(target=bucle, name="despachador", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=5)

    def correr(self, intervalo: float = 1.0) -> None:  # pragma: no cover - bucle del proceso
        log.info("Despachador de outbox iniciado")
        while True:
            if self.despachar_pendientes() == 0:
                time.sleep(intervalo)

"""Despachador de la outbox.

Lee eventos no despachados en orden, los entrega a los manejadores suscritos por nombre y
los marca como despachados. Si un manejador falla, se registra el error y se reintenta en la
siguiente pasada hasta MAX_INTENTOS; después el evento queda con error para revisión.
Con FOR UPDATE SKIP LOCKED varios despachadores pueden correr a la vez sin repetir eventos.
"""

from __future__ import annotations

import logging
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

    def correr(self, intervalo: float = 1.0) -> None:  # pragma: no cover - bucle del proceso
        log.info("Despachador de outbox iniciado")
        while True:
            if self.despachar_pendientes() == 0:
                time.sleep(intervalo)

"""Ejecutor en segundo plano de extracciones (cola dentro del proceso, ADR 0003).

Cada pedido corre ExtraerArticulo en un hilo; con `en_paralelo = 1` las demás esperan en cola. El avance de
cada una queda en la base (Extraccion.progreso), así que la interfaz lo ve igual si la lanzó la API o la CLI.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.compartido.dominio import ErrorDeDominio
from app.contextos.extraccion.aplicacion.casos_de_uso import ExtraerArticulo, OpcionesDeExtraccion

log = logging.getLogger("extraccion")


@dataclass(frozen=True)
class PedidoDeExtraccion:
    proyecto_id: uuid.UUID
    articulo_id: uuid.UUID
    nombre: str
    opciones: OpcionesDeExtraccion


@dataclass(frozen=True)
class Pendiente:
    """Pedido sin extracción en marcha todavía."""

    articulo_id: uuid.UUID
    posicion: int
    fase: str
    desde: float  # time.time()


# Fases de un pedido antes de que exista su Extraccion (después, el avance lo da Extraccion.progreso).
EN_COLA, CONVIRTIENDO, ESPERANDO_MINERU, EXTRAYENDO = "en_cola", "convirtiendo", "esperando_mineru", "extrayendo"

# Prepara el artículo antes de extraer (convertirlo con MinerU si hace falta). Llama a `informar(fase)` al cambiar.
Preparar = Callable[[PedidoDeExtraccion, Callable[[str], None]], None]


class EjecutorDeExtracciones:
    def __init__(self, extraer: ExtraerArticulo, en_paralelo: int = 1, preparar: Preparar | None = None) -> None:
        self._extraer, self._preparar = extraer, preparar
        self._pool = ThreadPoolExecutor(max_workers=max(1, en_paralelo), thread_name_prefix="extraccion")
        self._cerrojo = threading.Lock()
        self._pedidos: dict[uuid.UUID, PedidoDeExtraccion] = {}  # en cola o corriendo, en orden de llegada
        self._corriendo: set[uuid.UUID] = set()
        self._fases: dict[uuid.UUID, tuple[str, float]] = {}  # fase y desde cuándo (time.time())

    def encolar(self, pedido: PedidoDeExtraccion) -> int:
        """Devuelve la posición en la cola (0 = empieza ya). Rechaza un artículo que ya está en cola o corriendo."""
        with self._cerrojo:
            if pedido.articulo_id in self._pedidos:
                raise ErrorDeDominio(f"«{pedido.nombre}» ya está en cola o extrayéndose")
            posicion = len(self._pedidos)
            self._pedidos[pedido.articulo_id] = pedido
            self._fases[pedido.articulo_id] = (EN_COLA, time.time())
        log.info("«%s»: extracción encolada (posición %d) · Documento %s", pedido.nombre, posicion + 1,
                 pedido.opciones.documento)
        self._pool.submit(self._correr, pedido)
        return posicion

    def pendientes(self, proyecto_id: uuid.UUID) -> list[Pendiente]:
        """Pedidos que todavía no tienen extracción en marcha (en cola, esperando o convirtiendo), en orden."""
        with self._cerrojo:
            antes = [(a, self._fases[a]) for a, p in self._pedidos.items()
                     if p.proyecto_id == proyecto_id and self._fases[a][0] != EXTRAYENDO]
        return [Pendiente(a, i + 1, fase, desde) for i, (a, (fase, desde)) in enumerate(antes)]

    def _fase(self, articulo_id: uuid.UUID, fase: str) -> None:
        with self._cerrojo:
            if articulo_id in self._pedidos and self._fases.get(articulo_id, ("", 0))[0] != fase:
                self._fases[articulo_id] = (fase, time.time())

    def _correr(self, p: PedidoDeExtraccion) -> None:
        with self._cerrojo:
            self._corriendo.add(p.articulo_id)
        try:
            if self._preparar is not None:
                self._preparar(p, lambda fase: self._fase(p.articulo_id, fase))
            self._fase(p.articulo_id, EXTRAYENDO)
            r = self._extraer.ejecutar(p.proyecto_id, p.articulo_id, p.opciones)
            log.info("«%s»: extracción %s", p.nombre, r.estado)
        except Exception:
            log.exception("«%s»: la extracción no pudo empezar", p.nombre)
        finally:
            with self._cerrojo:
                self._pedidos.pop(p.articulo_id, None)
                self._fases.pop(p.articulo_id, None)
                self._corriendo.discard(p.articulo_id)

    def cerrar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

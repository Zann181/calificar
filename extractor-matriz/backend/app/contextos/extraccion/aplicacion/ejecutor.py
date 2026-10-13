"""Ejecutor en segundo plano de extracciones (cola dentro del proceso, ADR 0003).

Cada pedido pasa por dos etapas con hilos propios: preparar (convertir con MinerU) y extraer con el modelo
(ExtraerArticulo). Mientras el modelo trabaja en un artículo, MinerU ya convierte los que siguen en la cola; con
`en_paralelo = 1` solo una extracción usa el modelo a la vez y las demás esperan ya convertidas. El avance de
cada una queda en la base (Extraccion.progreso), así que la interfaz lo ve igual si la lanzó la API o la CLI.
La cola también se guarda en la base: al abrir la aplicación, reanudar() vuelve a lanzar lo que quedó pendiente
o a medias al cerrarla (una extracción a medias empieza de nuevo: la llamada al modelo no se puede retomar).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from app.compartido.dominio import ErrorDeDominio
from app.contextos.extraccion.aplicacion.casos_de_uso import ExtraerArticulo, OpcionesDeExtraccion
from app.contextos.extraccion.puertos import ColaDeExtracciones, LimiteDeUsoAgotado, PedidoGuardado

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
    reanuda: float | None = None  # solo en pausa por límite de uso: cuándo se reintenta (time.time())


# Fases de un pedido antes de que exista su Extraccion (después, el avance lo da Extraccion.progreso).
EN_COLA, CONVIRTIENDO, ESPERANDO_MINERU, EXTRAYENDO = "en_cola", "convirtiendo", "esperando_mineru", "extrayendo"
PAUSADA = "pausada"  # sin cupo de uso del modelo: espera y se reanuda sola
ESPERA_SIN_FECHA_S = 15 * 60  # si no se sabe cuándo vuelve el cupo, se reintenta cada tanto

# Prepara el artículo antes de extraer (convertirlo con MinerU si hace falta). Llama a `informar(fase)` al cambiar.
Preparar = Callable[[PedidoDeExtraccion, Callable[[str], None]], None]


class EjecutorDeExtracciones:
    def __init__(self, extraer: ExtraerArticulo, en_paralelo: int = 1, preparar: Preparar | None = None,
                 cola: ColaDeExtracciones | None = None) -> None:
        self._extraer, self._preparar, self._cola = extraer, preparar, cola
        self._cerrando = False
        self._pool = ThreadPoolExecutor(max_workers=max(1, en_paralelo), thread_name_prefix="extraccion")
        # Conversión adelantada: 2 hilos para que un PDF esperando a MinerU no frene a los ya convertidos
        # (la conversión en sí se serializa en la composición con su candado).
        self._pool_preparar = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preparacion")
        self._cerrojo = threading.Lock()
        self._pedidos: dict[uuid.UUID, PedidoDeExtraccion] = {}  # en cola o corriendo, en orden de llegada
        self._corriendo: set[uuid.UUID] = set()
        self._fases: dict[uuid.UUID, tuple[str, float]] = {}  # fase y desde cuándo (time.time())
        self._reanudan: dict[uuid.UUID, float] = {}  # pedidos en pausa: cuándo se reintenta
        self._parar = threading.Event()

    def encolar(self, pedido: PedidoDeExtraccion) -> int:
        """Devuelve la posición en la cola (0 = empieza ya). Rechaza un artículo que ya está en cola o corriendo."""
        with self._cerrojo:
            if pedido.articulo_id in self._pedidos:
                raise ErrorDeDominio(f"«{pedido.nombre}» ya está en cola o extrayéndose")
            posicion = len(self._pedidos)
            self._pedidos[pedido.articulo_id] = pedido
            self._fases[pedido.articulo_id] = (EN_COLA, time.time())
        if self._cola is not None:
            self._cola.guardar(PedidoGuardado(pedido.proyecto_id, pedido.articulo_id, pedido.nombre,
                                              asdict(pedido.opciones)))
        log.info("«%s»: extracción encolada (posición %d) · Documento %s", pedido.nombre, posicion + 1,
                 pedido.opciones.documento)
        self._pool_preparar.submit(self._preparar_pedido, pedido)
        return posicion

    def activo(self, articulo_id: uuid.UUID) -> bool:
        """True si el artículo está en cola, convirtiéndose, en pausa o extrayéndose en este proceso."""
        with self._cerrojo:
            return articulo_id in self._pedidos

    def pendientes(self, proyecto_id: uuid.UUID) -> list[Pendiente]:
        """Pedidos que todavía no tienen extracción en marcha (en cola, esperando o convirtiendo), en orden."""
        with self._cerrojo:
            antes = [(a, self._fases[a]) for a, p in self._pedidos.items()
                     if p.proyecto_id == proyecto_id and self._fases[a][0] != EXTRAYENDO]
            reanudan = dict(self._reanudan)
        return [Pendiente(a, i + 1, fase, desde, reanudan.get(a)) for i, (a, (fase, desde)) in enumerate(antes)]

    def _fase(self, articulo_id: uuid.UUID, fase: str) -> None:
        with self._cerrojo:
            if articulo_id in self._pedidos and self._fases.get(articulo_id, ("", 0))[0] != fase:
                self._fases[articulo_id] = (fase, time.time())

    def _preparar_pedido(self, p: PedidoDeExtraccion) -> None:
        """Etapa 1, sin ocupar el modelo: convierte el PDF y lo deja listo en la cola de extracción."""
        try:
            if self._preparar is not None:
                self._preparar(p, lambda fase: self._fase(p.articulo_id, fase))
            self._fase(p.articulo_id, EN_COLA)  # ya convertido: espera su turno con el modelo
            self._pool.submit(self._correr, p)
        except Exception:
            log.exception("«%s»: la extracción no pudo empezar", p.nombre)
            self._soltar(p)

    def _correr(self, p: PedidoDeExtraccion) -> None:
        """Etapa 2: la extracción con el modelo (una a la vez con `en_paralelo = 1`)."""
        with self._cerrojo:
            self._corriendo.add(p.articulo_id)
        try:
            while True:
                self._fase(p.articulo_id, EXTRAYENDO)
                try:
                    r = self._extraer.ejecutar(p.proyecto_id, p.articulo_id, p.opciones)
                except LimiteDeUsoAgotado as e:
                    if not self._pausar(p, e):
                        return  # se está cerrando la aplicación: el pedido sigue guardado y se retoma al abrir
                    continue
                break
            log.info("«%s»: extracción %s", p.nombre, r.estado)
        except Exception:
            log.exception("«%s»: la extracción no pudo empezar", p.nombre)
        finally:
            self._soltar(p)

    def _pausar(self, p: PedidoDeExtraccion, e: LimiteDeUsoAgotado) -> bool:
        """Espera a que vuelva el cupo de uso (no es un error). False si la aplicación se cierra antes."""
        espera = ESPERA_SIN_FECHA_S if e.restablece is None else max(60.0, e.restablece.timestamp() - time.time() + 30)
        hasta = time.time() + espera
        with self._cerrojo:
            self._fases[p.articulo_id] = (PAUSADA, time.time())
            self._reanudan[p.articulo_id] = hasta
        log.warning("«%s»: en pausa, se agotó el cupo de uso del modelo; se reanuda a las %s", p.nombre,
                    time.strftime("%H:%M", time.localtime(hasta)))
        while time.time() < hasta:
            if self._parar.wait(5):
                return False
        with self._cerrojo:
            self._reanudan.pop(p.articulo_id, None)
        return True

    def _soltar(self, p: PedidoDeExtraccion) -> None:
        with self._cerrojo:
            self._reanudan.pop(p.articulo_id, None)
            self._pedidos.pop(p.articulo_id, None)
            self._fases.pop(p.articulo_id, None)
            self._corriendo.discard(p.articulo_id)
        if self._cola is not None and not self._cerrando:  # cortada al cerrar: se retoma al abrir
            self._cola.quitar(p.articulo_id)

    def reanudar(self, sin_actividad_s: float) -> int:
        """Al abrir la aplicación: cierra las extracciones que quedaron a medias y vuelve a encolar los pedidos
        guardados, en su orden. Devuelve cuántos encoló."""
        if self._cola is None:
            return 0
        guardados = self._cola.pendientes()
        cerradas = self._extraer.cerrar_interrumpidas({g.articulo_id for g in guardados}, sin_actividad_s)
        if cerradas:
            log.warning("%d extracción(es) quedaron a medias al cerrar la aplicación", cerradas)
        encolados = 0
        for g in guardados:
            try:
                self.encolar(PedidoDeExtraccion(g.proyecto_id, g.articulo_id, g.nombre,
                                                OpcionesDeExtraccion(**g.opciones)))
                encolados += 1
            except Exception:
                log.exception("«%s»: no se pudo retomar la extracción pendiente", g.nombre)
                self._cola.quitar(g.articulo_id)
        if encolados:
            log.info("Se retoman %d extracción(es) que quedaron pendientes al cerrar la aplicación", encolados)
        return encolados

    def cerrar(self) -> None:
        self._cerrando = True
        self._parar.set()
        self._pool_preparar.shutdown(wait=False, cancel_futures=True)
        self._pool.shutdown(wait=False, cancel_futures=True)

"""Agente de sincronización: corre las pasadas en segundo plano (ADR 0009, sección 6.2).

Disparadores: eventos de la outbox (agrupados `agrupar_s`), temporizador de reconciliación, arranque y el botón
«Sincronizar ahora». La aplicación local nunca espera al agente: cualquier fallo queda en el estado y se reintenta
con espera creciente.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.contextos.sincronizacion.aplicacion.restaurador import RestauracionRechazada, Restaurador
from app.contextos.sincronizacion.aplicacion.sincronizador import Sincronizador
from app.contextos.sincronizacion.dominio.plan import ErrorDeSincronizacion
from app.contextos.sincronizacion.puertos import Corrida, RepositorioDeDestinos

log = logging.getLogger("sincronizacion")
ESPERA_MINIMA_S = 5.0
ESPERA_MAXIMA_S = 600.0


@dataclass
class EstadoDelAgente:
    estado: str = "sin_configurar"  # sin_configurar | pausado | sincronizado | subiendo | sin_conexion | error
    detalle: str = ""
    ultima_ok: float | None = None  # time.time() de la última pasada correcta
    hechos: int = 0
    total: int = 0
    fase: str = ""
    pendiente: bool = False  # hay un disparador sin atender
    proxima_en: float | None = None
    espera_s: float = ESPERA_MINIMA_S
    revision: int | None = None
    eventos_sin_enviar: int = 0  # cambios locales desde la última pasada correcta («N cambios pendientes»)

    def a_dict(self) -> dict[str, Any]:
        ahora = time.time()
        return {
            "estado": self.estado, "detalle": self.detalle,
            "hace_s": None if self.ultima_ok is None else int(ahora - self.ultima_ok),
            "hechos": self.hechos, "total": self.total, "fase": self.fase, "pendiente": self.pendiente,
            "revision": self.revision,
            "cambios_pendientes": self.eventos_sin_enviar,
        }


@dataclass
class _Pedido:
    motivo: str
    todo: bool = False
    tomar_control: bool = False
    corrida: Corrida | None = None
    listo: threading.Event = field(default_factory=threading.Event)


class AgenteDeSincronizacion:
    def __init__(self, sincronizador: Sincronizador, destinos: RepositorioDeDestinos,
                 reloj: Callable[[], float] = time.monotonic, restaurador: Restaurador | None = None) -> None:
        self._s, self._destinos, self._reloj = sincronizador, destinos, reloj
        self._restaurador = restaurador
        self._restauraciones: dict[uuid.UUID, dict[str, Any]] = {}
        self._estados: dict[uuid.UUID, EstadoDelAgente] = {}
        self._pedidos: dict[uuid.UUID, list[_Pedido]] = {}
        self._desde: dict[uuid.UUID, float] = {}  # cuándo vence la espera de agrupación de cada proyecto
        self._ultima: dict[uuid.UUID, float] = {}  # cuándo corrió por última vez (reconciliación)
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._cerrojo = threading.Lock()

    # -- control ------------------------------------------------------------------------------------------------
    def iniciar(self) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        for d in self._destinos.activos():
            self._pedir(d.proyecto_id, _Pedido("arranque"))
        self._hilo = threading.Thread(target=self._bucle, name="sincronizacion", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        self._despertar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=5)

    @property
    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def notificar(self, proyecto_id: uuid.UUID | None = None) -> None:
        """Un evento cambió datos: se sincroniza tras la espera de agrupación."""
        proyectos = [proyecto_id] if proyecto_id else [d.proyecto_id for d in self._destinos.activos()]
        for pid in proyectos:
            with self._cerrojo:
                self._estados.setdefault(pid, EstadoDelAgente()).eventos_sin_enviar += 1
            self._pedir(pid, _Pedido("evento"))

    def ahora(self, proyecto_id: uuid.UUID, *, todo: bool = False, tomar_control: bool = False,
              esperar: float | None = None) -> Corrida | None:
        """«Sincronizar ahora» o «Reenviar todo»: sin esperar a que se agrupe. Con `esperar` bloquea hasta ese tiempo."""
        p = _Pedido("manual", todo=todo, tomar_control=tomar_control)
        self._pedir(proyecto_id, p, inmediato=True)
        if esperar is not None:
            p.listo.wait(esperar)
        return p.corrida

    def estado(self, proyecto_id: uuid.UUID) -> EstadoDelAgente:
        with self._cerrojo:
            e = self._estados.setdefault(proyecto_id, EstadoDelAgente())
        d = self._destinos.obtener(proyecto_id)
        if d is None or not d.url:
            e.estado, e.detalle = "sin_configurar", "Configure la URL y el token de la nube"
        elif d.pausado:
            e.estado, e.detalle = "pausado", "La sincronización está en pausa"
        elif e.estado in ("sin_configurar", "pausado"):
            e.estado, e.detalle = ("sincronizado" if e.ultima_ok else "subiendo"), ""
        return e

    # -- restauración (Fase 2) ----------------------------------------------------------------------------------
    def plan_de_restauracion(self, proyecto_id: uuid.UUID) -> dict[str, Any]:
        """Qué bajaría «Descargar proyecto desde la nube», sin tocar nada."""
        assert self._restaurador is not None
        _, nube = self._s.conectar(proyecto_id)
        m = nube.manifiesto(proyecto_id)
        p = self._restaurador.planear(nube, proyecto_id, m)
        return {"faltan": len(p.faltan), "distintos": len(p.distintos), "solo_locales": len(p.solo_locales),
                "archivos_faltan": len(p.archivos_faltan), "archivos_distintos": len(p.archivos_distintos),
                "hay_conflictos": p.hay_conflictos, "vacio": p.vacio,
                "ejemplos_distintos": p.distintos[:10], "ejemplos_solo_locales": p.solo_locales[:10]}

    def restaurar(self, proyecto_id: uuid.UUID, *, reemplazar: bool) -> None:
        """Baja el proyecto de la nube en segundo plano. Mientras tanto no se sincroniza hacia la nube."""
        assert self._restaurador is not None
        if self._restauraciones.get(proyecto_id, {}).get("estado") == "restaurando":
            return
        estado: dict[str, Any] = {"estado": "restaurando", "hechos": 0, "total": 0, "fase": "", "detalle": "",
                                  "resultado": None}
        self._restauraciones[proyecto_id] = estado
        _, nube = self._s.conectar(proyecto_id)

        def progreso(fase: str, hechos: int, total: int) -> None:
            estado.update(fase=fase, hechos=hechos, total=total)

        def correr() -> None:
            try:
                assert self._restaurador is not None
                m = nube.manifiesto(proyecto_id)
                r = self._restaurador.ejecutar(nube, proyecto_id, m, reemplazar=reemplazar, progreso=progreso)
                estado.update(estado="ok", resultado={
                    "agregados": r.agregados, "archivos": r.archivos, "bytes": r.bytes_bajados,
                    "reemplazados": r.reemplazados, "solo_locales": len(r.solo_locales)})
            except (RestauracionRechazada, ErrorDeSincronizacion) as e:
                estado.update(estado="error", detalle=str(e))
            except Exception as e:  # una restauración que falla nunca tumba la aplicación
                log.exception("La restauración falló")
                estado.update(estado="error", detalle=f"{type(e).__name__}: {e}")

        threading.Thread(target=correr, name="restauracion", daemon=True).start()

    def estado_de_restauracion(self, proyecto_id: uuid.UUID) -> dict[str, Any]:
        return dict(self._restauraciones.get(proyecto_id, {"estado": "ninguna", "hechos": 0, "total": 0, "detalle": "",
                                                           "fase": "", "resultado": None}))

    # -- interior -------------------------------------------------------------------------------------------------
    def _pedir(self, proyecto_id: uuid.UUID, pedido: _Pedido, inmediato: bool = False) -> None:
        d = self._destinos.obtener(proyecto_id)
        with self._cerrojo:
            self._pedidos.setdefault(proyecto_id, []).append(pedido)
            self._estados.setdefault(proyecto_id, EstadoDelAgente()).pendiente = True
            espera = 0.0 if inmediato else float(d.agrupar_s if d else ESPERA_MINIMA_S)
            ya = self._desde.get(proyecto_id)
            self._desde[proyecto_id] = min(ya, self._reloj() + espera) if ya else self._reloj() + espera
        self._despertar.set()

    def _bucle(self) -> None:
        log.info("Agente de sincronización iniciado")
        while not self._parar.is_set():
            try:
                self._una_vuelta()
            except Exception:
                log.exception("El agente de sincronización falló en una vuelta")
            self._despertar.wait(1.0)
            self._despertar.clear()

    def _una_vuelta(self) -> None:
        ahora = self._reloj()
        for d in self._destinos.activos():
            pid = d.proyecto_id
            with self._cerrojo:
                vence = self._desde.get(pid)
                pedidos = self._pedidos.get(pid, [])
            if self._restauraciones.get(pid, {}).get("estado") == "restaurando":
                continue  # no se sube nada mientras se baja
            manual = any(p.motivo == "manual" for p in pedidos)
            if d.pausado and not manual:
                continue
            if not pedidos and d.automatico and ahora - self._ultima.get(pid, -1e18) >= d.reconciliar_s:
                self._pedir(pid, _Pedido("temporizador"), inmediato=True)
                continue
            if not pedidos or vence is None or ahora < vence:
                continue
            with self._cerrojo:
                lote = self._pedidos.pop(pid, [])
                self._desde.pop(pid, None)
            self._correr(pid, lote)

    def _correr(self, pid: uuid.UUID, lote: list[_Pedido]) -> None:
        e = self._estados.setdefault(pid, EstadoDelAgente())
        motivo = "manual" if any(p.motivo == "manual" for p in lote) else lote[0].motivo
        e.estado, e.pendiente, e.hechos, e.total = "subiendo", False, 0, 0

        def progreso(fase: str, hechos: int, total: int) -> None:
            e.fase, e.hechos, e.total = fase, hechos, total

        c = self._s.pasada(pid, motivo=motivo, tomar_control=any(p.tomar_control for p in lote),
                           todo=any(p.todo for p in lote), progreso=progreso)
        self._ultima[pid] = self._reloj()
        e.fase = ""
        if c.estado == "ok":
            e.estado, e.detalle, e.ultima_ok, e.espera_s = "sincronizado", "", time.time(), ESPERA_MINIMA_S
            e.revision, e.eventos_sin_enviar = c.revision, 0
        else:
            e.estado, e.detalle = c.estado, c.detalle
            if c.estado != "error" or "verificación" in c.detalle:
                # Espera creciente; el siguiente intento es un pedido más con su propia espera.
                self._pedir_con_espera(pid, e.espera_s)
                e.espera_s = min(e.espera_s * 2, ESPERA_MAXIMA_S)
        for p in lote:
            p.corrida = c
            p.listo.set()

    def _pedir_con_espera(self, pid: uuid.UUID, espera: float) -> None:
        with self._cerrojo:
            self._pedidos.setdefault(pid, []).append(_Pedido("reintento"))
            self._desde[pid] = self._reloj() + espera

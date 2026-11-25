"""Eventos del servidor (SSE) de la nube (ADR 0009, Fase 2): el visor se entera de una revisión nueva al instante.

El visor ya sabe sondear /revision cada 15 s; esto lo reemplaza mientras la conexión viva, sin consultar la base en
cada vuelta (la nube gratuita de Neon se suspende en reposo). Un solo proceso: el aviso viaja en memoria, del lote que
se acaba de aplicar a cada conexión abierta. Un latido cada 15 s evita que el proxy cierre una conexión ociosa.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

LATIDO_S = 15.0


class Difusor:
    """Reparte el número de revisión nuevo a todas las conexiones abiertas. `publicar` se llama desde cualquier hilo."""

    def __init__(self) -> None:
        self._suscriptores: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[int]]] = []
        self._cerrojo = threading.Lock()

    @property
    def conexiones(self) -> int:
        with self._cerrojo:
            return len(self._suscriptores)

    def suscribir(self) -> asyncio.Queue[int]:
        cola: asyncio.Queue[int] = asyncio.Queue(maxsize=1)  # solo importa la revisión más reciente
        with self._cerrojo:
            self._suscriptores.append((asyncio.get_running_loop(), cola))
        return cola

    def desuscribir(self, cola: asyncio.Queue[int]) -> None:
        with self._cerrojo:
            self._suscriptores = [(lp, c) for lp, c in self._suscriptores if c is not cola]

    def publicar(self, revision: int) -> None:
        with self._cerrojo:
            destinos = list(self._suscriptores)
        for lazo, cola in destinos:
            try:
                lazo.call_soon_threadsafe(self._poner, cola, revision)
            except RuntimeError:  # el lazo de esa conexión ya cerró
                self.desuscribir(cola)

    @staticmethod
    def _poner(cola: asyncio.Queue[int], revision: int) -> None:
        if cola.full():
            cola.get_nowait()
        cola.put_nowait(revision)


def evento(revision: int) -> str:
    return f"event: revision\ndata: {json.dumps({'revision': revision})}\n\n"


async def flujo(difusor: Difusor, revision_actual: Callable[[], Awaitable[int]],
                desconectado: Callable[[], Awaitable[bool]], latido_s: float = LATIDO_S) -> AsyncIterator[str]:
    cola = difusor.suscribir()
    try:
        yield "retry: 5000\n\n"  # si se corta, el navegador reintenta a los 5 s
        yield evento(await revision_actual())
        while True:
            try:
                revision = await asyncio.wait_for(cola.get(), latido_s)
            except TimeoutError:
                if await desconectado():
                    return
                yield ": latido\n\n"
                continue
            yield evento(revision)
    finally:
        difusor.desuscribir(cola)


def enrutador() -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["modo"])

    @r.get("/eventos")
    async def eventos(request: Request) -> StreamingResponse:
        c = request.app.state.contenedor

        async def actual() -> int:
            revision: int = await run_in_threadpool(c.ingesta.revision)
            return revision

        return StreamingResponse(flujo(c.difusor, actual, request.is_disconnected), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

    return r

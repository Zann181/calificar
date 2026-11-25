"""Aplicación FastAPI: routers, sesión y manejo de errores."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import api_extracciones, estado, eventos_nube, modo_nube
from app.compartido import registro, seguridad
from app.compartido.dominio import ErrorDeDominio, NoEncontrado
from app.config import Settings, settings
from app.contextos.biblioteca import api as api_biblioteca
from app.contextos.exportacion import api as api_exportacion
from app.contextos.matriz import api as api_matriz
from app.contextos.normas import api as api_normas
from app.contextos.sincronizacion import api as api_sincronizacion


def crear_app(ajustes: Settings | None = None, contenedor: Any = None,
              intercambiar_codigo: modo_nube.IntercambiarCodigo | None = None) -> FastAPI:
    ajustes = ajustes or settings()
    registro.instalar(ajustes.registro_ruta)

    @asynccontextmanager
    async def ciclo(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "contenedor", None) is None:
            from app.composicion import construir

            app.state.contenedor = construir(ajustes)
        servidor = logging.getLogger("servidor")
        servidor.info("Servidor listo (modo %s)", ajustes.modo)
        c = app.state.contenedor
        if ajustes.modo == "nube":
            # ADR 0009: réplica de solo lectura. Sin hilos de fondo, sin conversión ni extracción: la API no tiene estado.
            yield
            return
        if ajustes.despachador_en_servidor:
            c.despachador.iniciar_en_hilo(periodica=c.convertir_nuevos if ajustes.convertir_al_cargar else None)
        else:
            servidor.warning("El despachador no corre dentro del servidor: la conversión y las filas de una "
                             "extracción necesitan `cli despachar`")
        try:  # lo que quedó en cola o a medias al cerrar la aplicación sigue solo
            c.ejecutor.reanudar(api_extracciones.SIN_ACTIVIDAD_S)
        except Exception:
            servidor.exception("No se pudieron retomar las extracciones pendientes")
        if ajustes.despachador_en_servidor:
            c.agente.iniciar()  # sincronización con la nube (ADR 0009); sin destino configurado no hace nada
        yield
        c.agente.detener()
        c.ejecutor.cerrar()
        c.despachador.detener()

    app = FastAPI(title="Extractor de matriz felicidad y desempeño", version="0.1.0", lifespan=ciclo)
    app.state.contenedor = contenedor
    app.state.registro_ruta = ajustes.registro_ruta
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in ajustes.cors_origenes.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(NoEncontrado)
    async def _no_encontrado(_: Request, e: NoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(e)})

    @app.exception_handler(ErrorDeDominio)
    async def _dominio(_: Request, e: ErrorDeDominio) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(e), "tipo": type(e).__name__})

    @app.exception_handler(LookupError)
    async def _falta(_: Request, e: LookupError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(e)})

    @app.get("/api/v1/salud")
    def salud() -> dict[str, str]:
        return {"estado": "ok"}

    if ajustes.modo == "nube":
        modo_nube.instalar(app, ajustes, intercambiar_codigo)  # falla cerrada si falta configuración de acceso
        app.include_router(api_sincronizacion.nube)
        app.include_router(eventos_nube.enrutador())
    else:
        app.include_router(api_sincronizacion.local)
    app.include_router(modo_nube.enrutador_de_capacidades(ajustes))
    for r in (seguridad.enrutador, api_biblioteca.enrutador, api_normas.enrutador, api_matriz.enrutador,
              api_exportacion.enrutador, registro.enrutador, estado.enrutador,
              api_extracciones.enrutador):
        app.include_router(r)
    # Después de la API: la interfaz compilada responde todo lo que no es /api.
    if (ajustes.interfaz_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=ajustes.interfaz_dir, html=True), name="interfaz")
    return app


app = crear_app()

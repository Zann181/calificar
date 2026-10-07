"""Aplicación FastAPI: routers, sesión y manejo de errores."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.compartido import seguridad
from app.compartido.dominio import ErrorDeDominio, NoEncontrado
from app.config import Settings, settings
from app.contextos.biblioteca import api as api_biblioteca
from app.contextos.exportacion import api as api_exportacion
from app.contextos.matriz import api as api_matriz
from app.contextos.normas import api as api_normas


def crear_app(ajustes: Settings | None = None, contenedor: Any = None) -> FastAPI:
    ajustes = ajustes or settings()

    @asynccontextmanager
    async def ciclo(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "contenedor", None) is None:
            from app.composicion import construir

            app.state.contenedor = construir(ajustes)
        yield

    app = FastAPI(title="Extractor de matriz felicidad y desempeño", version="0.1.0", lifespan=ciclo)
    app.state.contenedor = contenedor
    # Uso local sin login: la API entra sola como este usuario (None = login normal).
    app.state.usuario_sin_login = ajustes.admin_correo.lower() if ajustes.sin_login else None
    app.add_middleware(SessionMiddleware, secret_key=ajustes.sesion_secreto, session_cookie="sesion_extractor",
                       https_only=ajustes.sesion_segura, same_site="lax", max_age=60 * 60 * 12)
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

    for r in (seguridad.enrutador, api_biblioteca.enrutador, api_normas.enrutador, api_matriz.enrutador,
              api_exportacion.enrutador):
        app.include_router(r)
    # Después de la API: la interfaz compilada responde todo lo que no es /api.
    if (ajustes.interfaz_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=ajustes.interfaz_dir, html=True), name="interfaz")
    return app


app = crear_app()

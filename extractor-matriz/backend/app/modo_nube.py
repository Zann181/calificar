"""Reglas de MODO=nube (ADR 0009, secciones 6.3 y 8): sesión de lectores con Google, solo lectura y revisión.

Lo que hace la guardia, en orden, con cada pedido a /api:
  - /api/v1/salud, /api/v1/auth/* y /api/v1/capacidades: públicos (la pantalla de acceso los necesita).
  - /api/v1/sync/*: solo el agente, con su token de servicio (lo verifica la ruta); el token NO lee lo demás.
  - todo lo demás: exige sesión de un lector permitido (401) y solo admite lecturas (405).
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings

COOKIE_SESION = "sesion"
COOKIE_ESTADO = "estado_oauth"
VIGENCIA_SESION_S = 7 * 24 * 3600
LECTURAS = {"GET", "HEAD", "OPTIONS"}
GOOGLE_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
EMISORES = {"https://accounts.google.com", "accounts.google.com"}

IntercambiarCodigo = Callable[[str, str], dict[str, Any]]  # (código, redirect_uri) → claims del id_token


def intercambiar_con_google(ajustes: Settings) -> IntercambiarCodigo:
    def intercambiar(codigo: str, redirect_uri: str) -> dict[str, Any]:
        r = httpx.post(GOOGLE_TOKEN, timeout=20, data={
            "code": codigo, "client_id": ajustes.google_client_id, "client_secret": ajustes.google_client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
        r.raise_for_status()
        # El id_token llega directo de Google por TLS: OpenID permite fiarse de él sin revalidar la firma (§3.1.3.7).
        carga = r.json()["id_token"].split(".")[1]
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        return claims
    return intercambiar


def _serializador(ajustes: Settings, sal: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(ajustes.secreto_sesion, salt=sal)


def lector_de(request: Request, ajustes: Settings) -> str | None:
    """Correo del lector con sesión válida, o None. Se vuelve a comprobar contra la lista en cada pedido."""
    cookie = request.cookies.get(COOKIE_SESION)
    if not cookie:
        return None
    try:
        datos = _serializador(ajustes, "sesion").loads(cookie, max_age=VIGENCIA_SESION_S)
    except BadSignature:
        return None
    correo = str(datos.get("correo", "")).lower()
    if correo in ajustes.lectores:
        return correo
    c = getattr(request.app.state, "contenedor", None)  # lectores agregados desde el panel local (Fase 2)
    return correo if c is not None and correo in c.lectores.correos() else None


def instalar(app: FastAPI, ajustes: Settings, intercambiar: IntercambiarCodigo | None = None) -> None:
    faltan = ajustes.faltantes_de_nube()
    if faltan:
        raise RuntimeError("MODO=nube no arranca sin su configuración de acceso. Faltan: " + ", ".join(faltan)
                           + " (ver .env.nube.example)")
    app.state.intercambiar_codigo = intercambiar or intercambiar_con_google(ajustes)
    seguras = ajustes.url_publica.startswith("https://")

    @app.middleware("http")
    async def guardia(request: Request, siguiente: Callable[[Request], Awaitable[Response]]) -> Response:
        ruta = request.url.path
        request.state.lector = None
        if not ruta.startswith("/api/"):
            return await siguiente(request)  # la interfaz compilada es pública; sus datos no
        publica = (ruta == "/api/v1/salud" or ruta == "/api/v1/capacidades" or ruta.startswith("/api/v1/auth/"))
        if ruta.startswith("/api/v1/sync/") or publica:
            request.state.lector = lector_de(request, ajustes)  # solo informativo: las capacidades lo usan
            return await siguiente(request)
        lector = lector_de(request, ajustes)
        if lector is None:
            return JSONResponse(status_code=401, content={"detail": "Inicie sesión con su cuenta de Google"})
        if request.method not in LECTURAS:
            return JSONResponse(status_code=405, headers={"Allow": "GET, HEAD"}, content={
                "detail": "Esta es una copia de solo lectura: los cambios se hacen en el equipo local"})
        request.state.lector = lector
        return await siguiente(request)

    r = APIRouter(prefix="/api/v1/auth", tags=["acceso"])

    def redirect_uri() -> str:
        return ajustes.url_publica.rstrip("/") + "/api/v1/auth/google/retorno"

    @r.get("/google/entrar")
    def entrar() -> Response:
        estado = secrets.token_urlsafe(24)
        destino = GOOGLE_AUTORIZAR + "?" + urlencode({
            "client_id": ajustes.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
            "scope": "openid email", "state": estado, "prompt": "select_account"})
        resp = RedirectResponse(destino, status_code=302)
        resp.set_cookie(COOKIE_ESTADO, _serializador(ajustes, "estado").dumps(estado), max_age=600, httponly=True,
                        secure=seguras, samesite="lax")
        return resp

    @r.get("/google/retorno")
    def retorno(request: Request, code: str = "", state: str = "", error: str = "") -> Response:
        if error or not code:
            return _pagina(400, "Google no autorizó el acceso", "Vuelva a intentarlo desde la pantalla de acceso.")
        try:
            esperado = _serializador(ajustes, "estado").loads(request.cookies.get(COOKIE_ESTADO, ""), max_age=600)
        except BadSignature:
            return _pagina(400, "El intento de acceso caducó", "Vuelva a intentarlo desde la pantalla de acceso.")
        if not secrets.compare_digest(str(esperado), state):
            return _pagina(400, "El intento de acceso no coincide", "Vuelva a intentarlo desde la pantalla de acceso.")
        try:
            claims = request.app.state.intercambiar_codigo(code, redirect_uri())
        except Exception:
            return _pagina(502, "No se pudo completar el acceso con Google", "Vuelva a intentarlo en un momento.")
        correo = str(claims.get("email", "")).lower()
        valido = (claims.get("aud") == ajustes.google_client_id and claims.get("iss") in EMISORES
                  and claims.get("email_verified") in (True, "true") and float(claims.get("exp", 0)) > time.time())
        contenedor = getattr(request.app.state, "contenedor", None)
        agregados = contenedor.lectores.correos() if contenedor is not None else set()
        if not valido or (correo not in ajustes.lectores and correo not in agregados):
            return _pagina(403, "Este correo no tiene acceso",
                           "La lista de lectores es cerrada. Pida a quien administra el proyecto que agregue su correo.")
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(COOKIE_SESION, _serializador(ajustes, "sesion").dumps({"correo": correo}),
                        max_age=VIGENCIA_SESION_S, httponly=True, secure=seguras, samesite="lax")
        resp.delete_cookie(COOKIE_ESTADO)
        return resp

    @r.get("/yo")
    def yo(request: Request) -> dict[str, str]:
        if request.state.lector is None:
            raise HTTPException(status_code=401, detail="Sin sesión")
        return {"correo": request.state.lector}

    @r.post("/salir")
    def salir() -> Response:
        resp = JSONResponse({"salio": True})
        resp.delete_cookie(COOKIE_SESION)
        return resp

    app.include_router(r)


def _pagina(estado: int, titulo: str, texto: str) -> HTMLResponse:
    return HTMLResponse(status_code=estado, content=(
        f"<!doctype html><meta charset=utf-8><title>{titulo}</title>"
        "<body style='font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem'>"
        f"<h1>{titulo}</h1><p>{texto}</p><p><a href='/'>Volver</a></p>"))


def enrutador_de_capacidades(ajustes: Settings) -> APIRouter:
    """`/capacidades` y `/revision`, en ambos modos: la interfaz decide qué mostrar y cuándo recargar."""
    r = APIRouter(prefix="/api/v1", tags=["modo"])

    @r.get("/capacidades")
    def capacidades(request: Request) -> dict[str, Any]:
        nube = ajustes.modo == "nube"
        lector = getattr(request.state, "lector", None)
        return {"modo": ajustes.modo, "escritura": not nube, "autenticado": (lector is not None) if nube else True,
                "lector": lector, "acceso": "/api/v1/auth/google/entrar" if nube else None}

    @r.get("/revision")
    def revision(request: Request) -> Response:
        n = request.app.state.contenedor.ingesta.revision() if ajustes.modo == "nube" else 0
        etiqueta = f'"{n}"'
        if request.headers.get("if-none-match") == etiqueta:
            return Response(status_code=304, headers={"ETag": etiqueta})
        return JSONResponse({"revision": n}, headers={"ETag": etiqueta, "Cache-Control": "no-cache"})

    return r



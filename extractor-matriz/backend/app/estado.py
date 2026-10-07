"""GET /api/v1/estado: qué piezas están activas (barra superior de la interfaz).

Servidor, despachador de eventos, MinerU (conversión de PDF), la CLI de Claude Code (modelo de lenguaje) y
pdftotext (lo usa el validador).
Cada pieza devuelve `estado` (ok, aviso o error) y un `detalle` legible. La comprobación de Claude ejecuta la
CLI, por eso se guarda un minuto.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request

from app.compartido.seguridad import Usuario, usuario_actual
from app.composicion import Contenedor
from app.config import Settings
from app.contextos.extraccion.adaptadores.claude_cli import entorno_cli
from app.contextos.extraccion.adaptadores.validador import buscar_pdftotext

enrutador = APIRouter(prefix="/api/v1", tags=["estado"])

VIGENCIA_CLAUDE = 60.0
_cerrojo = threading.Lock()
_cache_claude: dict[str, tuple[float, dict[str, Any]]] = {}


def _pieza(id: str, nombre: str, estado: str, detalle: str) -> dict[str, str]:
    return {"id": id, "nombre": nombre, "estado": estado, "detalle": detalle}


def _ejecutar(cmd: list[str], tiempo: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=tiempo, env=entorno_cli())


def comprobar_claude(cli: str) -> dict[str, str]:
    try:
        v = _ejecutar([cli, "--version"])
    except FileNotFoundError:
        return _pieza("claude", "Claude", "error", f"No se encontró la CLI «{cli}». Defina CLAUDE_CLI en .env")
    except subprocess.TimeoutExpired:
        return _pieza("claude", "Claude", "error", "La CLI no respondió a tiempo")
    version = (v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr).strip() else "versión desconocida"
    try:
        a = _ejecutar([cli, "auth", "status"])
        sesion = json.loads(a.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return _pieza("claude", "Claude", "aviso", f"CLI encontrada ({version}); no se pudo comprobar la sesión")
    if sesion.get("loggedIn"):
        return _pieza("claude", "Claude", "ok", f"CLI conectada · {version} · {cli}")
    return _pieza("claude", "Claude", "error", f"CLI encontrada ({version}) pero sin sesión: ejecute `claude` e inicie sesión")


def _claude(cli: str) -> dict[str, str]:
    with _cerrojo:
        t, valor = _cache_claude.get(cli, (0.0, {}))
        if time.monotonic() - t < VIGENCIA_CLAUDE:
            return valor
    nuevo = comprobar_claude(cli)
    with _cerrojo:
        _cache_claude[cli] = (time.monotonic(), nuevo)
    return nuevo


def _puerto_abierto(url: str) -> bool:
    """True si algo escucha en el host y puerto de la URL (aunque no conteste a tiempo)."""
    u = urlparse(url)
    try:
        with socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=1.5):
            return True
    except OSError:
        return False


def _mineru(c: Contenedor, ajustes: Settings) -> dict[str, str]:
    salud = c.mineru()
    if salud is not None:
        version = salud.get("mineru")
        return _pieza("mineru", "MinerU", "ok", f"Activo en {ajustes.mineru_url}" + (f" · versión {version}" if version else ""))
    if _puerto_abierto(ajustes.mineru_url):
        return _pieza("mineru", "MinerU", "aviso", "Ocupado: el puerto acepta conexiones pero /salud no contesta, "
                      "lo normal mientras convierte un PDF (en CPU toma de 11 a 21 s por página)")
    if ajustes.mineru_python.exists():
        return _pieza("mineru", "MinerU", "error", f"Instalado pero apagado: nada escucha en {ajustes.mineru_url}. "
                      "Se arranca con el acceso directo del Extractor")
    return _pieza("mineru", "MinerU", "error", f"No está instalado (falta {ajustes.mineru_python}). "
                  "Sin él los PDF nuevos no se convierten")


def _despachador(c: Contenedor) -> dict[str, str]:
    d = c.despachador
    if not d.activo:
        return _pieza("despachador", "Despachador", "error", "No corre: los PDF no se convierten solos ni las "
                      "extracciones llenan la matriz")
    hace = None if d.ultimo_latido is None else time.monotonic() - d.ultimo_latido
    if hace is not None and hace > 600:  # una conversión larga bloquea el hilo; solo se avisa si es excesivo
        return _pieza("despachador", "Despachador", "aviso", f"Sin latido desde hace {int(hace)} s")
    return _pieza("despachador", "Despachador", "ok", "Activo: convierte PDF nuevos y escribe las filas de cada extracción")


def _pdftotext(ajustes: Settings) -> dict[str, str]:
    ruta = buscar_pdftotext(ajustes.pdftotext)
    if ruta is None:
        return _pieza("pdftotext", "pdftotext", "error", "No se encontró: el validador no puede comprobar las citas "
                      "y toda extracción fallará. Instale Git para Windows o poppler, o defina PDFTOTEXT en .env")
    return _pieza("pdftotext", "pdftotext", "ok", f"Validador listo · {ruta}")


@enrutador.get("/estado")
def estado(request: Request, _: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    c: Contenedor = request.app.state.contenedor
    return {"componentes": [
        _pieza("servidor", "Servidor", "ok", "API en marcha"),
        _despachador(c),
        _mineru(c, c.ajustes),
        _claude(c.ajustes.claude_cli),
        _pdftotext(c.ajustes),
    ]}

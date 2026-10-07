"""Adaptador ClaudeCli del puerto ModeloDeLenguaje (ADR 0002).

Ejecuta `claude -p` con la sesión de Claude Code del equipo, aislado de la configuración personal
(--setting-sources "", --strict-mcp-config) y sin heredar las variables CLAUDE_* ni ANTHROPIC_BASE_URL
del proceso anfitrión. Cada llamada usa una carpeta temporal con el mensaje de sistema y las imágenes
de páginas, que el modelo abre con la herramienta Read (limitada a esa carpeta).

La salida se pide en stream-json: además del resultado trae el evento `rate_limit_event`, con el uso de la cuenta
en la ventana de 5 horas y cuándo se restablece. El último visto queda en LIMITE (lo muestra la cabecera).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.contextos.extraccion.puertos import RespuestaModelo


class ErrorDelModelo(RuntimeError):
    pass


def entorno_cli() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL")}


class LimiteDeCuenta:
    """Último uso de la cuenta informado por la CLI: % usado de la ventana de 5 horas y de 7 días, y su reinicio."""

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._datos: dict[str, Any] | None = None
        self._visto = 0.0  # time.monotonic() del último dato

    def registrar(self, info: dict[str, Any]) -> None:
        ventanas = info.get("unifiedWindows") or {}
        if not ventanas and info.get("rateLimitType"):  # CLI sin unifiedWindows: solo la ventana del evento
            ventanas = {info["rateLimitType"]: {"utilization": info.get("utilization"), "resetsAt": info.get("resetsAt")}}

        def ventana(clave: str) -> dict[str, Any] | None:
            v = ventanas.get(clave)
            if not v or v.get("utilization") is None:
                return None
            reinicio = v.get("resetsAt")
            return {"usado": round(float(v["utilization"]) * 100, 1),
                    "restablece": datetime.fromtimestamp(reinicio, UTC).isoformat() if reinicio else None}

        datos = {"cinco_horas": ventana("five_hour"), "siete_dias": ventana("seven_day"),
                 "bloqueada": info.get("status") not in (None, "allowed", "allowed_warning"),
                 "actualizado": datetime.now(UTC).isoformat()}
        with self._cerrojo:
            self._datos, self._visto = datos, time.monotonic()

    def actual(self) -> dict[str, Any] | None:
        with self._cerrojo:
            return dict(self._datos) if self._datos else None

    def antiguedad(self) -> float:
        """Segundos desde el último dato (infinito si no hay)."""
        with self._cerrojo:
            return time.monotonic() - self._visto if self._datos else float("inf")


LIMITE = LimiteDeCuenta()


def leer_flujo(stdout: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Del stream-json de la CLI: el objeto `result` y el último `rate_limit_info`."""
    resultado, limite = None, None
    for linea in stdout.splitlines():
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            o = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "result":
            resultado = o
        elif o.get("type") == "rate_limit_event" and isinstance(o.get("rate_limit_info"), dict):
            limite = o["rate_limit_info"]
    return resultado, limite


def sondear_limite(cli: str, modelo: str = "claude-haiku-4-5-20251001") -> None:
    """Llamada mínima (una palabra con Haiku) solo para conocer el uso de la cuenta. Actualiza LIMITE."""
    with tempfile.TemporaryDirectory(prefix="extraccion-limite-") as tmp:
        r = subprocess.run([cli, "-p", "--output-format", "stream-json", "--verbose", "--model", modelo,
                            "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
                            "--tools", "", "--max-turns", "1"],
                           input="Responde solo: ok", capture_output=True, text=True, encoding="utf-8", cwd=tmp,
                           env=entorno_cli(), timeout=60)
    _, limite = leer_flujo(r.stdout)
    if limite:
        LIMITE.registrar(limite)


class ClaudeCli:
    def __init__(self, modelos: dict[str, str], cli: str = "claude", *, max_turnos: int = 30,
                 tiempo_max: float = 3600) -> None:
        self._modelos, self._cli, self._turnos, self._tiempo = modelos, cli, max_turnos, tiempo_max

    def completar(self, *, rol: str, sistema: str, mensaje: str,
                  imagenes: dict[str, bytes] | None = None) -> RespuestaModelo:
        modelo = self._modelos[rol]
        with tempfile.TemporaryDirectory(prefix=f"extraccion-{rol}-") as tmp:
            trabajo = Path(tmp)
            archivo_sistema = trabajo / "sistema.txt"
            archivo_sistema.write_text(sistema, encoding="utf-8")
            for nombre, png in (imagenes or {}).items():
                (trabajo / nombre).write_bytes(png)
            cmd = [self._cli, "-p", "--output-format", "stream-json", "--verbose", "--model", modelo,
                   "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
                   "--system-prompt-file", str(archivo_sistema), "--max-turns", str(self._turnos)]
            cmd += (["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(trabajo)] if imagenes
                    else ["--tools", ""])
            inicio = time.perf_counter()
            try:
                r = subprocess.run(cmd, input=mensaje, capture_output=True, text=True, encoding="utf-8",
                                   cwd=trabajo, env=entorno_cli(), timeout=self._tiempo)
            except FileNotFoundError as e:
                raise ErrorDelModelo(f"No se encontró la CLI de Claude ('{self._cli}'); defina CLAUDE_CLI") from e
            segundos = round(time.perf_counter() - inicio, 1)
        datos, limite = leer_flujo(r.stdout)
        if limite:
            LIMITE.registrar(limite)
        if datos is None:
            raise ErrorDelModelo(f"{rol}: la CLI no devolvió resultado: {r.stdout[-300:]} {r.stderr[:300]}")
        if datos.get("is_error"):
            raise ErrorDelModelo(f"{rol}: {datos.get('result')}")
        u = datos.get("usage") or {}
        uso = {"modelo": modelo, "segundos": segundos, "turnos": datos.get("num_turns"),
               "entrada": u.get("input_tokens", 0), "cache_escritura": u.get("cache_creation_input_tokens", 0),
               "cache_lectura": u.get("cache_read_input_tokens", 0), "salida": u.get("output_tokens", 0),
               "costo_usd": datos.get("total_cost_usd", 0),
               "cuenta_5h": (LIMITE.actual() or {}).get("cinco_horas") if limite else None}
        return RespuestaModelo(texto=str(datos.get("result") or ""), uso=uso)

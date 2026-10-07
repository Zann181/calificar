"""Adaptador ClaudeCli del puerto ModeloDeLenguaje (ADR 0002).

Ejecuta `claude -p` con la sesión de Claude Code del equipo, aislado de la configuración personal
(--setting-sources "", --strict-mcp-config) y sin heredar las variables CLAUDE_* ni ANTHROPIC_BASE_URL
del proceso anfitrión. Cada llamada usa una carpeta temporal con el mensaje de sistema y las imágenes
de páginas, que el modelo abre con la herramienta Read (limitada a esa carpeta).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.contextos.extraccion.puertos import RespuestaModelo


class ErrorDelModelo(RuntimeError):
    pass


def entorno_cli() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL")}


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
            cmd = [self._cli, "-p", "--output-format", "json", "--model", modelo,
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
        try:
            datos: dict[str, Any] = json.loads(r.stdout)
        except json.JSONDecodeError as e:
            raise ErrorDelModelo(f"{rol}: la CLI no devolvió JSON: {r.stdout[:300]} {r.stderr[:300]}") from e
        if datos.get("is_error"):
            raise ErrorDelModelo(f"{rol}: {datos.get('result')}")
        u = datos.get("usage") or {}
        uso = {"modelo": modelo, "segundos": segundos, "turnos": datos.get("num_turns"),
               "entrada": u.get("input_tokens", 0), "cache_escritura": u.get("cache_creation_input_tokens", 0),
               "cache_lectura": u.get("cache_read_input_tokens", 0), "salida": u.get("output_tokens", 0),
               "costo_usd": datos.get("total_cost_usd", 0)}
        return RespuestaModelo(texto=str(datos.get("result") or ""), uso=uso)

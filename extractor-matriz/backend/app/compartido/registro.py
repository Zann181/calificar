"""Registro de eventos para la interfaz: qué está pasando y en qué orden.

Un manejador de `logging` agrega cada mensaje como una línea JSON a `datos/registro.jsonl`. Es un archivo,
no memoria, para que lo vean la API y los comandos de la CLI (otro proceso). La interfaz lo consulta con
`GET /api/v1/registro?desde=<posición>`: la respuesta trae solo lo nuevo y la posición siguiente.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.compartido.seguridad import Usuario, usuario_actual

# Loggers que aparecen en la interfaz. Los de uvicorn y SQLAlchemy quedan fuera a propósito: ruido, y
# la propia consulta del registro se vería a sí misma.
ORIGENES = ("biblioteca", "extraccion", "composicion", "outbox", "matriz", "normas", "exportacion", "servidor")
MAX_BYTES = 4_000_000
COLA_AL_ABRIR = 300

_cerrojo = threading.Lock()


class ManejadorDeRegistro(logging.Handler):
    def __init__(self, ruta: Path) -> None:
        super().__init__(level=logging.INFO)
        self.ruta = ruta

    def emit(self, record: logging.LogRecord) -> None:
        try:
            mensaje = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                mensaje += f" · {type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            linea = json.dumps({"t": datetime.now(UTC).isoformat(timespec="milliseconds"), "nivel": record.levelname,
                                "origen": record.name, "mensaje": mensaje[:4000]}, ensure_ascii=False)
            with _cerrojo:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                if self.ruta.exists() and self.ruta.stat().st_size > MAX_BYTES:
                    self.ruta.replace(self.ruta.with_suffix(".jsonl.1"))
                with self.ruta.open("a", encoding="utf-8") as f:
                    f.write(linea + "\n")
        except Exception:  # el registro nunca debe tumbar el trabajo
            self.handleError(record)


def instalar(ruta: Path) -> None:
    """Conecta el manejador a los loggers de la aplicación (idempotente)."""
    for nombre in ORIGENES:
        lg = logging.getLogger(nombre)
        if any(isinstance(h, ManejadorDeRegistro) and h.ruta == ruta for h in lg.handlers):
            continue
        lg.setLevel(logging.INFO)
        lg.addHandler(ManejadorDeRegistro(ruta))


def leer(ruta: Path, desde: int | None, limite: int = 500) -> tuple[list[dict[str, Any]], int]:
    """Eventos escritos después de `desde` (posición en bytes) y la posición siguiente.

    Sin `desde` devuelve la cola del archivo. Si el archivo rotó (es más corto que `desde`), empieza de cero.
    """
    if not ruta.exists():
        return [], 0
    with ruta.open("rb") as f:
        f.seek(0, 2)
        fin = f.tell()
        if desde is None:
            f.seek(max(0, fin - 120_000))
            datos = f.read()
            if fin > 120_000:
                datos = datos.split(b"\n", 1)[-1]  # descarta la línea partida
            inicio = fin - len(datos)
        else:
            inicio = desde if desde <= fin else 0
            f.seek(inicio)
            datos = f.read(1_000_000)
    ultimo = datos.rfind(b"\n")
    if ultimo < 0:
        return [], inicio
    datos = datos[: ultimo + 1]
    eventos: list[dict[str, Any]] = []
    posicion = inicio
    for crudo in datos.splitlines(keepends=True):
        posicion += len(crudo)
        try:
            e = json.loads(crudo)
        except json.JSONDecodeError:
            continue
        e["id"] = posicion
        eventos.append(e)
    if desde is None:
        eventos = eventos[-COLA_AL_ABRIR:]
    elif len(eventos) > limite:
        eventos = eventos[:limite]
        posicion = eventos[-1]["id"]
    return eventos, posicion


enrutador = APIRouter(prefix="/api/v1", tags=["registro"])


@enrutador.get("/registro")
def registro(request: Request, desde: int | None = Query(None, ge=0), limite: int = Query(500, ge=1, le=2000),
             _: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    eventos, siguiente = leer(request.app.state.registro_ruta, desde, limite)
    return {"eventos": eventos, "siguiente": siguiente}

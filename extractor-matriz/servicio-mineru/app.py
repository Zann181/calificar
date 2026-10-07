"""Servicio MinerU: convierte un PDF con el backend pipeline y devuelve la salida cruda en zip.

POST /convertir  (multipart, campo "archivo") -> application/zip con
    content_list.json, middle.json y images/
GET  /salud      -> versión de MinerU y backend en uso

La normalización a DocumentoEstructurado NO se hace aquí: la hace el adaptador MineruHttp
del backend, para que el servicio se pueda reemplazar sin tocar el dominio.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

BACKEND = "pipeline"
IDIOMA = os.environ.get("MINERU_IDIOMA", "en")
METODO = os.environ.get("MINERU_METODO", "auto")

app = FastAPI(title="servicio-mineru")
# MinerU carga modelos grandes en memoria; una conversión a la vez evita quedarse sin RAM.
_candado = threading.Lock()


def _version() -> str:
    try:
        from mineru.version import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "desconocida"


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"mineru": _version(), "backend": BACKEND, "metodo": METODO,
            "dispositivo": os.environ.get("MINERU_DEVICE_MODE", "auto")}


def convertir_bytes(pdf: bytes, nombre: str = "articulo") -> tuple[bytes, float]:
    """Devuelve (zip, segundos). Separada del endpoint para usarla desde herramientas de F0."""
    from mineru.cli.common import do_parse

    base = "articulo"
    with _candado, tempfile.TemporaryDirectory() as tmp:
        inicio = time.perf_counter()
        do_parse(
            tmp, [base], [pdf], [IDIOMA], backend=BACKEND, parse_method=METODO,
            f_draw_layout_bbox=False, f_draw_span_bbox=False, f_dump_md=True,
            f_dump_middle_json=True, f_dump_model_output=False, f_dump_orig_pdf=False,
            f_dump_content_list=True,
        )
        segundos = time.perf_counter() - inicio
        salida = next(Path(tmp, base).iterdir())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for ruta in salida.rglob("*"):
                if not ruta.is_file():
                    continue
                rel = ruta.relative_to(salida).as_posix()
                if rel.endswith("_content_list.json"):
                    rel = "content_list.json"
                elif rel.endswith("_content_list_v2.json"):
                    rel = "content_list_v2.json"
                elif rel.endswith("_middle.json"):
                    rel = "middle.json"
                elif rel.endswith(".md"):
                    rel = "articulo.md"
                z.write(ruta, rel)
            z.writestr("servicio.json", json.dumps({"mineru": _version(), "backend": BACKEND, "metodo": METODO,
                                                    "segundos": round(segundos, 2), "nombre": nombre},
                                                   ensure_ascii=False))
        return buffer.getvalue(), segundos


@app.post("/convertir")
async def convertir(archivo: UploadFile = File(...)) -> Response:
    datos = await archivo.read()
    if not datos.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="El archivo no es un PDF")
    try:
        zip_bytes, segundos = convertir_bytes(datos, archivo.filename or "articulo.pdf")
    except Exception as e:  # la causa exacta llega al adaptador, que la guarda en DetalleError
        raise HTTPException(status_code=500, detail=f"MinerU falló: {type(e).__name__}: {e}") from e
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"X-Segundos": f"{segundos:.2f}"})

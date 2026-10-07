"""Ejecuta validar_extraccion.py SIN modificarlo, forzando UTF-8 en pdftotext (ADR 0001, hallazgo H4).

En Windows, pdftotext (xpdf 4.00) escribe Latin-1 por defecto y Python decodifica la salida con cp1252:
"–" o "−" se pierden y V23 rechaza citas literales correctas. Mismo arreglo que herramientas/validar_utf8.py.

Uso: python _validar_utf8.py validar_extraccion.py salida.json libro.json [articulo.pdf]
"""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

_run_original = subprocess.run


def _run_utf8(args: Any, *a: Any, **kw: Any) -> Any:
    if isinstance(args, list) and args and Path(str(args[0])).stem == "pdftotext":
        args = [args[0], "-enc", "UTF-8", *args[1:]]
        if kw.get("text"):
            kw["encoding"] = "utf-8"
    return _run_original(args, *a, **kw)


if __name__ == "__main__":
    subprocess.run = _run_utf8
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    validador = sys.argv[1]
    sys.argv = [validador, *sys.argv[2:]]
    runpy.run_path(validador, run_name="__main__")

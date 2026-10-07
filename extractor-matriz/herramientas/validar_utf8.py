"""Ejecuta recursos/validar_extraccion.py SIN modificarlo, forzando UTF-8 en pdftotext.

En Windows, pdftotext (xpdf 4.00) escribe Latin-1 por defecto y Python decodifica la salida
con cp1252: caracteres como "–" o "−" se pierden y V23 rechaza citas literales correctas.
Este envoltorio agrega `-enc UTF-8` a la llamada y decodifica en UTF-8 (ADR 0001, hallazgo H4).

Uso: python herramientas/validar_utf8.py salida.json libro.json articulo.pdf
"""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

VALIDADOR = Path(__file__).resolve().parents[1] / "recursos" / "validar_extraccion.py"
_run_original = subprocess.run


def _run_utf8(args, *a, **kw):  # type: ignore[no-untyped-def]
    if isinstance(args, list) and args and Path(str(args[0])).stem == "pdftotext":
        args = [args[0], "-enc", "UTF-8", *args[1:]]
        if kw.get("text"):
            kw["encoding"] = "utf-8"
    return _run_original(args, *a, **kw)


if __name__ == "__main__":
    subprocess.run = _run_utf8  # type: ignore[assignment]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.argv = [str(VALIDADOR), *sys.argv[1:]]
    runpy.run_path(str(VALIDADOR), run_name="__main__")

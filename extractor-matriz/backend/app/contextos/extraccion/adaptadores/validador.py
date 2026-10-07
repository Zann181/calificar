"""ScriptValidador: ejecuta recursos/validar_extraccion.py tal cual, con archivos temporales (sección 6).

- Clasifica las líneas "ERROR" y "AVISO". Si el esquema falla, el script imprime los errores sin prefijo
  y termina; esas líneas cuentan como errores.
- Si el esquema del libro no admite bloque_id en la evidencia (libro 2.1), lo quita de una copia antes
  de validar. El libro 2.2 lo admite (H5) y la copia no cambia.
- pdftotext en UTF-8 (H4), mediante _validar_utf8.py.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.contextos.extraccion.puertos import ResultadoValidacion

ENVOLTORIO = Path(__file__).with_name("_validar_utf8.py")
_FIN_ESQUEMA = re.compile(r"^\d+ errores de esquema")


class ErrorDelValidador(RuntimeError):
    pass


def admite_bloque_id(libro: dict[str, Any]) -> bool:
    texto = json.dumps((libro.get("esquema_de_salida") or {}).get("json_schema") or {})
    return '"bloque_id"' in texto


def sin_bloque_id(salida: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copia = copy.deepcopy(salida)
    for item in copia:
        for evidencias in ((item.get("trazabilidad") or {}).get("evidencia") or {}).values():
            for e in evidencias or []:
                if isinstance(e, dict):
                    e.pop("bloque_id", None)
    return copia


def clasificar(texto: str) -> ResultadoValidacion:
    lineas = [ln.rstrip() for ln in texto.splitlines()]
    errores = [ln[len("ERROR"):].strip() for ln in lineas if ln.startswith("ERROR")]
    avisos = [ln[len("AVISO"):].strip() for ln in lineas if ln.startswith("AVISO")]
    fin = next((i for i, ln in enumerate(lineas) if _FIN_ESQUEMA.match(ln.strip())), None)
    if fin is not None:
        errores += [ln.strip() for ln in lineas[:fin] if ln.strip()]
    return ResultadoValidacion(errores=errores, avisos=avisos)


def buscar_pdftotext(configurado: str = "") -> Path | None:
    """El validador llama a `pdftotext` por nombre. Arrancado desde el acceso directo, el PATH no incluye
    la carpeta de Git para Windows, que es donde suele estar; por eso se busca también ahí."""
    if configurado:
        ruta = shutil.which(configurado)
        return Path(ruta) if ruta else None
    if ruta := shutil.which("pdftotext"):
        return Path(ruta)
    git = shutil.which("git")
    candidatos = [Path(git).parents[1] / "mingw64" / "bin"] if git else []
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMW6432"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidatos += [Path(base) / "Git" / "mingw64" / "bin", Path(base) / "Programs" / "Git" / "mingw64" / "bin"]
    return next((c / "pdftotext.exe" for c in candidatos if (c / "pdftotext.exe").is_file()), None)


class ScriptValidador:
    def __init__(self, script: Path, tiempo_max: float = 300, pdftotext: str = "") -> None:
        self._script, self._tiempo, self._pdftotext = script, tiempo_max, pdftotext

    def comprobar(self) -> None:
        self._entorno()

    def _entorno(self) -> dict[str, str]:
        """PATH con la carpeta de pdftotext al frente, para que el script lo encuentre por nombre."""
        ruta = buscar_pdftotext(self._pdftotext)
        if ruta is None:
            raise ErrorDelValidador("No se encontró pdftotext, que el validador necesita para comparar las citas "
                                    "con el PDF (V23). Instale Git para Windows o poppler, o defina PDFTOTEXT en .env")
        entorno = dict(os.environ)
        entorno["PATH"] = str(ruta.parent) + os.pathsep + entorno.get("PATH", "")
        return entorno

    def validar(self, salida: list[dict[str, Any]], libro: dict[str, Any], pdf: bytes | None) -> ResultadoValidacion:
        entorno = self._entorno() if pdf is not None else None
        a_validar = salida if admite_bloque_id(libro) else sin_bloque_id(salida)
        with tempfile.TemporaryDirectory(prefix="validar-") as tmp:
            d = Path(tmp)
            (d / "salida.json").write_text(json.dumps(a_validar, ensure_ascii=False), encoding="utf-8")
            (d / "libro.json").write_text(json.dumps(libro, ensure_ascii=False), encoding="utf-8")
            args = [sys.executable, str(ENVOLTORIO), str(self._script), str(d / "salida.json"), str(d / "libro.json")]
            if pdf is not None:
                (d / "articulo.pdf").write_bytes(pdf)
                args.append(str(d / "articulo.pdf"))
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=self._tiempo,
                               env=entorno)
        resultado = clasificar(r.stdout)
        if r.returncode not in (0, 1) or (r.returncode == 1 and not resultado.errores):
            raise ErrorDelValidador(f"El validador terminó con código {r.returncode}: {r.stderr[-1000:]}")
        return resultado

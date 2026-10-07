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
import re
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


class ScriptValidador:
    def __init__(self, script: Path, tiempo_max: float = 300) -> None:
        self._script, self._tiempo = script, tiempo_max

    def validar(self, salida: list[dict[str, Any]], libro: dict[str, Any], pdf: bytes | None) -> ResultadoValidacion:
        a_validar = salida if admite_bloque_id(libro) else sin_bloque_id(salida)
        with tempfile.TemporaryDirectory(prefix="validar-") as tmp:
            d = Path(tmp)
            (d / "salida.json").write_text(json.dumps(a_validar, ensure_ascii=False), encoding="utf-8")
            (d / "libro.json").write_text(json.dumps(libro, ensure_ascii=False), encoding="utf-8")
            args = [sys.executable, str(ENVOLTORIO), str(self._script), str(d / "salida.json"), str(d / "libro.json")]
            if pdf is not None:
                (d / "articulo.pdf").write_bytes(pdf)
                args.append(str(d / "articulo.pdf"))
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=self._tiempo)
        resultado = clasificar(r.stdout)
        if r.returncode not in (0, 1) or (r.returncode == 1 and not resultado.errores):
            raise ErrorDelValidador(f"El validador terminó con código {r.returncode}: {r.stderr[-1000:]}")
        return resultado

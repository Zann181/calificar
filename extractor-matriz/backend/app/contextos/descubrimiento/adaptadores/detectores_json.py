"""Carga de los datos de detección desde `recursos/` (sin lógica: la clasificación y los detectores son datos)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.contextos.descubrimiento.dominio.detectores import ConfigDeDetectores, Nivel


def _json(ruta: Path) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(ruta.read_text(encoding="utf-8"))
    return datos


def cargar_config(recursos: Path) -> ConfigDeDetectores:
    clasif = _json(recursos / "detectabilidad_columnas.json")["columnas"]
    det = _json(recursos / "detectores_columnas.json")
    paises = _json(recursos / "paises_iso.json")["paises"]
    return ConfigDeDetectores(
        niveles={k: Nivel(v["nivel"]) for k, v in clasif.items()},
        grupos={k: str(v.get("grupo", "")) for k, v in clasif.items()},
        si_falta={k: str(v["si_falta"]) for k, v in clasif.items() if v.get("si_falta")},
        detectores=det["detectores"],
        terminos_felicidad=tuple(det.get("terminos_felicidad", [])),
        terminos_desempeno=tuple(det.get("terminos_desempeno", [])),
        paises={str(k): str(v) for k, v in paises.items()})

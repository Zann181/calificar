"""F0: convierte los PDF de prueba con el servicio MinerU (en proceso) y mide el tiempo por página.

Uso (desde servicio-mineru/.venv):
    python ../herramientas/f0_convertir.py ../recursos/fixtures/kumar_2022.pdf ../recursos/fixtures/singh_2023.pdf

Guarda cada zip en recursos/fixtures/mineru/<nombre>.zip y agrega una línea a
docs/decisiones/0001/tiempos.csv (archivo, páginas, segundos, s/página, dispositivo).
"""

import csv
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "servicio-mineru"))

import pypdfium2  # noqa: E402  (dependencia de MinerU)

from app import convertir_bytes  # noqa: E402


def main() -> None:
    destino = RAIZ / "recursos" / "fixtures" / "mineru"
    destino.mkdir(parents=True, exist_ok=True)
    tiempos = RAIZ / "docs" / "decisiones" / "0001" / "tiempos.csv"
    tiempos.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not tiempos.exists()
    with tiempos.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["archivo", "paginas", "segundos", "s_por_pagina", "dispositivo", "fecha"])
        for ruta in map(Path, sys.argv[1:]):
            pdf = ruta.read_bytes()
            paginas = len(pypdfium2.PdfDocument(pdf))
            zip_bytes, seg = convertir_bytes(pdf, ruta.name)
            (destino / f"{ruta.stem}.zip").write_bytes(zip_bytes)
            w.writerow([ruta.name, paginas, f"{seg:.1f}", f"{seg / paginas:.1f}",
                        os.environ.get("MINERU_DEVICE_MODE", "cpu"), time.strftime("%Y-%m-%d %H:%M")])
            f.flush()
            print(f"{ruta.name}: {paginas} páginas, {seg:.1f} s ({seg / paginas:.1f} s/página)")


if __name__ == "__main__":
    main()

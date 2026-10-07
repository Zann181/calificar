"""F0: verificación automática del ADR 0001 sobre TODOS los bloques de Kumar y Singh.

Para cada bloque con texto, recorta el texto del PDF dentro del rectángulo convertido
(PyMuPDF, puntos, origen arriba a la izquierda) y lo compara con el texto de MinerU
(rapidfuzz.partial_ratio sobre texto normalizado). Si la fórmula de coordenadas fuera
errónea, el recorte traería otro texto y la similitud caería.

Uso (desde backend/.venv):
    python ../herramientas/f0_verificar_rectangulos.py
Salida: docs/decisiones/0001/verificacion.csv y resumen en pantalla.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pymupdf
from rapidfuzz import fuzz

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.compartido.normalizacion import norm  # noqa: E402
from app.contextos.biblioteca.adaptadores.mineru import normalizar  # noqa: E402

ARTICULOS = {"kumar_2022": "kumar_2022.pdf", "singh_2023": "singh_2023.pdf"}
_MARCAS = re.compile(r"</?su[bp]>|\$[^$]*\$")


def main() -> None:
    salida = RAIZ / "docs" / "decisiones" / "0001" / "verificacion.csv"
    filas = []
    for nombre, pdf_nombre in ARTICULOS.items():
        doc = normalizar((RAIZ / "recursos" / "fixtures" / "mineru" / f"{nombre}.zip").read_bytes())
        pdf = pymupdf.open(RAIZ / "recursos" / "fixtures" / pdf_nombre)
        for b in doc.bloques:
            if b.tipo in ("figura", "tabla"):
                continue  # el texto de tablas y figuras se compara aparte (OCR/HTML, no capa de texto)
            texto_mineru = norm(_MARCAS.sub(" ", b.texto))
            if not texto_mineru:
                filas.append([nombre, b.id, b.tipo, "", "SIN_TEXTO", ""])
                continue
            recorte = norm(pdf[b.pagina - 1].get_textbox(pymupdf.Rect(*b.rect.a_lista()) + (-2, -2, 2, 2)))
            sim = fuzz.partial_ratio(texto_mineru[:300], recorte) if recorte else 0.0
            # Desplazamiento de control: el mismo rectángulo corrido 40 pt hacia abajo
            corrido = norm(pdf[b.pagina - 1].get_textbox(pymupdf.Rect(*b.rect.a_lista()) + (0, 40, 0, 40)))
            sim_c = fuzz.partial_ratio(texto_mineru[:300], corrido) if corrido else 0.0
            filas.append([nombre, b.id, b.tipo, f"{sim:.1f}", "OK" if sim >= 90 else "REVISAR", f"{sim_c:.1f}"])
    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["articulo", "bloque", "tipo", "similitud", "estado", "similitud_control_corrido_40pt"])
        w.writerows(filas)
    for nombre in ARTICULOS:
        propias = [f for f in filas if f[0] == nombre]
        conteo = {e: sum(1 for f in propias if f[4] == e) for e in ("OK", "REVISAR", "SIN_TEXTO")}
        print(nombre, len(propias), "bloques de texto:", conteo)
    for f in filas:
        if f[4] == "REVISAR":
            print("  REVISAR", f)
    print("Salida:", salida)


if __name__ == "__main__":
    main()

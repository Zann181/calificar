"""LectorPdf sobre PyMuPDF: capa de texto dentro de un rectángulo (H1, H3) y páginas en PNG (sección 8.1)."""

from __future__ import annotations

import re
from typing import Any


def _pymupdf() -> Any:
    """PyMuPDF se importa al usarlo: el modo nube (ADR 0009) nunca lo necesita y no debe pagar su memoria."""
    import pymupdf

    return pymupdf


class LectorPyMuPdf:
    def textos_en_rect(self, pdf: bytes, rects: dict[str, tuple[int, tuple[float, float, float, float]]]) -> dict[str, str]:
        pymupdf = _pymupdf()
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            textos = {}
            for id_bloque, (pagina, (x0, y0, x1, y1)) in rects.items():
                if not 1 <= pagina <= doc.page_count:
                    continue
                # Recorte vertical de 2 pt: evita las líneas vecinas (igual que el arnés de F0).
                r = pymupdf.Rect(x0 - 1, y0 + 2, x1 + 1, y1 - 2)
                textos[id_bloque] = re.sub(r"[ \t]+", " ", doc[pagina - 1].get_textbox(r)).strip()
            return textos

    def renderizar(self, pdf: bytes, paginas: list[int], ppp: int = 110) -> dict[int, bytes]:
        with _pymupdf().open(stream=pdf, filetype="pdf") as doc:
            return {p: doc[p - 1].get_pixmap(dpi=ppp).tobytes("png") for p in paginas if 1 <= p <= doc.page_count}

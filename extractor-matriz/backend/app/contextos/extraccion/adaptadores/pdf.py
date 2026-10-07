"""LectorPdf sobre PyMuPDF: capa de texto dentro de un rectángulo (H1, H3) y páginas en PNG (sección 8.1)."""

from __future__ import annotations

import re

import pymupdf


class LectorPyMuPdf:
    def textos_en_rect(self, pdf: bytes, rects: dict[str, tuple[int, tuple[float, float, float, float]]]) -> dict[str, str]:
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
            textos = {}
            for id_bloque, (pagina, (x0, y0, x1, y1)) in rects.items():
                if not 1 <= pagina <= doc.page_count:
                    continue
                # Recorte vertical de 2 pt: evita las líneas vecinas (igual que el arnés de F0).
                r = pymupdf.Rect(x0 - 1, y0 + 2, x1 + 1, y1 - 2)  # type: ignore[no-untyped-call]
                textos[id_bloque] = re.sub(r"[ \t]+", " ", doc[pagina - 1].get_textbox(r)).strip()
            return textos

    def renderizar(self, pdf: bytes, paginas: list[int], ppp: int = 110) -> dict[int, bytes]:
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
            return {p: doc[p - 1].get_pixmap(dpi=ppp).tobytes("png") for p in paginas if 1 <= p <= doc.page_count}

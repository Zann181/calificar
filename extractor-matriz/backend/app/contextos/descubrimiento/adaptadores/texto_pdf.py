"""Texto de un PDF por páginas, con pymupdf (que solo se importa al usarlo: la nube no lo necesita)."""

from __future__ import annotations

from typing import Any

from app.compartido.dominio import ErrorDeDominio

MAX_PAGINAS = 80


class LectorDeTextoPymupdf:
    def paginas(self, datos: bytes) -> list[str]:
        import pymupdf

        try:
            doc: Any = pymupdf.open(stream=datos, filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as e:  # pymupdf lanza varios tipos según el daño
            raise ErrorDeDominio(f"{type(e).__name__}: {e}") from e
        try:
            return [doc[i].get_text() for i in range(min(len(doc), MAX_PAGINAS))]
        finally:
            doc.close()

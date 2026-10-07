"""F0: dibuja rectángulos de bloque sobre las páginas renderizadas para validar el ADR 0001.

Uso (desde backend/.venv):
    python ../herramientas/f0_dibujar_rectangulos.py

Para Kumar y Singh toma 10 bloques de cada uno (variando página y tipo), aplica la fórmula del
normalizador (bbox_content_list / 1000 × tamaño de página en puntos) y los dibuja con PyMuPDF,
cuyo sistema de coordenadas es el de PDF.js: puntos, origen arriba a la izquierda.
Salida: docs/decisiones/0001/<articulo>_p<NN>.png y docs/decisiones/0001/bloques.md (índice).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.contextos.biblioteca.adaptadores.mineru import normalizar  # noqa: E402

SALIDA = RAIZ / "docs" / "decisiones" / "0001"
ARTICULOS = {"kumar_2022": "kumar_2022.pdf", "singh_2023": "singh_2023.pdf"}
POR_ARTICULO = 10
DPI = 110
COLORES = {"titulo": (0.8, 0, 0.8), "parrafo": (0, 0.4, 1), "tabla": (1, 0.3, 0), "figura": (0, 0.6, 0),
           "otro": (0.5, 0.5, 0.5), "nota": (0.6, 0.3, 0), "ecuacion": (0, 0.6, 0.6), "leyenda": (0.3, 0.3, 0.9)}


def elegir(bloques: list, n: int) -> list:
    """Reparte la muestra entre tipos y páginas: primero un bloque por tipo, luego por página."""
    elegidos, vistos_tipo, vistas_pag = [], set(), set()
    for b in bloques:
        if b.tipo not in vistos_tipo:
            elegidos.append(b)
            vistos_tipo.add(b.tipo)
            vistas_pag.add(b.pagina)
    for b in bloques:
        if len(elegidos) >= n:
            break
        if b not in elegidos and b.pagina not in vistas_pag:
            elegidos.append(b)
            vistas_pag.add(b.pagina)
    for b in bloques:
        if len(elegidos) >= n:
            break
        if b not in elegidos and b.tipo in ("parrafo", "tabla"):
            elegidos.append(b)
    return sorted(elegidos[:n], key=lambda b: b.id)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    indice = ["# Bloques dibujados para el ADR 0001", "",
              "| # | Artículo | Bloque | Tipo | Rect (pt) | Texto |", "| --- | --- | --- | --- | --- | --- |"]
    k = 0
    for nombre, pdf_nombre in ARTICULOS.items():
        crudo = RAIZ / "recursos" / "fixtures" / "mineru" / f"{nombre}.zip"
        doc = normalizar(crudo.read_bytes())
        pdf = pymupdf.open(RAIZ / "recursos" / "fixtures" / pdf_nombre)
        muestra = elegir(list(doc.bloques), POR_ARTICULO)
        for pagina in sorted({b.pagina for b in muestra}):
            page = pdf[pagina - 1]
            for b in (x for x in muestra if x.pagina == pagina):
                k += 1
                r = pymupdf.Rect(*b.rect.a_lista())
                color = COLORES.get(b.tipo, (1, 0, 0))
                page.draw_rect(r, color=color, width=1.5)
                page.insert_text((r.x0 + 2, max(r.y0 - 2, 8)), f"{k} {b.id}", fontsize=7, color=color)
                texto = b.texto.replace("\n", " ").replace("|", "/")[:70]
                indice.append(f"| {k} | {nombre} | {b.id} | {b.tipo} | {tuple(round(v) for v in b.rect.a_lista())} | {texto} |")
            page.get_pixmap(dpi=DPI).save(SALIDA / f"{nombre}_p{pagina:02d}.png")
        p1 = doc.paginas[0]
        indice.append("")
        indice.append(f"{nombre}: página MinerU {p1.ancho_pt}×{p1.alto_pt} pt; PDF real "
                      f"{pdf[0].rect.width:.2f}×{pdf[0].rect.height:.2f} pt; rotación {pdf[0].rotation}.")
        indice.append("")
    (SALIDA / "bloques.md").write_text("\n".join(indice) + "\n", encoding="utf-8")
    print(f"{k} rectángulos dibujados en {SALIDA}")


if __name__ == "__main__":
    main()

"""Texto etiquetado (sección 8.1): el artículo con el identificador y el tipo de cada bloque.

Hallazgos del ADR 0001 que se resuelven aquí:
- H1 y H3: si MinerU dejó el bloque vacío o metió LaTeX ($), el texto sale de la capa de texto del
  PDF dentro del rectángulo del bloque. La aplicación lo pide al puerto LectorPdf y lo pasa en `capa`.
- H9: se quitan los escapes de Markdown (\\*\\*, \\_) que MinerU agrega en tablas y notas.

El texto de cada bloque que ve el modelo (`por_bloque`) es también el que usa el anclaje: así una
cita copiada del texto etiquetado se encuentra en el mismo texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.compartido.normalizacion import norm
from app.contextos.extraccion.dominio.documento import BloqueDeTrabajo, DocumentoDeTrabajo

_ESCAPE = re.compile(r"\\([*_#])")


def sin_escapes(texto: str) -> str:
    return _ESCAPE.sub(r"\1", texto)


def sin_cortes(texto: str) -> str:
    """Une las palabras cortadas al final de línea ("facto-\\nrial" → "factorial"), como hace norm() del
    validador con el texto de pdftotext. Si no, el modelo cita "facto- rial" y V23 la rechaza."""
    return texto.replace("-\n", "").replace("\n", " ").strip()


def necesita_capa(b: BloqueDeTrabajo) -> bool:
    """H1 y H3: bloques de texto que MinerU dejó vacíos o con LaTeX."""
    return not b.es_tabla and b.tipo != "figura" and (not b.texto.strip() or "$" in b.texto)


@dataclass(frozen=True)
class TextoEtiquetado:
    texto: str
    por_bloque: dict[str, str] = field(default_factory=dict)  # líneas del bloque tal como las ve el modelo
    efectivo_norm: dict[str, str] = field(default_factory=dict)  # texto normalizado para el anclaje


def _lineas_de_tabla(b: BloqueDeTrabajo, numero: int) -> tuple[list[str], str]:
    etiqueta = f"[{b.id} | tabla | Tabla {numero}]"
    if b.tabla_es_imagen:
        return [f"{etiqueta} (tabla en imagen; ver página {b.pagina} en PNG)"], b.texto
    filas = set(b.filas_grilla)
    todas = [ln for ln in b.texto.split("\n") if ln]
    n_leyenda = next((i for i, ln in enumerate(todas) if ln in filas), len(todas))
    libres = [ln for ln in todas if ln not in filas]
    partes = [f"{etiqueta} leyenda: {ln}" for ln in libres[:n_leyenda]]
    partes += [f'{etiqueta} fila "{c.etiqueta_fila}" | columna "{c.etiqueta_columna}" = "{c.texto}"'
               for c in b.celdas]
    partes += [f"{etiqueta} nota: {ln}" for ln in libres[n_leyenda:]]
    return partes, b.texto


def texto_etiquetado(doc: DocumentoDeTrabajo, capa: dict[str, str] | None = None) -> TextoEtiquetado:
    capa = capa or {}
    lineas: list[str] = []
    por_bloque: dict[str, str] = {}
    efectivo: dict[str, str] = {}
    n_tabla = 0
    for b in doc.bloques:
        if b.es_tabla:
            n_tabla += 1
            partes, base = _lineas_de_tabla(b, n_tabla)
            partes = [sin_escapes(p) for p in partes]
            lineas += partes
            por_bloque[b.id] = "\n".join(partes)
            efectivo[b.id] = norm(sin_escapes(base))
            continue
        if b.tipo == "figura":
            texto = sin_escapes(sin_cortes(b.texto))
            linea = f"[{b.id} | figura | imagen] {texto or '(sin texto)'} (ver página {b.pagina} en PNG)"
        else:
            texto = capa.get(b.id, "") if necesita_capa(b) else b.texto
            texto = sin_escapes(sin_cortes(texto))
            if not texto:
                continue
            linea = f"[{b.id} | {b.tipo}] {texto}"
        lineas.append(linea)
        por_bloque[b.id] = linea
        efectivo[b.id] = norm(texto)
    return TextoEtiquetado(texto="\n".join(lineas), por_bloque=por_bloque, efectivo_norm=efectivo)

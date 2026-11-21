"""Núcleo compartido: definición de columna que produce Normas y consumen Matriz y Exportación.

Es un objeto de valor sin comportamiento; la derivación desde el libro vive en
contextos/normas/dominio/catalogo.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NO_INDICA = "No indica"
NO_INDICA_NS = "No indica (no significativo)"
NO_APLICA = "No aplica"
CODIGOS_FALTANTE = (NO_INDICA, NO_INDICA_NS, NO_APLICA)

TIPOS_NUMERICOS = ("entero", "entero o null", "número o null")


@dataclass(frozen=True)
class DefinicionDeColumna:
    clave: str
    encabezado_excel: str
    letra: str
    posicion: int
    tipo_de_dato: str
    obligatorio: bool
    valores_permitidos: tuple[str, ...] | None
    requiere_evidencia: bool
    nivel_de_registro: str
    nota_encabezado: str
    # Guía de lectura de la columna, derivada del libro (para qué sirve, dónde buscar, regla, faltante, ejemplo).
    guia: dict[str, Any] = field(default_factory=dict, compare=False)
    # Columnas que calcula el programa (no el extractor): cómo se calculan, según el libro (instruccion_operativa.derivada).
    derivada: dict[str, Any] | None = field(default=None, compare=False)
    # Versión del libro que agregó la columna; el Excel anterior puede no traer su encabezado.
    agregada_en_version: str | None = None

    @property
    def es_derivada(self) -> bool:
        return self.derivada is not None

    @property
    def es_numerica(self) -> bool:
        return self.tipo_de_dato in TIPOS_NUMERICOS

    def a_dict(self) -> dict[str, Any]:
        return {
            "clave": self.clave,
            "encabezado_excel": self.encabezado_excel,
            "letra": self.letra,
            "posicion": self.posicion,
            "tipo_de_dato": self.tipo_de_dato,
            "obligatorio": self.obligatorio,
            "valores_permitidos": list(self.valores_permitidos) if self.valores_permitidos else None,
            "requiere_evidencia": self.requiere_evidencia,
            "nivel_de_registro": self.nivel_de_registro,
            "nota_encabezado": self.nota_encabezado,
            "es_numerica": self.es_numerica,
            "es_derivada": self.es_derivada,
            "agregada_en_version": self.agregada_en_version,
            "guia": self.guia,
        }

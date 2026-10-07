"""Núcleo compartido: definición de columna que produce Normas y consumen Matriz y Exportación.

Es un objeto de valor sin comportamiento; la derivación desde el libro vive en
contextos/normas/dominio/catalogo.py.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        }

"""Comparación de campos críticos entre dos extracciones (sección 8.3, pasos 6 y 8).

Numéricos con tolerancia 0.001; categorías por igualdad exacta (sin espacios en los extremos).
La lista de campos críticos es la de la sección 8.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TOLERANCIA = 0.001

CRITICOS_FILA = (
    "Muestra", "Correlación Feli 1 - JP", "Beta Fel 1- JP", "Fiabilidad Alfa - Omega (desempeño)",
    "Fiabilidad Alfa - Omega (felicidad)", "# Ítems", "Items instrumento1", "Desempeño", "Hedónica/eudaimónica",
    "Tipo de felicidad real", "How measure the employee perfomance", "Study design", "Nivel",
    "Analysis method (principal)", "Direccionalidad de la relación", "Incluir en meta análisi",
)
CRITICOS_TRAZABILIDAD = (
    "metodo_obtencion_r", "tipo_de_efecto", "tecnica_del_beta", "tipo_fiabilidad_desempeno",
    "tipo_fiabilidad_felicidad",
)
CAMPO_NUMERO_DE_FILAS = "número de filas"


@dataclass(frozen=True)
class Diferencia:
    fila: int | None  # posición en la salida; None para el número de filas
    estudio: Any
    campo: str
    valor_a: Any
    valor_b: Any

    def a_dict(self) -> dict[str, Any]:
        return {"fila": self.fila, "estudio": self.estudio, "campo": self.campo, "a": self.valor_a, "b": self.valor_b}


@dataclass(frozen=True)
class Comparacion:
    diferencias: tuple[Diferencia, ...]
    coincidencias: int
    total: int

    @property
    def acuerdo(self) -> float:
        return round(self.coincidencias / self.total, 3) if self.total else 0.0


def iguales(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(float(a) - float(b)) <= TOLERANCIA
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return bool(a == b)


def comparar(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> Comparacion:
    """Compara fila por fila, en orden. El número de filas cuenta como un campo."""
    diferencias: list[Diferencia] = []
    total, coincidencias = 1, 1
    if len(a) != len(b):
        coincidencias = 0
        diferencias.append(Diferencia(None, None, CAMPO_NUMERO_DE_FILAS, len(a), len(b)))
    for i in range(min(len(a), len(b))):
        fa, fb = a[i].get("fila") or {}, b[i].get("fila") or {}
        ta, tb = a[i].get("trazabilidad") or {}, b[i].get("trazabilidad") or {}
        pares = [(c, fa.get(c), fb.get(c)) for c in CRITICOS_FILA]
        pares += [(c, ta.get(c), tb.get(c)) for c in CRITICOS_TRAZABILIDAD]
        for campo, va, vb in pares:
            total += 1
            if iguales(va, vb):
                coincidencias += 1
            else:
                diferencias.append(Diferencia(i, fa.get("Estudio"), campo, va, vb))
    return Comparacion(diferencias=tuple(diferencias), coincidencias=coincidencias, total=total)

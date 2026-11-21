"""Columnas derivadas: las calcula el programa, no el extractor (libro v2.3, ADR 0008).

Cómo se calcula cada una lo dice el libro (`instruccion_operativa.derivada`); aquí solo se interpreta. Tipos:
- `trazabilidad`: refleja un campo de la trazabilidad de la fila (la trazabilidad es la fuente de verdad).
- `tabla`: busca el valor de otra columna en una tabla y lo clasifica contra un umbral (Cultura Hofstede).
- `por_condicion`: usa el número de condición del árbol de Incluir en meta análisi (Conjunto MA).

Un valor que no se puede calcular (por ejemplo, una fila heredada sin árbol) es None: la celda queda pendiente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.compartido.columnas import DefinicionDeColumna

Json = Any
_CONDICION = re.compile(r"^\s*Condición\s+(\d+)\s*:")


@dataclass(frozen=True)
class Derivada:
    valor: Json
    razon: str


def _de_trazabilidad(spec: dict[str, Any], valores: dict[str, Json], trazabilidad: dict[str, Any],
                     documento: int | None, provisional: bool) -> Derivada:
    campo = str(spec["campo"])
    valor = trazabilidad.get(campo)
    if valor is not None:
        return Derivada(valor, f"Refleja trazabilidad.{campo}.")
    modelo = spec.get("provisional_heredada")
    if provisional and modelo and documento is not None:
        return Derivada(str(modelo).format(documento=documento),
                        f"Provisional: la fila no tiene trazabilidad.{campo}; se asume una sola muestra por documento.")
    return Derivada(None, f"La fila no tiene trazabilidad.{campo}.")


def _por_tabla(spec: dict[str, Any], valores: dict[str, Json]) -> Derivada:
    sin_dato = spec["sin_dato"]
    pais = valores.get(str(spec["de"]))
    if not isinstance(pais, str) or not pais.strip():
        return Derivada(sin_dato, f"{spec['de']} vacío: sin valor para clasificar.")
    nombre = spec.get("alias", {}).get(pais.strip(), pais.strip())
    idv = spec["tabla_idv"].get(nombre)
    if idv is None:
        return Derivada(sin_dato, f"{nombre} no está en la tabla IDV del libro: revisar a mano.")
    clase = spec["por_encima"] if idv > spec["umbral"] else spec["por_debajo_o_igual"]
    return Derivada(clase, f"IDV de {nombre} = {idv} (umbral {spec['umbral']}).")


def _por_condicion(spec: dict[str, Any], valores: dict[str, Json], trazabilidad: dict[str, Any]) -> Derivada:
    motivo = trazabilidad.get(str(spec["campo"]))
    m = _CONDICION.match(motivo) if isinstance(motivo, str) else None
    if m is None:
        return Derivada(None, "La fila no tiene el número de condición del árbol de Incluir.")
    condicion = m.group(1)
    clase = spec["condiciones"].get(condicion, spec["por_defecto"])
    if clase != "Principal":
        return Derivada(clase, f"Condición {condicion} del árbol de Incluir.")
    enfoque = valores.get(str(spec["columna_para_principal"]))
    principal = spec["principal"].get(enfoque) if isinstance(enfoque, str) else None
    if principal is None:
        return Derivada(None, f"Condición {condicion}, pero {spec['columna_para_principal']} no permite elegir "
                              "el tipo de conjunto principal.")
    return Derivada(principal, f"Condición {condicion} del árbol de Incluir; {spec['columna_para_principal']} = "
                               f"{enfoque}.")


def calcular(definicion: DefinicionDeColumna, valores: dict[str, Json], trazabilidad: dict[str, Any], *,
             documento: int | None = None, provisional: bool = False) -> Derivada:
    """Valor de una columna derivada. `valores` trae las demás celdas de la fila por clave.

    `provisional`: la fila es heredada; se admiten los valores provisionales que el libro prevé para ella.
    """
    spec = definicion.derivada
    if spec is None:
        raise ValueError(f"'{definicion.clave}' no es una columna derivada")
    tipo = spec.get("tipo")
    if tipo == "trazabilidad":
        return _de_trazabilidad(spec, valores, trazabilidad, documento, provisional)
    if tipo == "tabla":
        return _por_tabla(spec, valores)
    if tipo == "por_condicion":
        return _por_condicion(spec, valores, trazabilidad)
    raise ValueError(f"Tipo de derivación desconocido en '{definicion.clave}': {tipo!r}")

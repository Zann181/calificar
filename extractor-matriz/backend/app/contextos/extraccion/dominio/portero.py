"""Portero de modelos (ADR 0005): decide si cada llamada va al modelo especializado o al ligero.

Prioridad, en este orden:
1. Regla central: un dato sin ubicación comprobable nunca entra como verificado. Los roles que producen
   o verifican la evidencia (extractor y auditor) van siempre al modelo especializado.
2. Campos críticos (sección 8.2): el conciliador decide en ellos con el modelo especializado.
3. Costo: el codificador ciego y el conciliador de campos no críticos usan el modelo ligero cuando el
   artículo no tiene señales de complejidad. Si la respuesta ligera no trae el JSON pedido, se repite
   con el especializado.

El portero no llama al modelo: mira el documento y el campo. Así no gasta créditos y se puede probar.
Los umbrales son provisionales hasta medirlos en los 5 artículos piloto de F2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.contextos.extraccion.dominio.comparacion import (
    CAMPO_NUMERO_DE_FILAS,
    CRITICOS_FILA,
    CRITICOS_TRAZABILIDAD,
)
from app.contextos.extraccion.dominio.documento import DocumentoDeTrabajo


class Nivel(StrEnum):
    ESPECIALIZADO = "especializado"
    LIGERO = "ligero"


@dataclass(frozen=True)
class Decision:
    nivel: Nivel
    motivo: str


# Roles que nunca bajan al modelo ligero (prioridad 1).
ROLES_ESPECIALIZADOS = ("extractor", "auditor")

CAMPOS_CRITICOS = frozenset((*CRITICOS_FILA, *CRITICOS_TRAZABILIDAD, CAMPO_NUMERO_DE_FILAS))

# Unos 100 mil tokens de texto del artículo: por encima, el modelo ligero cobra la tarifa de contexto largo.
MAX_CARACTERES_LIGERO = 300_000
MAX_TABLAS_LIGERO = 4

# Señales de varias filas de efecto o de la condición 9 (SEM latente), donde el modelo ligero se equivoca
# de categoría en campos críticos (Tipo de felicidad real en Singh, ADR 0002).
_COMPLEJIDAD = re.compile(
    r"structural equation|\bSEM\b|\blatent\b|multilevel|\bHLM\b|mediat|moderat|\bstudy\s*2\b|\bsample\s*2\b"
    r"|longitudinal|\bwave\s*2\b|\btime\s*2\b",
    re.I,
)


def decidir_rol(rol: str) -> Decision:
    if rol in ROLES_ESPECIALIZADOS:
        return Decision(Nivel.ESPECIALIZADO, f"el {rol} produce o verifica la evidencia")
    raise ValueError(f"El rol '{rol}' se decide con su propia regla")


def decidir_ciego(documento: DocumentoDeTrabajo, texto_etiquetado: str) -> Decision:
    if documento.paginas_con_imagen():
        return Decision(Nivel.ESPECIALIZADO, "tablas o figuras en imagen")
    if len(texto_etiquetado) > MAX_CARACTERES_LIGERO:
        return Decision(Nivel.ESPECIALIZADO, "artículo largo")
    if sum(1 for b in documento.bloques if b.es_tabla) > MAX_TABLAS_LIGERO:
        return Decision(Nivel.ESPECIALIZADO, f"más de {MAX_TABLAS_LIGERO} tablas")
    m = _COMPLEJIDAD.search(texto_etiquetado)
    if m:
        return Decision(Nivel.ESPECIALIZADO, f"diseño complejo ('{m.group(0)}')")
    return Decision(Nivel.LIGERO, "artículo sin señales de complejidad")


def decidir_conciliador(campo: str) -> Decision:
    if campo in CAMPOS_CRITICOS:
        return Decision(Nivel.ESPECIALIZADO, "campo crítico")
    return Decision(Nivel.LIGERO, "campo no crítico; el cambio solo se aplica si su cita se ancla")

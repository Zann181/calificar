"""Lo que cada rol recibe del libro de códigos (sección 8.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.contextos.extraccion.dominio.comparacion import CAMPO_NUMERO_DE_FILAS

# Secciones que van en el bloque de sistema. No se envían la capa diagnóstica ni recomendaciones_generales.
SECCIONES = ("prompt_para_el_extractor", "protocolo_de_extraccion", "como_se_construye_cada_fila",
             "vocabularios_controlados", "trazabilidad_por_fila", "validaciones_automaticas",
             "esquema_de_salida", "ejemplo_verificado")


def libro_para_sistema(libro: dict[str, Any]) -> str:
    partes: dict[str, Any] = {k: libro[k] for k in SECCIONES if k in libro}
    partes["columnas"] = {k: {"instruccion_operativa": v.get("instruccion_operativa")}
                          for k, v in (libro.get("columnas") or {}).items()}
    return json.dumps(partes, ensure_ascii=False, indent=1)


@dataclass(frozen=True)
class DatosDelEquipo:
    """Datos que el equipo entrega para cada artículo (prompt_para_el_extractor)."""

    documento: int
    estudio_inicial: int
    covidence: int | None = None
    via: str = "Covidence"


def prompt_del_extractor(libro: dict[str, Any], d: DatosDelEquipo) -> str:
    base = str(libro.get("prompt_para_el_extractor") or "")
    return (base.replace("Documento = <n>", f"Documento = {d.documento}")
                .replace("Estudio inicial = <n>", f"Estudio inicial = {d.estudio_inicial}")
                .replace("Covidence # = <n o vacío>", f"Covidence # = {d.covidence if d.covidence else 'vacío'}")
                .replace("Vía de identificación = <texto>", f"Vía de identificación = {d.via}"))


def regla_para_campo(libro: dict[str, Any], campo: str) -> Any:
    """Regla del libro que decide un campo, para el conciliador.

    H10 (ADR 0001): los campos estructurales no son columnas; el número de filas y el mapa de efectos se
    deciden con regla_para_abrir_una_fila_nueva, y los de trazabilidad con su entrada en trazabilidad_por_fila.
    """
    columna = (libro.get("columnas") or {}).get(campo)
    if columna is not None:
        return columna.get("instruccion_operativa")
    construccion = libro.get("como_se_construye_cada_fila") or {}
    if campo in (CAMPO_NUMERO_DE_FILAS, "mapa_de_efectos", "Estudio"):
        return construccion.get("regla_para_abrir_una_fila_nueva", construccion)
    trazabilidad = libro.get("trazabilidad_por_fila") or {}
    if isinstance(trazabilidad, dict):
        campos = trazabilidad.get("campos", trazabilidad)
        if isinstance(campos, dict) and campo in campos:
            return campos[campo]
    return trazabilidad

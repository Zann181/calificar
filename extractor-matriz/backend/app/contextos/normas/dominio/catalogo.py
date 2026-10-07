"""Servicio de dominio CatalogoDeColumnas.

Deriva del contenido del libro de códigos la definición de cada columna. Nada de lo que
sabe la aplicación sobre columnas se escribe a mano: grilla, validación y exportación
leen de aquí.

nota_encabezado reproduce el texto de las notas del Excel (Matriz_de_sintesis_con_notas.xlsx);
la prueba test_catalogo.py lo compara con las 54 notas.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio

_LIMITE_EJEMPLO = 217
_NOTA_FINAL = (
    "Nota: el registro de trazabilidad es la hoja Trazabilidad que genera la skill "
    "(página, ubicación y cita de cada dato)."
)
SECCIONES_OBLIGATORIAS = ("columnas", "esquema_de_salida", "vocabularios_controlados", "validaciones_automaticas")


class LibroInvalido(ErrorDeDominio):
    pass


def _legible(texto: str) -> str:
    """Pasa las referencias técnicas del libro al lenguaje de las notas del Excel."""
    texto = re.sub(
        r"trazabilidad\.(\w+)",
        lambda m: "el registro de trazabilidad (" + m.group(1).replace("_", " ") + ")",
        texto,
    )
    texto = texto.replace("(V14)", "(regla V14 del libro)")
    texto = re.sub(r"\bes null\b", "está vacía", texto)
    texto = re.sub(r"\bnull\b", "celda vacía", texto)
    return texto.replace(" a el registro", " al registro").replace(" de el registro", " del registro")


def _ejemplo(valor: Any) -> str:
    if valor is None:
        return "celda vacía"
    texto = str(valor).replace("\n", " / ")
    return texto if len(texto) <= _LIMITE_EJEMPLO else texto[:_LIMITE_EJEMPLO] + "..."


def _nota(clave: str, col: dict[str, Any], ejemplo: dict[str, Any]) -> str:
    io = col["instruccion_operativa"]
    lineas = [
        f"{col['letra_excel']}. {clave}",
        "",
        "PARA QUÉ SIRVE",
        f"{col['descripcion']} {col.get('relacion_con_otras_columnas', '')}".strip(),
        "",
        "CÓMO LLENARLA",
    ]
    if io.get("donde_buscar"):
        lineas.append(_legible(f"Dónde buscar: {io['donde_buscar']}"))
    regla = io.get("regla_de_decision")
    if regla is None and isinstance(col.get("reglas_de_codificacion"), list):
        regla = col["reglas_de_codificacion"]
    if isinstance(regla, list):
        lineas += [_legible(f"• {x}") for x in regla]
    elif regla:
        lineas.append(_legible(regla))
    if isinstance(io.get("valores_permitidos"), list):
        lineas.append("Valores permitidos: " + "; ".join(io["valores_permitidos"]))
    if io.get("formato"):
        lineas.append(_legible(f"Formato: {io['formato']}"))
    tipo = (
        _legible(io["tipo_de_dato"])
        + "; "
        + ("obligatoria" if io["obligatorio"] else "opcional")
        + f"; nivel {io['nivel_de_registro']}"
        + ("; exige página y cita del artículo" if io["requiere_evidencia"] else "")
    )
    lineas += [
        "",
        "TIPO DE DATO Y NIVEL",
        tipo,
        "",
        "SI EL DATO NO ESTÁ",
        _legible(io["codigo_si_falta"]),
        "",
        "EJEMPLO (Kumar, 2022, verificado)",
        _ejemplo(ejemplo.get(clave)),
        "",
        _NOTA_FINAL,
    ]
    return "\n".join(lineas)


# Campos de trazabilidad que no describen una celda concreta: se explican en otro lugar de la interfaz.
_TRAZABILIDAD_GENERAL = frozenset({
    "evidencia", "inferencias", "discrepancias_en_el_articulo", "advertencias_pendientes", "mapa_de_efectos",
    "estado_del_dato", "confianza", "extractor", "fecha_extraccion", "verificador", "id_muestra",
})


def _textos(valor: Any) -> Any:
    if isinstance(valor, str):
        return _legible(valor)
    if isinstance(valor, list):
        return [_textos(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _textos(v) for k, v in valor.items()}
    return valor


def _campos_de_trazabilidad(col: dict[str, Any], campos: dict[str, str]) -> list[dict[str, str]]:
    """Campos de trazabilidad que el propio libro nombra en las reglas de la columna."""
    io = col["instruccion_operativa"]
    texto = json.dumps(
        [io, col.get("como_se_extrae"), col.get("reglas_de_codificacion"), col.get("tratamiento_del_dato_faltante"),
         col.get("relacion_con_otras_columnas")], ensure_ascii=False)
    return [{"campo": c, "descripcion": _legible(d)} for c, d in campos.items()
            if c not in _TRAZABILIDAD_GENERAL and re.search(r"\b" + re.escape(c) + r"\b", texto)]


def _guia(col: dict[str, Any], campos: dict[str, str]) -> dict[str, Any]:
    """Lo que el libro dice de la columna, para explicar por qué y cómo se llenó una celda."""
    io = col["instruccion_operativa"]
    nivel = col.get("nivel_de_registro")
    guia: dict[str, Any] = {
        "para_que_sirve": col.get("descripcion"),
        "relacion_con_otras_columnas": col.get("relacion_con_otras_columnas"),
        "naturaleza": col.get("naturaleza"),
        "escala_de_medicion": col.get("escala_de_medicion"),
        "nivel_recomendado": nivel.get("recomendado") if isinstance(nivel, dict) else nivel,
        "donde_buscar": io.get("donde_buscar"),
        "como_se_extrae": col.get("como_se_extrae"),
        "regla_de_decision": io.get("regla_de_decision"),
        "reglas_de_codificacion": col.get("reglas_de_codificacion"),
        "formato": io.get("formato"),
        "codigo_si_falta": io.get("codigo_si_falta"),
        "tratamiento_del_dato_faltante": col.get("tratamiento_del_dato_faltante"),
        "ejemplo": col.get("ejemplo"),
        "campos_de_trazabilidad": _campos_de_trazabilidad(col, campos),
    }
    return {k: _textos(v) for k, v in guia.items() if v not in (None, "", [], {})}


def derivar_protocolo(contenido: dict[str, Any]) -> dict[str, Any]:
    """Reglas generales del libro que explican cómo se lee cualquier celda (veracidad, fuentes, faltantes)."""
    p = contenido.get("protocolo_de_extraccion") or {}
    formato = p.get("formato_general") or {}
    protocolo: dict[str, Any] = _textos({
        "principios_de_veracidad": p.get("principios_de_veracidad") or [],
        "precedencia_de_fuentes": p.get("precedencia_de_fuentes_dentro_del_articulo") or [],
        "faltantes": formato.get("faltantes") or {},
        "como_se_construye_cada_fila": {
            "unidad_de_analisis": (contenido.get("como_se_construye_cada_fila") or {}).get("unidad_de_analisis"),
            "jerarquia": (contenido.get("como_se_construye_cada_fila") or {}).get("jerarquia"),
            "regla_para_abrir_una_fila_nueva":
                (contenido.get("como_se_construye_cada_fila") or {}).get("regla_para_abrir_una_fila_nueva") or [],
        },
    })
    return protocolo


def validar_estructura(contenido: dict[str, Any]) -> None:
    faltan = [s for s in SECCIONES_OBLIGATORIAS if s not in contenido]
    if faltan:
        raise LibroInvalido(f"Al libro le faltan secciones: {', '.join(faltan)}")
    for clave, col in contenido["columnas"].items():
        for campo in ("posicion", "letra_excel", "encabezado_original", "descripcion", "instruccion_operativa"):
            if campo not in col:
                raise LibroInvalido(f"La columna '{clave}' no tiene '{campo}'")


def derivar_columnas(contenido: dict[str, Any]) -> list[DefinicionDeColumna]:
    validar_estructura(contenido)
    salidas = contenido.get("ejemplo_verificado", {}).get("salida") or [{}]
    ejemplo: dict[str, Any] = salidas[0].get("fila", {})
    columnas = []
    campos = (contenido.get("trazabilidad_por_fila") or {}).get("campos") or {}
    for clave, col in contenido["columnas"].items():
        io = col["instruccion_operativa"]
        permitidos = io.get("valores_permitidos")
        columnas.append(
            DefinicionDeColumna(
                clave=clave,
                encabezado_excel=col["encabezado_original"],
                letra=col["letra_excel"],
                posicion=int(col["posicion"]),
                tipo_de_dato=io["tipo_de_dato"],
                obligatorio=bool(io["obligatorio"]),
                valores_permitidos=tuple(permitidos) if isinstance(permitidos, list) else None,
                requiere_evidencia=bool(io["requiere_evidencia"]),
                nivel_de_registro=str(io["nivel_de_registro"]),
                nota_encabezado=_nota(clave, col, ejemplo),
                guia=_guia(col, campos),
            )
        )
    columnas.sort(key=lambda c: c.posicion)
    posiciones = [c.posicion for c in columnas]
    if len(set(posiciones)) != len(posiciones):
        raise LibroInvalido("Hay columnas con la misma posición")
    return columnas


class CatalogoDeColumnas:
    """Vista de consulta sobre las columnas de una versión del libro."""

    def __init__(self, contenido: dict[str, Any]) -> None:
        self._columnas = derivar_columnas(contenido)
        self._por_clave = {c.clave: c for c in self._columnas}

    @property
    def columnas(self) -> list[DefinicionDeColumna]:
        return list(self._columnas)

    def columna(self, clave: str) -> DefinicionDeColumna:
        try:
            return self._por_clave[clave]
        except KeyError as e:
            raise ErrorDeDominio(f"Columna desconocida: {clave}") from e

    def por_posicion(self, posicion: int) -> DefinicionDeColumna:
        for c in self._columnas:
            if c.posicion == posicion:
                return c
        raise ErrorDeDominio(f"No hay columna en la posición {posicion}")

    def claves(self) -> list[str]:
        return [c.clave for c in self._columnas]

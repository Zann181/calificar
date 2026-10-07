"""Instrucciones de los cuatro roles (sección 8.2) y lectura de sus respuestas.

Los textos vienen del arnés de F0 (herramientas/f0_extraccion.py), que dio 0 errores del validador
y 22 de 22 campos críticos en Kumar y Singh (ADR 0002).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.contextos.extraccion.dominio.libro import DatosDelEquipo, prompt_del_extractor

REGLA_BLOQUES = (
    "El artículo llega como texto etiquetado: cada línea empieza con [pNN-bMM | tipo]. pNN es la página "
    "del PDF. Cita solo bloques que existen en el texto etiquetado y copia la cita literal de ese bloque. "
    "En cada objeto de evidencia agrega la clave \"bloque_id\" con el identificador del bloque citado "
    "(libro v2.2). Para tablas y figuras que son imagen, lee los archivos PNG "
    "indicados con la herramienta Read."
)

REGLAS_EXTRACTOR = (
    "Reglas no negociables:\n- Cada valor lleva página del PDF, ubicación y una cita literal y contigua de 25 "
    "palabras como máximo.\n- Nada de conocimiento externo: ni siglas, ni años, ni número de ítems, ni teorías "
    "que el artículo no diga.\n- Toda inferencia va a trazabilidad.inferencias y toda contradicción del "
    "artículo a discrepancias_en_el_articulo.\n- Si una regla del libro te obliga a escribir algo falso o no "
    "cubre el caso, no lo fuerces: repórtalo en trazabilidad.advertencias_pendientes.\n"
    "Responde únicamente con el arreglo JSON."
)


class RespuestaInvalida(ValueError):
    """El modelo no devolvió el JSON pedido."""


def json_de(texto: str) -> Any:
    """Toma el JSON de la respuesta: dentro de un bloque ``` o desde el primer [ o {."""
    m = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    candidato = m.group(1) if m else texto
    posiciones = [i for i in (candidato.find("["), candidato.find("{")) if i >= 0]
    if not posiciones:
        raise RespuestaInvalida(f"La respuesta no trae JSON: {texto[:200]!r}")
    try:
        return json.loads(candidato[min(posiciones):])
    except json.JSONDecodeError:
        # Texto después del JSON: se toma el valor más largo que decodifica.
        try:
            valor, _ = json.JSONDecoder().raw_decode(candidato[min(posiciones):])
            return valor
        except json.JSONDecodeError as e:
            raise RespuestaInvalida(f"JSON inválido en la respuesta: {e}") from e


def lista_de(texto: str) -> list[dict[str, Any]]:
    valor = json_de(texto)
    if isinstance(valor, dict):
        valor = [valor]
    if not isinstance(valor, list) or not all(isinstance(x, dict) for x in valor):
        raise RespuestaInvalida("Se esperaba un arreglo JSON de objetos")
    return valor


def _imagenes(nombres: list[str]) -> str:
    return ", ".join(nombres) or "ninguna"


def extractor(libro: dict[str, Any], libro_sistema: str, datos: DatosDelEquipo, etiquetado: str,
              imagenes: list[str]) -> tuple[str, str]:
    sistema = (prompt_del_extractor(libro, datos) + "\n\n" + REGLA_BLOQUES
               + "\n\nLIBRO DE CÓDIGOS (secciones normativas y contexto):\n" + libro_sistema)
    mensaje = (f"{REGLAS_EXTRACTOR}\n\nImágenes de páginas con figuras o tablas en imagen: {_imagenes(imagenes)}\n\n"
               f"TEXTO ETIQUETADO DEL ARTÍCULO:\n{etiquetado}")
    return sistema, mensaje


def correccion(mensaje: str, salida: list[dict[str, Any]], errores: list[str]) -> str:
    return (f"{mensaje}\n\nTU SALIDA ANTERIOR:\n{json.dumps(salida, ensure_ascii=False)}\n\n"
            "ERRORES DEL VALIDADOR (corrígelos sin inventar datos; conserva bloque_id en cada evidencia):\n"
            + "\n".join(errores) + "\nResponde únicamente con el arreglo JSON corregido.")


def auditor(libro_sistema: str, salida: list[dict[str, Any]], anclas: list[dict[str, Any]], etiquetado: str,
            imagenes: list[str]) -> tuple[str, str]:
    sistema = ("Eres el Agente Auditor de evidencia. No extraes: verificas. " + REGLA_BLOQUES
               + "\n\nLIBRO DE CÓDIGOS:\n" + libro_sistema)
    mensaje = (
        "Para cada fila y cada columna con valor distinto de faltante:\n"
        "1. Comprueba en el texto etiquetado que la cita existe en la página citada y que sostiene el valor en esa "
        "columna. Para tablas, verifica la fila y la columna de la tabla. Para figuras y tablas en imagen, mira el PNG.\n"
        "2. Comprueba que la categoría cumple la instruccion_operativa de la columna.\n"
        "3. Comprueba que los faltantes (No indica, No aplica) son reales: busca en todo el artículo si el dato sí estaba.\n"
        "4. Comprueba que no se abrieron filas de más ni de menos según regla_para_abrir_una_fila_nueva.\n"
        "Las anclas indican dónde encontró el programa cada cita (NO_VERIFICABLE: no la encontró); revísalas con "
        "especial cuidado.\n"
        "Veredictos por celda: CONFIRMADO, REFUTADO (con la evidencia correcta: página, bloque_id y cita) o NO VERIFICABLE "
        "(con el motivo). Responde únicamente con un arreglo JSON de objetos {estudio, columna, auditor: \"Auditor de "
        "evidencia\", veredicto, hallazgo, evidencia, resolucion: null, estado: \"Pendiente\"} solo con los veredictos "
        "distintos de CONFIRMADO. Sin elogios.\n\n"
        f"Imágenes: {_imagenes(imagenes)}\n\nSALIDA A AUDITAR:\n{json.dumps(salida, ensure_ascii=False)}\n\n"
        f"ANCLAS:\n{json.dumps(anclas, ensure_ascii=False)}\n\nTEXTO ETIQUETADO DEL ARTÍCULO:\n{etiquetado}")
    return sistema, mensaje


def ciego(libro_sistema: str, datos: DatosDelEquipo, etiquetado: str, imagenes: list[str]) -> tuple[str, str]:
    sistema = ("Eres el Codificador Ciego. No tienes acceso a otra extracción y no debes buscarla. " + REGLA_BLOQUES
               + "\n\nLIBRO DE CÓDIGOS:\n" + libro_sistema)
    mensaje = (
        f"Datos del equipo: Documento = {datos.documento}, Estudio inicial = {datos.estudio_inicial}.\n"
        "Extrae de forma independiente, para cada fila que corresponda abrir según el libro, solo estos campos, cada uno "
        "con página, bloque_id y cita literal: número de filas y su mapa de efectos; Muestra; Correlación Feli 1 - JP y "
        "metodo_obtencion_r; Beta Fel 1- JP, tipo_de_efecto y tecnica_del_beta; las dos fiabilidades con su tipo "
        "(tipo_fiabilidad_desempeno, tipo_fiabilidad_felicidad); # Ítems e Items instrumento1; Desempeño, "
        "Hedónica/eudaimónica y Tipo de felicidad real; How measure the employee perfomance, Study design, Nivel y "
        "Analysis method (principal); Direccionalidad de la relación e Incluir en meta análisi con su condición.\n"
        "Responde únicamente con un arreglo JSON, un objeto por fila: {\"fila\": {Estudio y los campos de columna con su "
        "clave exacta}, \"trazabilidad\": {metodo_obtencion_r, tipo_de_efecto, tecnica_del_beta, tipo_fiabilidad_desempeno, "
        "tipo_fiabilidad_felicidad, mapa_de_efectos, motivo_decision_inclusion, evidencia: {campo: [{pagina_pdf, bloque_id, "
        "cita_textual}]}}}. Usa los mismos vocabularios y formatos numéricos que esquema_de_salida.\n\n"
        f"Imágenes: {_imagenes(imagenes)}\n\nTEXTO ETIQUETADO DEL ARTÍCULO:\n{etiquetado}")
    return sistema, mensaje


SISTEMA_CONCILIADOR = (
    "Eres el Conciliador. Decide usando solo el texto de los bloques que recibes. No uses conocimiento externo "
    "ni elijas por mayoría. Si el texto de los bloques no alcanza para decidir, responde PENDIENTE.")


def conciliador(*, estudio: Any, campo: str, valor_extractor: Any, valor_alternativo: Any, origen: str,
                detalle: Any, regla: Any, bloques: str) -> str:
    return (
        f"Celda: Estudio {estudio}, campo '{campo}'.\n"
        f"Valor del extractor: {json.dumps(valor_extractor, ensure_ascii=False)}\n"
        f"Valor alternativo ({origen}): {json.dumps(valor_alternativo, ensure_ascii=False)}\n"
        f"Detalle: {json.dumps(detalle, ensure_ascii=False)}\n"
        f"Regla del libro: {json.dumps(regla, ensure_ascii=False)}\n\nBLOQUES:\n{bloques}\n\n"
        "Devuelve solo un objeto JSON: {\"decision\": \"VALOR_EXTRACTOR\" | \"VALOR_ALTERNATIVO\" | \"OTRO\" | \"PENDIENTE\", "
        "\"valor\": <valor final o null>, \"bloque_id\": \"<id>\", \"cita_textual\": \"<subcadena literal de 25 palabras como "
        "máximo>\", \"razonamiento\": \"<una o dos oraciones>\"}")


def bloques_citados(por_bloque: dict[str, str], *fuentes: Any) -> str:
    ids = set(re.findall(r"p\d{2,}-b\d{2,}", json.dumps(fuentes, ensure_ascii=False)))
    return "\n".join(por_bloque[i] for i in sorted(ids) if i in por_bloque) or "(sin bloques citados)"

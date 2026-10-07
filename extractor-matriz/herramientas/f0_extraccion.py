"""F0: extracción completa de un artículo con los cuatro roles mediante Claude Code CLI (ADR 0002).

Mide tokens y costo por rol y compara la salida con el ejemplo verificado. Es un arnés de la
prueba técnica, no el motor M4: no escribe en la base ni en la matriz.

Uso (desde backend/.venv, en la raíz del repositorio):
    python herramientas/f0_extraccion.py kumar_2022                     # cuatro roles
    python herramientas/f0_extraccion.py singh_2023 --solo-extractor --modelo-extractor claude-sonnet-5-5
    python herramientas/f0_extraccion.py kumar_2022 --sin-modelo         # solo prepara y prueba lo local

Salida: docs/decisiones/f0/extraccion/<articulo>__<modelo extractor>/ con texto_etiquetado.txt,
salida.json, anclas.json, validacion_*.txt, auditoria_evidencia.json, codificacion_ciega.json,
discrepancias.json, conciliacion.json, comparacion_verificado.json y uso.csv.

Decisiones de la prueba (ver ADR 0001, hallazgos H1-H5):
- El texto de los bloques de párrafo sale de la capa de texto del PDF dentro del rectángulo de
  MinerU (H1: MinerU mueve el texto de párrafos que cruzan página; H3: convierte números en LaTeX).
- Libro v2.2 (H5, decidido 2026-10-05): bloque_id viaja dentro de cada evidencia; anclas.json
  solo resume las anclas para revisarlas.
- El validador se ejecuta sin modificar, con herramientas/validar_utf8.py (H4).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pymupdf

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.contextos.biblioteca.adaptadores.mineru import _grilla, normalizar  # noqa: E402
from app.contextos.biblioteca.dominio.documento import Bloque, DocumentoEstructurado  # noqa: E402

LIBRO = RAIZ / "recursos" / "Libro_de_codigos_extraccion_v2.json"
FIXTURES = RAIZ / "recursos" / "fixtures"
SALIDA_BASE = RAIZ / "docs" / "decisiones" / "f0" / "extraccion"

# Datos del equipo (Documento, Estudio inicial, Covidence #, vía) tomados de los ejemplos verificados.
ARTICULOS: dict[str, dict[str, Any]] = {
    "kumar_2022": {"documento": 1, "estudio": 1, "covidence": 671, "via": "Covidence"},
    "singh_2023": {"documento": 47, "estudio": 71, "covidence": None,
                   "via": "Otros métodos: búsqueda manual"},
}

MODELOS = {
    "extractor": os.environ.get("MODELO_EXTRACTOR", "claude-opus-5-5"),
    "auditor": os.environ.get("MODELO_AUDITOR", "claude-opus-5-5"),
    "ciego": os.environ.get("MODELO_CIEGO", "claude-sonnet-5-5"),
    "conciliador": os.environ.get("MODELO_CONCILIADOR", "claude-opus-5-5"),
}

SECCIONES = ["prompt_para_el_extractor", "protocolo_de_extraccion", "como_se_construye_cada_fila",
             "vocabularios_controlados", "trazabilidad_por_fila", "validaciones_automaticas",
             "esquema_de_salida", "ejemplo_verificado"]

FILA_CRITICOS = ["Muestra", "Correlación Feli 1 - JP", "Beta Fel 1- JP", "Fiabilidad Alfa - Omega (desempeño)",
                 "Fiabilidad Alfa - Omega (felicidad)", "# Ítems", "Items instrumento1", "Desempeño",
                 "Hedónica/eudaimónica", "Tipo de felicidad real", "How measure the employee perfomance",
                 "Study design", "Nivel", "Analysis method (principal)", "Direccionalidad de la relación",
                 "Incluir en meta análisi"]
TRAZ_CRITICOS = ["metodo_obtencion_r", "tipo_de_efecto", "tecnica_del_beta", "tipo_fiabilidad_desempeno",
                 "tipo_fiabilidad_felicidad"]
TOLERANCIA = 0.001
MAX_ITERACIONES = 3

REGLA_BLOQUES = (
    "El artículo llega como texto etiquetado: cada línea empieza con [pNN-bMM | tipo]. pNN es la página "
    "del PDF. Cita solo bloques que existen en el texto etiquetado y copia la cita literal de ese bloque. "
    "En cada objeto de evidencia agrega la clave \"bloque_id\" con el identificador del bloque citado "
    "(libro v2.2). Para tablas y figuras que son imagen, lee los archivos PNG "
    "indicados con la herramienta Read."
)


# --------------------------------------------------------------------------- preparación

def texto_de_capa(pdf: pymupdf.Document, b: Bloque) -> str:
    r = pymupdf.Rect(*b.rect.a_lista()) + (-1, 2, 1, -2)  # recorte vertical: evita líneas vecinas
    return re.sub(r"[ \t]+", " ", pdf[b.pagina - 1].get_textbox(r)).strip()


def _sin_escapes(texto: str) -> str:
    """MinerU escapa Markdown en tablas y notas (\\*\\* p<.001, cr\\_fdh); el PDF no lo trae (hallazgo H9)."""
    return re.sub(r"\\([*_#])", r"\1", texto)


def texto_etiquetado(doc: DocumentoEstructurado, pdf: pymupdf.Document) -> tuple[str, dict[str, str]]:
    """Formato de la sección 8.1. Devuelve el texto y el texto usado por bloque (para conciliar)."""
    lineas: list[str] = []
    por_bloque: dict[str, str] = {}
    n_tabla = 0
    for b in doc.bloques:
        if b.tipo == "tabla" and b.tabla is not None:
            n_tabla += 1
            etiqueta = f"[{b.id} | tabla | Tabla {n_tabla}]"
            if b.tabla.es_imagen:
                texto = f"{etiqueta} (tabla en imagen; ver página {b.pagina} en PNG)"
                lineas.append(texto)
                por_bloque[b.id] = b.texto
                continue
            # b.texto = leyenda + filas de la grilla + notas al pie; las filas se reemplazan por celdas
            filas = {" ".join(f) for f in _grilla(b.tabla.html)}
            todas = [ln for ln in b.texto.split("\n") if ln]
            n_leyenda = next((i for i, ln in enumerate(todas) if ln in filas), len(todas))
            libres = [ln for ln in todas if ln not in filas]
            partes = [f"{etiqueta} leyenda: {ln}" for ln in libres[:n_leyenda]]
            partes += [f'{etiqueta} fila "{c.etiqueta_fila}" | columna "{c.etiqueta_columna}" = "{c.texto}"'
                       for c in b.tabla.celdas]
            partes += [f"{etiqueta} nota: {ln}" for ln in libres[n_leyenda:]]
            lineas += partes
            por_bloque[b.id] = "\n".join(partes)
            continue
        if b.tipo == "figura":
            texto = b.texto.replace("\n", " ").strip() or "(sin texto)"
            linea = f"[{b.id} | figura | imagen] {texto} (ver página {b.pagina} en PNG)"
        else:
            # H1/H3: solo cuando MinerU dejó el bloque vacío o metió LaTeX se usa la capa de texto del PDF
            texto = texto_de_capa(pdf, b) if (not b.texto.strip() or "$" in b.texto) else b.texto
            if not texto.strip():
                continue
            linea = f"[{b.id} | {b.tipo}] " + texto.replace("\n", " ")
        lineas.append(linea)
        por_bloque[b.id] = linea
    lineas = [_sin_escapes(ln) for ln in lineas]
    por_bloque = {k: _sin_escapes(v) for k, v in por_bloque.items()}
    return "\n".join(lineas), por_bloque


def renderizar_paginas(doc: DocumentoEstructurado, pdf: pymupdf.Document, destino: Path) -> list[Path]:
    paginas = sorted({b.pagina for b in doc.bloques
                      if b.tipo == "figura" or (b.tabla is not None and b.tabla.es_imagen)})
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for p in paginas:
        ruta = destino / f"pag-{p:02d}.png"
        pdf[p - 1].get_pixmap(dpi=110).save(ruta)
        rutas.append(ruta)
    return rutas


def libro_para_sistema(libro: dict[str, Any]) -> str:
    partes = {k: libro[k] for k in SECCIONES}
    partes["columnas"] = {k: {"instruccion_operativa": v.get("instruccion_operativa")}
                          for k, v in libro["columnas"].items()}
    return json.dumps(partes, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- llamada al modelo

def _entorno_cli() -> dict[str, str]:
    """La CLI usa la sesión propia del equipo; no hereda la del proceso anfitrión."""
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL")}


def llamar(rol: str, modelo: str, sistema: str, mensaje: str, trabajo: Path, *, con_lectura: bool,
           uso: list[dict[str, Any]]) -> str:
    archivo_sistema = trabajo / f"sistema_{rol}.txt"
    archivo_sistema.write_text(sistema, encoding="utf-8")
    cmd = [os.environ.get("CLAUDE_CLI", "claude"), "-p", "--output-format", "json", "--model", modelo,
           "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
           "--system-prompt-file", str(archivo_sistema), "--max-turns", "30"]
    cmd += ["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(trabajo)] if con_lectura else ["--tools", ""]
    inicio = time.perf_counter()
    r = subprocess.run(cmd, input=mensaje, capture_output=True, text=True, encoding="utf-8",
                       cwd=trabajo, env=_entorno_cli(), timeout=3600)
    try:
        datos = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{rol}: la CLI no devolvió JSON: {r.stdout[:300]} {r.stderr[:300]}") from e
    u = datos.get("usage", {})
    uso.append({
        "rol": rol, "modelo": modelo, "segundos": round(time.perf_counter() - inicio, 1),
        "turnos": datos.get("num_turns"), "input": u.get("input_tokens", 0),
        "cache_escritura": u.get("cache_creation_input_tokens", 0), "cache_lectura": u.get("cache_read_input_tokens", 0),
        "output": u.get("output_tokens", 0), "costo_usd": datos.get("total_cost_usd", 0), "error": datos.get("is_error"),
    })
    if datos.get("is_error"):
        raise RuntimeError(f"{rol}: {datos.get('result')}")
    return str(datos.get("result", ""))


def json_de(texto: str) -> Any:
    m = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    candidato = m.group(1) if m else texto
    inicio = min((i for i in (candidato.find("["), candidato.find("{")) if i >= 0), default=0)
    return json.loads(candidato[inicio:])


# --------------------------------------------------------------------------- validación y anclas

def separar_bloques(salida: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resume las anclas por fila, columna y evidencia; no modifica la salida (libro v2.2)."""
    anclas: dict[str, Any] = {}
    for i, f in enumerate(salida):
        for col, evs in (f.get("trazabilidad", {}).get("evidencia") or {}).items():
            for j, e in enumerate(evs or []):
                if isinstance(e, dict) and "bloque_id" in e:
                    anclas[f"{i}|{col}|{j}"] = e["bloque_id"]
    return salida, anclas


def validar(ruta_salida: Path, articulo: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(RAIZ / "herramientas" / "validar_utf8.py"), str(ruta_salida), str(LIBRO),
                        str(FIXTURES / f"{articulo}.pdf")], capture_output=True, text=True, encoding="utf-8")
    m = re.search(r"(\d+) errores", r.stdout)
    return (int(m.group(1)) if m else 99), r.stdout + r.stderr


# --------------------------------------------------------------------------- comparación

def _igual(a: Any, b: Any) -> bool:
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= TOLERANCIA
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def comparar(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """Campos críticos fila por fila. Devuelve (diferencias, coincidencias, total)."""
    difs: list[dict[str, Any]] = []
    coincidencias = total = 1
    if len(a) != len(b):
        coincidencias = 0
        difs.append({"fila": None, "campo": "número de filas", "a": len(a), "b": len(b)})
    for i in range(min(len(a), len(b))):
        fa, fb = a[i].get("fila", {}), b[i].get("fila", {})
        ta, tb = a[i].get("trazabilidad", {}), b[i].get("trazabilidad", {})
        pares = [(c, fa.get(c), fb.get(c)) for c in FILA_CRITICOS] + [(c, ta.get(c), tb.get(c)) for c in TRAZ_CRITICOS]
        for campo, va, vb in pares:
            total += 1
            if _igual(va, vb):
                coincidencias += 1
            else:
                difs.append({"fila": i, "estudio": fa.get("Estudio"), "campo": campo, "a": va, "b": vb})
    return difs, coincidencias, total


# --------------------------------------------------------------------------- roles

def rol_extractor(ctx: dict[str, Any], modelo: str) -> list[dict[str, Any]]:
    d = ARTICULOS[ctx["articulo"]]
    base = ctx["libro"]["prompt_para_el_extractor"]
    base = (base.replace("Documento = <n>", f"Documento = {d['documento']}")
                .replace("Estudio inicial = <n>", f"Estudio inicial = {d['estudio']}")
                .replace("Covidence # = <n o vacío>", f"Covidence # = {d['covidence'] if d['covidence'] else 'vacío'}")
                .replace("Vía de identificación = <texto>", f"Vía de identificación = {d['via']}"))
    sistema = base + "\n\n" + REGLA_BLOQUES + "\n\nLIBRO DE CÓDIGOS (secciones normativas y contexto):\n" + ctx["libro_sistema"]
    reglas = ("Reglas no negociables:\n- Cada valor lleva página del PDF, ubicación y una cita literal y contigua de 25 "
              "palabras como máximo.\n- Nada de conocimiento externo: ni siglas, ni años, ni número de ítems, ni teorías "
              "que el artículo no diga.\n- Toda inferencia va a trazabilidad.inferencias y toda contradicción del "
              "artículo a discrepancias_en_el_articulo.\n- Si una regla del libro te obliga a escribir algo falso o no "
              "cubre el caso, no lo fuerces: repórtalo en trazabilidad.advertencias_pendientes.\n"
              "Responde únicamente con el arreglo JSON.")
    mensaje = (f"{reglas}\n\nImágenes de páginas con figuras o tablas en imagen: {ctx['imagenes'] or 'ninguna'}\n\n"
               f"TEXTO ETIQUETADO DEL ARTÍCULO:\n{ctx['etiquetado']}")
    trabajo: Path = ctx["trabajo"]
    salida = json_de(llamar("extractor", modelo, sistema, mensaje, trabajo, con_lectura=True, uso=ctx["uso"]))
    for it in range(1, MAX_ITERACIONES + 1):
        salida, anclas = separar_bloques(salida)
        ruta = trabajo / "salida.json"
        ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
        (trabajo / "anclas.json").write_text(json.dumps(anclas, ensure_ascii=False, indent=1), encoding="utf-8")
        errores, informe = validar(ruta, ctx["articulo"])
        (trabajo / f"validacion_{it}.txt").write_text(informe, encoding="utf-8")
        ctx["iteraciones_validador"] = it
        ctx["errores_validador"] = errores
        if errores == 0 or it == MAX_ITERACIONES:
            break
        correccion = (f"{mensaje}\n\nTU SALIDA ANTERIOR:\n{json.dumps(salida, ensure_ascii=False)}\n\n"
                      f"ERRORES DEL VALIDADOR (corrígelos sin inventar datos; conserva bloque_id en cada evidencia):\n"
                      f"{informe}\nResponde únicamente con el arreglo JSON corregido.")
        salida = json_de(llamar("extractor", modelo, sistema, correccion, trabajo, con_lectura=True, uso=ctx["uso"]))
    return salida


def rol_auditor(ctx: dict[str, Any], salida: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sistema = ("Eres el Agente Auditor de evidencia. No extraes: verificas. " + REGLA_BLOQUES +
               "\n\nLIBRO DE CÓDIGOS:\n" + ctx["libro_sistema"])
    mensaje = (
        "Para cada fila y cada columna con valor distinto de faltante:\n"
        "1. Comprueba en el texto etiquetado que la cita existe en la página citada y que sostiene el valor en esa "
        "columna. Para tablas, verifica la fila y la columna de la tabla. Para figuras y tablas en imagen, mira el PNG.\n"
        "2. Comprueba que la categoría cumple la instruccion_operativa de la columna.\n"
        "3. Comprueba que los faltantes (No indica, No aplica) son reales: busca en todo el artículo si el dato sí estaba.\n"
        "4. Comprueba que no se abrieron filas de más ni de menos según regla_para_abrir_una_fila_nueva.\n"
        "Veredictos por celda: CONFIRMADO, REFUTADO (con la evidencia correcta: página, bloque_id y cita) o NO VERIFICABLE "
        "(con el motivo). Responde únicamente con un arreglo JSON de objetos {estudio, columna, auditor: \"Auditor de "
        "evidencia\", veredicto, hallazgo, evidencia, resolucion: null, estado: \"Pendiente\"} solo con los veredictos "
        "distintos de CONFIRMADO. Sin elogios.\n\n"
        f"Imágenes: {ctx['imagenes'] or 'ninguna'}\n\nSALIDA A AUDITAR:\n{json.dumps(salida, ensure_ascii=False)}\n\n"
        f"TEXTO ETIQUETADO DEL ARTÍCULO:\n{ctx['etiquetado']}")
    r = json_de(llamar("auditor", MODELOS["auditor"], sistema, mensaje, ctx["trabajo"], con_lectura=True, uso=ctx["uso"]))
    return r if isinstance(r, list) else []


def rol_ciego(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    d = ARTICULOS[ctx["articulo"]]
    sistema = ("Eres el Codificador Ciego. No tienes acceso a otra extracción y no debes buscarla. " + REGLA_BLOQUES +
               "\n\nLIBRO DE CÓDIGOS:\n" + ctx["libro_sistema"])
    mensaje = (
        f"Datos del equipo: Documento = {d['documento']}, Estudio inicial = {d['estudio']}.\n"
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
        f"Imágenes: {ctx['imagenes'] or 'ninguna'}\n\nTEXTO ETIQUETADO DEL ARTÍCULO:\n{ctx['etiquetado']}")
    r = json_de(llamar("ciego", MODELOS["ciego"], sistema, mensaje, ctx["trabajo"], con_lectura=True, uso=ctx["uso"]))
    return r if isinstance(r, list) else []


def _bloques_citados(ctx: dict[str, Any], *fuentes: Any) -> str:
    ids = set(re.findall(r"p\d{2}-b\d{2}", json.dumps(fuentes, ensure_ascii=False)))
    return "\n".join(ctx["por_bloque"][i] for i in sorted(ids) if i in ctx["por_bloque"]) or "(sin bloques citados)"


def rol_conciliador(ctx: dict[str, Any], punto: dict[str, Any]) -> dict[str, Any]:
    campo = punto["campo"]
    regla = ctx["libro"]["columnas"].get(campo, {}).get("instruccion_operativa") or ctx["libro"]["trazabilidad_por_fila"]
    sistema = ("Eres el Conciliador. Decide usando solo el texto de los bloques que recibes. No uses conocimiento externo "
               "ni elijas por mayoría. Si el texto de los bloques no alcanza para decidir, responde PENDIENTE.")
    mensaje = (
        f"Celda: Estudio {punto.get('estudio')}, campo '{campo}'.\nValor del extractor: {json.dumps(punto.get('a'), ensure_ascii=False)}\n"
        f"Valor alternativo ({punto['origen']}): {json.dumps(punto.get('b'), ensure_ascii=False)}\n"
        f"Detalle: {json.dumps(punto.get('detalle'), ensure_ascii=False)}\n"
        f"Regla del libro: {json.dumps(regla, ensure_ascii=False)}\n\nBLOQUES:\n{punto['bloques']}\n\n"
        "Devuelve solo un objeto JSON: {\"decision\": \"VALOR_EXTRACTOR\" | \"VALOR_ALTERNATIVO\" | \"OTRO\" | \"PENDIENTE\", "
        "\"valor\": <valor final o null>, \"bloque_id\": \"<id>\", \"cita_textual\": \"<subcadena literal de 25 palabras como "
        "máximo>\", \"razonamiento\": \"<una o dos oraciones>\"}")
    try:
        r = json_de(llamar("conciliador", MODELOS["conciliador"], sistema, mensaje, ctx["trabajo"], con_lectura=False,
                           uso=ctx["uso"]))
    except (RuntimeError, json.JSONDecodeError) as e:
        r = {"decision": "PENDIENTE", "error": str(e)}
    return {**{k: v for k, v in punto.items() if k != "bloques"}, "conciliacion": r}


# --------------------------------------------------------------------------- principal

def preparar(articulo: str, modelo: str) -> dict[str, Any]:
    trabajo = SALIDA_BASE / f"{articulo}__{modelo}"
    trabajo.mkdir(parents=True, exist_ok=True)
    doc = normalizar((FIXTURES / "mineru" / f"{articulo}.zip").read_bytes())
    pdf = pymupdf.open(FIXTURES / f"{articulo}.pdf")
    etiquetado, por_bloque = texto_etiquetado(doc, pdf)
    (trabajo / "texto_etiquetado.txt").write_text(etiquetado, encoding="utf-8")
    imagenes = [p.name for p in renderizar_paginas(doc, pdf, trabajo)]
    libro = json.loads(LIBRO.read_text(encoding="utf-8"))
    return {"articulo": articulo, "trabajo": trabajo, "etiquetado": etiquetado, "por_bloque": por_bloque,
            "imagenes": ", ".join(imagenes), "libro": libro, "libro_sistema": libro_para_sistema(libro), "uso": []}


def verificado(articulo: str, libro: dict[str, Any]) -> list[dict[str, Any]]:
    if articulo == "kumar_2022":
        return list(libro["ejemplo_verificado"]["salida"])
    return list(json.loads((FIXTURES / "piloto_singh_2023_v21.json").read_text(encoding="utf-8")))


def guardar(ctx: dict[str, Any], nombre: str, datos: Any) -> None:
    (ctx["trabajo"] / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("articulo", choices=sorted(ARTICULOS))
    ap.add_argument("--modelo-extractor", default=MODELOS["extractor"])
    ap.add_argument("--solo-extractor", action="store_true")
    ap.add_argument("--sin-modelo", action="store_true", help="solo prepara el texto y prueba validador y comparación")
    a = ap.parse_args()
    ctx = preparar(a.articulo, a.modelo_extractor)
    ref = verificado(a.articulo, ctx["libro"])
    resumen: dict[str, Any] = {"articulo": a.articulo, "modelo_extractor": a.modelo_extractor,
                               "caracteres_etiquetado": len(ctx["etiquetado"]),
                               "caracteres_libro_sistema": len(ctx["libro_sistema"]), "imagenes": ctx["imagenes"]}
    if a.sin_modelo:
        ruta = ctx["trabajo"] / "verificado.json"
        ruta.write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
        resumen["errores_validador_verificado"] = validar(ruta, a.articulo)[0]
        difs, c, t = comparar(ref, ref)
        resumen["autocomparacion"] = f"{c}/{t}"
        print(json.dumps(resumen, ensure_ascii=False, indent=1))
        return

    salida = rol_extractor(ctx, a.modelo_extractor)
    difs_ref, c, t = comparar(salida, ref)
    guardar(ctx, "comparacion_verificado.json", {"coincidencias": c, "total": t, "diferencias": difs_ref})
    resumen |= {"filas": len(salida), "iteraciones_validador": ctx["iteraciones_validador"],
                "errores_validador": ctx["errores_validador"], "acuerdo_con_verificado": round(c / t, 3)}

    if not a.solo_extractor:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_aud = ex.submit(rol_auditor, ctx, salida)
            f_cie = ex.submit(rol_ciego, ctx)
            auditoria, ciega = f_aud.result(), f_cie.result()
        guardar(ctx, "auditoria_evidencia.json", auditoria)
        guardar(ctx, "codificacion_ciega.json", ciega)
        difs, c2, t2 = comparar(salida, ciega)
        resumen["acuerdo_extractor_ciego"] = round(c2 / t2, 3)
        puntos = [{**d, "origen": "Codificador ciego",
                   "bloques": _bloques_citados(ctx, salida[d["fila"]] if d.get("fila") is not None and d["fila"] < len(salida) else {},
                                               ciega[d["fila"]] if d.get("fila") is not None and d["fila"] < len(ciega) else {})}
                  for d in difs]
        puntos += [{"fila": None, "estudio": h.get("estudio"), "campo": h.get("columna"), "a": None,
                    "b": h.get("evidencia"), "detalle": h.get("hallazgo"), "origen": "Auditor de evidencia",
                    "bloques": _bloques_citados(ctx, h, salida)}
                   for h in auditoria if str(h.get("veredicto", "")).upper().startswith("REFUTADO")]
        guardar(ctx, "discrepancias.json", [{k: v for k, v in p.items() if k != "bloques"} for p in puntos])
        with ThreadPoolExecutor(max_workers=2) as ex:
            conciliacion = list(ex.map(lambda p: rol_conciliador(ctx, p), puntos))
        guardar(ctx, "conciliacion.json", conciliacion)
        resumen |= {"hallazgos_auditor": len(auditoria), "refutados": sum(1 for p in puntos if p["origen"] == "Auditor de evidencia"),
                    "discrepancias_ciego": len(difs), "conciliaciones": len(conciliacion)}

    with (ctx["trabajo"] / "uso.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ctx["uso"][0]))
        w.writeheader()
        w.writerows(ctx["uso"])
    por_rol: dict[str, dict[str, float]] = {}
    for u in ctx["uso"]:
        r = por_rol.setdefault(u["rol"], {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0, "costo_usd": 0.0})
        r["llamadas"] += 1
        r["tokens_entrada"] += u["input"] + u["cache_escritura"] + u["cache_lectura"]
        r["tokens_salida"] += u["output"]
        r["costo_usd"] = round(r["costo_usd"] + float(u["costo_usd"] or 0), 4)
    resumen["por_rol"] = por_rol
    resumen["costo_total_usd"] = round(sum(r["costo_usd"] for r in por_rol.values()), 4)
    guardar(ctx, "resumen.json", resumen)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

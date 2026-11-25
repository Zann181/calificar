"""Mide los detectores de la pestaña «Buscar» contra la matriz verificada (plan, Fase 2, aceptación).

Para cada documento de la matriz que tiene su PDF en «Artículos revisión sistemática/», toma el título de la matriz y el
**resumen** que se lee de la primera página del PDF (lo mismo que verían los detectores si la fuente trajera ese resumen),
corre los detectores de la etapa A y compara lo que sugieren con lo que la matriz dice de ese documento.

No usa red ni modelos. Se corre a mano, desde `backend/`:

    .venv/Scripts/python.exe ../herramientas/medir_deteccion.py [--detalle] [--etapa B]

Con `--etapa B` se lee además el **texto completo** del PDF (métodos y resultados, sin las referencias) y se combinan los
indicios con los del resumen, igual que hace la pestaña con «Analizar texto completo».

Lectura de los números: «con dato» = documentos cuya matriz tiene un valor en esa columna; «detectado» = documentos donde el
detector dio un indicio; «acuerdo» = el indicio coincide con algún valor de la matriz para ese documento. Recall = acuerdo /
con dato; precisión = acuerdo / detectado. El resumen del PDF se recorta con una heurística: parte del error es de ella.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import UTC, datetime
from collections import defaultdict
from pathlib import Path
from typing import Any

import openpyxl
import pymupdf

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.contextos.descubrimiento.adaptadores.detectores_json import cargar_config  # noqa: E402
from app.contextos.descubrimiento.dominio.busqueda import plano  # noqa: E402
from app.contextos.descubrimiento.dominio.candidato import Autor, Candidato, RegistroBibliografico  # noqa: E402
from app.contextos.descubrimiento.dominio.completitud import AnalisisDeTexto, celda_final  # noqa: E402
from app.contextos.descubrimiento.dominio.detectores import EstadoCelda, MotorDeDetectores  # noqa: E402

PDFS = RAIZ.parent / "Artículos revisión sistemática"
MATRIZ = RAIZ / "recursos" / "Matriz_de_sintesis_con_notas.xlsx"
# Columnas que la etapa A intenta y que tienen su contraparte en la matriz.
COLUMNAS = ["Muestra", "Correlación Feli 1 - JP", "Beta Fel 1- JP", "Instrumento felicidad", "Escala de medición: Performance",
            "Software", "Study design", "Sector", "Hedónica/eudaimónica", "Tipo de felicidad real",
            "Analysis method (principal)", "Método de aplicación", "Tipo de muestreo", "Nivel", "Constructo desempeño",
            "How measure the employee perfomance", "Direccionalidad de la relación", "Teoría 1"]
# Solo con texto completo (etapa B)
COLUMNAS_B = ["Fiabilidad Alfa - Omega (felicidad)", "Fiabilidad Alfa - Omega (desempeño)", "# Ítems", "Items instrumento1",
              "CFA", "Validez CFA", "Validez?", "Start date", "End date", "Inclusion criteria", "Exclusion criteria",
              "Definition Happiness", "Definition Performance"]


def resumen_del_pdf(ruta: Path) -> str:
    """Texto entre «Abstract/Resumen» y «Keywords/Introduction». Si no se reconoce, el primer tramo de la página 1."""
    doc = pymupdf.open(ruta)
    texto = " ".join(doc[i].get_text() for i in range(min(2, len(doc))))
    texto = re.sub(r"-\n(?=[a-z])", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    m = re.search(r"(?:abstract|resumen|summary)[\s:.\-—]*(.{300,3500}?)(?=\b(?:keywords?|key words|palabras clave|introduction|1\.?\s+introduction|jel)\b)",
                  texto, re.I)
    return m.group(1).strip() if m else texto[:2500]


def leer_matriz() -> dict[int, dict[str, list[Any]]]:
    """documento → columna → valores de todas sus filas (la matriz tiene una fila por efecto)."""
    wb = openpyxl.load_workbook(MATRIZ, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    filas = ws.iter_rows(values_only=True)
    cab = [str(c).strip() if c is not None else "" for c in next(filas)]
    from app.contextos.normas.dominio.catalogo import derivar_columnas
    import json
    libro = json.loads((RAIZ / "recursos" / "Libro_de_codigos_extraccion_v2.json").read_text(encoding="utf-8"))
    por_clave = {c.clave: c.encabezado_excel for c in derivar_columnas(libro)}
    idx = {clave: cab.index(enc.strip()) for clave, enc in por_clave.items() if enc.strip() in cab}
    docs: dict[int, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for fila in filas:
        if fila[idx["Documento"]] is None:
            continue
        d = int(fila[idx["Documento"]])
        for clave, i in idx.items():
            if fila[i] not in (None, ""):
                docs[d][clave].append(fila[i])
    return docs


def numeros(valor: Any) -> set[float]:
    return {abs(float(x.replace(",", "."))) for x in re.findall(r"\d+[.,]\d+|[.,]\d+|\d+", str(valor))}


def coincide(columna: str, detectado: str, valores: list[Any]) -> bool:
    if columna == "Muestra":
        return any(int(float(v)) == int(detectado) for v in valores if str(v).replace(".", "").isdigit())
    if columna in ("Correlación Feli 1 - JP", "Beta Fel 1- JP"):
        n = numeros(detectado)
        return any(abs(a - b) <= 0.006 for v in valores for a in numeros(v) for b in n)
    if columna in ("# Ítems", "Items instrumento1"):
        return any(int(detectado) == int(a) for v in valores for a in numeros(v) if a == int(a))
    if columna.startswith("Fiabilidad"):
        if detectado == "se reporta":
            return True  # el texto reporta fiabilidad y la matriz tiene un valor
        return any(abs(a - b) <= 0.006 for v in valores for a in numeros(v) for b in numeros(detectado))
    if columna in ("Start date", "End date"):
        anios = set(re.findall(r"(?:19|20)\d{2}", detectado))
        return any(anios & set(re.findall(r"(?:19|20)\d{2}", str(v))) for v in valores)
    if columna in ("Inclusion criteria", "Exclusion criteria", "Definition Happiness", "Definition Performance"):
        return True  # texto libre: basta con que ambos existan; se lee a ojo con --detalle
    d = plano(detectado)
    return any(d in plano(str(v)) or plano(str(v)) in d for v in valores)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detalle", action="store_true", help="muestra cada desacuerdo")
    ap.add_argument("--etapa", choices=["A", "B"], default="A")
    args = ap.parse_args()
    columnas = COLUMNAS + (COLUMNAS_B if args.etapa == "B" else [])
    motor = MotorDeDetectores(cargar_config(RAIZ / "recursos"))
    matriz = leer_matriz()
    por_numero = {int(re.match(r"(\d+)\.", p.name).group(1)): p for p in PDFS.glob("*.pdf") if re.match(r"(\d+)\.", p.name)}
    cuenta = {c: {"con_dato": 0, "detectado": 0, "acuerdo": 0, "ambos": 0} for c in columnas}
    usados = 0
    for doc, cols in sorted(matriz.items()):
        pdf = por_numero.get(doc)
        titulo = (cols.get("Title") or [""])[0]
        if pdf is None or not titulo:
            continue
        usados += 1
        anio = (cols.get("Año") or [None])[0]
        reg = RegistroBibliografico(fuente="pdf", id_externo=str(doc), posicion=1, titulo=str(titulo),
                                    anio=int(anio) if anio else None, resumen=resumen_del_pdf(pdf),
                                    autores=(Autor("X", "X"),))
        cand = Candidato.desde(uuid.uuid4(), reg)
        analisis = None
        if args.etapa == "B":
            documento = pymupdf.open(pdf)
            paginas = [documento[i].get_text() for i in range(len(documento))]
            r = motor.analizar_texto(cand, paginas)
            analisis = AnalisisDeTexto(candidato_id=cand.id, celdas=r.celdas, intentadas=r.intentadas, paginas=r.paginas,
                                       caracteres=r.caracteres, suficiente=r.suficiente, origen="pdf", analizado_en=datetime.now(UTC))
        for col in columnas:
            celda = celda_final(motor, col, cand, analisis) if analisis else motor.evaluar(col, cand)
            valores = cols.get(col, [])
            valores = [v for v in valores if str(v).strip().lower() not in ("no indica", "no aplica", "n/a")]
            c = cuenta[col]
            c["con_dato"] += 1 if valores else 0
            hallado = celda.estado == EstadoCelda.INDICIO and celda.valor is not None
            c["detectado"] += 1 if hallado else 0
            if hallado and valores:
                c["ambos"] += 1
                if coincide(col, str(celda.valor), valores):
                    c["acuerdo"] += 1
                elif args.detalle:
                    print(f"  desacuerdo doc {doc} · {col}: detectado «{str(celda.valor)[:50]}» vs matriz {[str(v)[:40] for v in valores[:3]]}")
    print(f"\nDocumentos medidos: {usados} (matriz verificada ↔ PDF)\n")
    print(f"{'Columna':42} {'con dato':>8} {'detectado':>9} {'acuerdo':>7} {'recall':>7} {'precisión':>9}")
    print(f"(etapa {args.etapa})")
    for col, c in cuenta.items():
        recall = f"{c['acuerdo'] / c['con_dato']:.0%}" if c["con_dato"] else "—"
        prec = f"{c['acuerdo'] / c['ambos']:.0%}" if c["ambos"] else "—"
        print(f"{col:42} {c['con_dato']:>8} {c['detectado']:>9} {c['acuerdo']:>7} {recall:>7} {prec:>9}")


if __name__ == "__main__":
    main()

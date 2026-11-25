"""Exportar la selección: CSV (para Excel) y RIS (para Zotero, EndNote, Mendeley). Solo texto: sin red ni modelos."""

from __future__ import annotations

import csv
import io

from app.contextos.descubrimiento.dominio.candidato import Candidato
from app.contextos.descubrimiento.dominio.completitud import Evaluacion


def a_csv(filas: list[tuple[Candidato, Evaluacion | None]], columnas: list[str]) -> str:
    """Una fila por candidato; por cada columna elegida, su valor sugerido y su estado. Con BOM para que Excel lea la ñ."""
    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\r\n")
    cabecera = ["Título", "Autores", "Año", "Revista", "DOI", "Fuentes", "Texto abierto", "Estado", "Ya en la matriz",
                "Puntaje", "Etiqueta"]
    for col in columnas:
        cabecera += [col, f"{col} [estado]"]
    w.writerow(cabecera)
    for c, ev in filas:
        fila = [c.titulo, "; ".join(a.nombre for a in c.autores), c.anio or "", c.revista, c.doi or "",
                ", ".join(c.fuentes), c.url_oa or "", c.estado.value, "sí" if c.en_matriz else "no",
                f"{round(ev.puntaje * 100)}%" if ev else "", ev.etiqueta.value if ev else ""]
        por_columna = {cel.columna: cel for cel in ev.celdas} if ev else {}
        for col in columnas:
            cel = por_columna.get(col)
            fila += [cel.valor or "" if cel else "", cel.estado.value if cel else ""]
        w.writerow(fila)
    return "﻿" + salida.getvalue()


def a_ris(candidatos: list[Candidato]) -> str:
    lineas: list[str] = []
    for c in candidatos:
        lineas.append("TY  - " + ("UNPB" if c.es_preprint else "JOUR"))
        lineas.append(f"TI  - {c.titulo}")
        lineas += [f"AU  - {a.nombre}" for a in c.autores]
        if c.anio:
            lineas.append(f"PY  - {c.anio}")
        if c.revista:
            lineas.append(f"JO  - {c.revista}")
        if c.doi:
            lineas.append(f"DO  - {c.doi}")
        if c.resumen:
            lineas.append(f"AB  - {c.resumen}")
        lineas += [f"KW  - {k}" for k in c.palabras_clave]
        if c.idioma:
            lineas.append(f"LA  - {c.idioma}")
        if c.url_oa:
            lineas.append(f"UR  - {c.url_oa}")
        lineas.append("ER  - ")
        lineas.append("")
    return "\r\n".join(lineas)

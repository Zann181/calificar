"""Lector de la matriz vigente en Excel (openpyxl).

- Hoja: la que tiene en la fila 1 los encabezados del catálogo en sus posiciones.
- Fila de datos: la que tiene algún valor en las columnas del catálogo.
- Los valores se toman tal cual; las fechas se guardan como {"$fecha": "AAAA-MM-DDTHH:MM:SS"}
  para que la exportación las devuelva como fecha y la ida y vuelta sea exacta.
- Los comentarios de celda (notas heredadas) se conservan con autor y texto.
"""

from __future__ import annotations

import io
from datetime import date, datetime, time
from typing import Any

import openpyxl

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio
from app.contextos.matriz.puertos import FilaLeida, MatrizLeida, NotaDeCelda

MARCA_FECHA = "$fecha"


def a_json(valor: Any) -> Any:
    if isinstance(valor, datetime | date | time):
        return {MARCA_FECHA: valor.isoformat()}
    return valor


def desde_json(valor: Any) -> Any:
    if isinstance(valor, dict) and MARCA_FECHA in valor:
        return datetime.fromisoformat(valor[MARCA_FECHA])
    return valor


class EncabezadosNoCoinciden(ErrorDeDominio):
    pass


def encontrar_hoja(wb: Any, columnas: list[DefinicionDeColumna]) -> Any:
    for ws in wb.worksheets:
        if all(ws.cell(1, c.posicion).value == c.encabezado_excel for c in columnas):
            return ws
    diferencias = []
    ws = wb.worksheets[0]
    for c in columnas:
        v = ws.cell(1, c.posicion).value
        if v != c.encabezado_excel:
            diferencias.append(f"{c.letra}: se esperaba {c.encabezado_excel!r} y hay {v!r}")
    raise EncabezadosNoCoinciden("Ninguna hoja tiene los encabezados del libro de códigos. "
                                 + "; ".join(diferencias[:8]))


class LectorExcel:
    def leer(self, datos: bytes, columnas: list[DefinicionDeColumna]) -> MatrizLeida:
        wb = openpyxl.load_workbook(io.BytesIO(datos))
        ws = encontrar_hoja(wb, columnas)
        posiciones = [c.posicion for c in columnas]
        filas: list[FilaLeida] = []
        for r in range(2, ws.max_row + 1):
            celdas = {p: ws.cell(r, p) for p in posiciones}
            if all(c.value is None for c in celdas.values()):
                continue
            filas.append(FilaLeida(
                fila_excel=r,
                valores={p: a_json(c.value) for p, c in celdas.items()},
                notas={p: NotaDeCelda(autor=c.comment.author, texto=c.comment.text)
                       for p, c in celdas.items() if c.comment is not None},
            ))
        return MatrizLeida(hoja=ws.title, filas=filas)

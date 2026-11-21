"""Aceptación de F1: importar y exportar la matriz de 71 filas da los mismos valores celda por celda."""

from __future__ import annotations

import io
import uuid

import openpyxl
import pytest

from app.composicion import Contenedor
from app.contextos.matriz.aplicacion.casos_de_uso import MatrizNoVacia
from app.contextos.matriz.dominio.fila import Origen
from tests.conftest import MATRIZ

HOJA = "Extracción completa.csv"


def test_importar_71_filas_con_25_notas(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    r = contenedor.matriz.importar.ejecutar(proyecto, MATRIZ.read_bytes(), MATRIZ.name)
    assert (r.filas, r.documentos, r.notas_heredadas) == (71, 47, 25)
    filas = contenedor.matriz.consultas.todas(proyecto)
    assert [f.estudio for f in filas] == list(range(1, 72))
    assert all(f.origen == Origen.HEREDADA for f in filas)
    kumar = contenedor.matriz.consultas.fila(proyecto, 1)
    assert kumar.valores()["Correlación Feli 1 - JP"] == 0.73
    assert sum(len(f.trazabilidad["notas_heredadas"]) for f in filas) == 25


def test_ida_y_vuelta_celda_por_celda(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    original = MATRIZ.read_bytes()
    contenedor.matriz.importar.ejecutar(proyecto, original, MATRIZ.name)
    exportacion = contenedor.exportar.ejecutar(proyecto)
    assert (exportacion.filas_heredadas, exportacion.filas_extraidas) == (71, 0)
    exportado = contenedor.exportar.leer(proyecto, exportacion.id)

    a = openpyxl.load_workbook(io.BytesIO(original))
    b = openpyxl.load_workbook(io.BytesIO(exportado))
    assert a.sheetnames == b.sheetnames
    wa, wb = a[HOJA], b[HOJA]
    columnas = contenedor.normas.consultas.columnas(proyecto)
    diferencias = []
    celdas = 0
    for fila in range(1, wa.max_row + 1):
        for c in columnas:
            x, y = wa.cell(fila, c.posicion), wb.cell(fila, c.posicion)
            celdas += 1
            if x.value != y.value:
                diferencias.append((fila, c.clave, x.value, y.value))
            if (x.comment and x.comment.text) != (y.comment and y.comment.text):
                diferencias.append((fila, c.clave, "comentario"))
    assert celdas >= 72 * 59
    # Lo único que cambia son las 5 columnas que agregó el libro v2.3 (encabezado y, en las derivadas, el valor
    # calculado); el Excel importado no las trae. Los datos y las notas de las 54 originales vuelven idénticos.
    nuevas = {c.clave for c in columnas if c.agregada_en_version}
    assert len(nuevas) == 5
    assert [d for d in diferencias if d[1] not in nuevas] == []
    assert {(d[0], d[1]) for d in diferencias if d[0] == 1} == {(1, k) for k in nuevas}


def test_reimportar_exige_reemplazar(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    datos = MATRIZ.read_bytes()
    contenedor.matriz.importar.ejecutar(proyecto, datos, MATRIZ.name)
    with pytest.raises(MatrizNoVacia):
        contenedor.matriz.importar.ejecutar(proyecto, datos, MATRIZ.name)
    r = contenedor.matriz.importar.ejecutar(proyecto, datos, MATRIZ.name, reemplazar=True)
    assert r.reemplazadas == 71
    assert len(contenedor.matriz.consultas.todas(proyecto)) == 71


def test_exportar_sin_importar(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    with pytest.raises(LookupError, match="importe la matriz"):
        contenedor.exportar.ejecutar(proyecto)


def test_migrar_al_libro_nuevo_agrega_las_5_columnas_a_filas_ya_guardadas(contenedor: Contenedor) -> None:
    """Base creada con el libro v2.2 (54 columnas) y luego libro v2.3: la migración agrega 5 celdas por fila,
    calcula las derivables sin leer PDF y es idempotente."""
    import json

    from tests.conftest import LIBRO, LIBRO_V22
    from tests.integracion.conftest import nuevo_proyecto

    pid = nuevo_proyecto(contenedor, "Migración")
    contenedor.normas.publicar.ejecutar(pid, json.loads(LIBRO_V22.read_text(encoding="utf-8")))
    ctx = contenedor.normas.consultas
    assert len(ctx.columnas(pid)) == 54
    contenedor.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    assert "Cultura Hofstede" not in contenedor.matriz.consultas.fila(pid, 1).celdas

    contenedor.normas.publicar.ejecutar(pid, json.loads(LIBRO.read_text(encoding="utf-8")))
    r = contenedor.matriz.agregar_columnas.ejecutar(pid)
    assert (r.filas, r.celdas_agregadas) == (71, 71 * 5)
    assert r.calculadas == 71 * 2  # ID muestra y Cultura Hofstede; el resto necesita leer el PDF

    filas = contenedor.matriz.consultas.todas(pid)
    for f in filas:
        v = f.valores()
        assert v["ID muestra"] == f"D{f.documento}-M1"
        assert v["Cultura Hofstede"] in ("Individualista", "Colectivista")
        assert v["Método obtención r"] is None and v["Constructo desempeño"] is None and v["Conjunto MA"] is None
    kumar = contenedor.matriz.consultas.fila(pid, 1)
    assert kumar.celda("Cultura Hofstede").inferencia is not None  # explica de dónde sale

    assert contenedor.matriz.agregar_columnas.ejecutar(pid).celdas_agregadas == 0  # idempotente

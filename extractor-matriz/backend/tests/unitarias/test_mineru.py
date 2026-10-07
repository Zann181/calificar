"""Normalización de la salida de MinerU (ADR 0001) con las salidas guardadas de Kumar y Singh."""

from __future__ import annotations

import json
import re
import zipfile

import pytest

from app.contextos.biblioteca.adaptadores.mineru import (
    ESCALA_CONTENT_LIST,
    ErrorDeConversion,
    normalizar,
    tabla_desde_html,
)
from app.contextos.biblioteca.dominio.documento import DocumentoEstructurado
from tests.conftest import FIXTURES

ZIPS = {"kumar_2022": 8, "singh_2023": 18}


def _crudo(nombre: str) -> bytes:
    return (FIXTURES / "mineru" / f"{nombre}.zip").read_bytes()


@pytest.mark.parametrize("nombre,paginas", ZIPS.items())
def test_paginas_y_ids(nombre: str, paginas: int) -> None:
    doc = normalizar(_crudo(nombre))
    assert len(doc.paginas) == paginas
    ids = [b.id for b in doc.bloques]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"p\d{2}-b\d{2}", i) for i in ids)
    assert all(b.id.startswith(f"p{b.pagina:02d}-") for b in doc.bloques)


@pytest.mark.parametrize("nombre", ZIPS)
def test_ids_estables(nombre: str) -> None:
    a, b = normalizar(_crudo(nombre)), normalizar(_crudo(nombre))
    assert [x.id for x in a.bloques] == [x.id for x in b.bloques]
    assert a.a_dict() == b.a_dict()


def test_formula_de_coordenadas_del_adr_0001() -> None:
    crudo = _crudo("kumar_2022")
    with zipfile.ZipFile(__import__("io").BytesIO(crudo)) as z:
        primero = json.loads(z.read("content_list.json"))[0]
        ancho, alto = json.loads(z.read("middle.json"))["pdf_info"][0]["page_size"]
    b = normalizar(crudo).bloques[0]
    x0, y0, x1, y1 = primero["bbox"]
    esperado = [round(x0 / ESCALA_CONTENT_LIST * ancho, 2), round(y0 / ESCALA_CONTENT_LIST * alto, 2),
                round(x1 / ESCALA_CONTENT_LIST * ancho, 2), round(y1 / ESCALA_CONTENT_LIST * alto, 2)]
    assert b.rect.a_lista() == esperado
    assert b.pagina == primero["page_idx"] + 1


def test_rectangulos_dentro_de_la_pagina() -> None:
    doc = normalizar(_crudo("singh_2023"))
    for b in doc.bloques:
        p = doc.pagina(b.pagina)
        assert p is not None
        x0, y0, x1, y1 = b.rect.a_lista()
        assert 0 <= x0 <= x1 <= p.ancho_pt + 1
        assert 0 <= y0 <= y1 <= p.alto_pt + 1


def test_tabla_1_de_kumar_con_etiquetas() -> None:
    doc = normalizar(_crudo("kumar_2022"))
    tabla = next(b for b in doc.bloques if b.tipo == "tabla")
    assert tabla.tabla is not None and not tabla.tabla.es_imagen
    celda = next(c for c in tabla.tabla.celdas if c.etiqueta_fila == "SWB" and c.etiqueta_columna == "JP")
    assert celda.texto == ".73**"


def test_documento_ida_y_vuelta_por_dict() -> None:
    doc = normalizar(_crudo("kumar_2022"))
    assert DocumentoEstructurado.desde_dict(doc.a_dict()).a_dict() == doc.a_dict()


def test_html_con_rowspan_y_colspan() -> None:
    html = ("<table><tr><th>V</th><th colspan='2'>Grupo</th></tr>"
            "<tr><td rowspan='2'>A</td><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></table>")
    t = tabla_desde_html(html)
    valores = {(c.fila, c.columna): (c.etiqueta_fila, c.etiqueta_columna, c.texto) for c in t.celdas}
    assert valores[(2, 1)] == ("A", "Grupo", "3")
    assert valores[(1, 2)] == ("A", "Grupo", "2")


def test_tabla_sin_html_es_imagen() -> None:
    assert tabla_desde_html(None).es_imagen
    assert tabla_desde_html("<img src='x'>").es_imagen


def test_zip_incompleto() -> None:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content_list.json", "[]")
    with pytest.raises(ErrorDeConversion):
        normalizar(buf.getvalue())

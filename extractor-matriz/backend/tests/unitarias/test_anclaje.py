"""Algoritmo de anclaje (sección 8.4) y texto etiquetado (sección 8.1)."""

from __future__ import annotations

from typing import Any

import pytest

from app.contextos.extraccion.dominio.anclaje import Ancla, Anclador, NivelAncla, nivel_mas_bajo
from app.contextos.extraccion.dominio.documento import DocumentoDeTrabajo
from app.contextos.extraccion.dominio.etiquetado import necesita_capa, sin_escapes, texto_etiquetado


def _bloque(id_: str, tipo: str, texto: str, tabla: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": id_, "pagina": int(id_[1:3]), "tipo": tipo, "rect": [10, 20, 300, 80], "texto": texto,
            "tabla": tabla}


@pytest.fixture
def doc() -> DocumentoDeTrabajo:
    return DocumentoDeTrabajo.desde_dict({"bloques": [
        _bloque("p03-b01", "parrafo", "The study is based on a sample of 395 teachers working for private institutions."),
        _bloque("p03-b02", "parrafo", "Job satisfaction was measured with three items."),
        _bloque("p03-b03", "tabla", "Table 1 Correlations\nSWB .73**\nNote: ** p<.01", {
            "html": "<table>...</table>", "es_imagen": False, "filas_grilla": ["SWB .73**"],
            "celdas": [{"fila": 1, "columna": 1, "texto": ".73**", "etiqueta_fila": "SWB", "etiqueta_columna": "JP"}]}),
        _bloque("p04-b01", "parrafo", "Results revealed that satisfied teachers perform better than others do."),
        _bloque("p05-b01", "figura", ""),
        _bloque("p05-b02", "parrafo", ""),  # H1: MinerU lo dejó vacío
        _bloque("p05-b03", "parrafo", "path $( \\mathrm { b } { = } 0 . 5 1 0 ,$ significant"),  # H3
    ]})


def _ev(cita: str, bloque: str | None, pagina: int = 3, **extra: Any) -> dict[str, Any]:
    return {"pagina_pdf": pagina, "ubicacion": "x", "cita_textual": cita, "bloque_id": bloque, **extra}


def test_cita_en_el_bloque_citado_queda_verificada_con_rango(doc: DocumentoDeTrabajo) -> None:
    a = Anclador(doc).anclar(_ev("sample of 395 teachers", "p03-b01"), estudio=1, columna="Muestra", indice=0)
    assert a.nivel == NivelAncla.VERIFICADA
    assert a.bloque_id == "p03-b01" and a.pagina == 3 and a.rect == (10, 20, 300, 80)
    assert a.rango is not None
    texto = doc.bloque("p03-b01").texto_norm  # type: ignore[union-attr]
    assert texto[a.rango[0]:a.rango[1]] == "sample of 395 teachers"


def test_celda_de_tabla_por_etiquetas(doc: DocumentoDeTrabajo) -> None:
    e = _ev(".73**", "p03-b03", fila_tabla="SWB", columna_tabla="JP")
    a = Anclador(doc).anclar(e, estudio=1, columna="Correlación Feli 1 - JP", indice=0)
    assert (a.nivel, a.nota) == (NivelAncla.VERIFICADA, "celda de tabla")


def test_cita_en_otro_bloque_se_corrige(doc: DocumentoDeTrabajo) -> None:
    a = Anclador(doc).anclar(_ev("measured with three items", "p03-b01"), estudio=1, columna="# Ítems", indice=0)
    assert a.nivel == NivelAncla.VERIFICADA_CON_CORRECCION
    assert a.bloque_id == "p03-b02"


def test_bloque_inexistente_busca_en_todo_el_documento(doc: DocumentoDeTrabajo) -> None:
    a = Anclador(doc).anclar(_ev("satisfied teachers perform better", "p99-b99", 4), estudio=1, columna="X", indice=0)
    assert a.nivel == NivelAncla.VERIFICADA_CON_CORRECCION and a.bloque_id == "p04-b01"


def test_coincidencia_aproximada_en_paginas_adyacentes_queda_por_confirmar(doc: DocumentoDeTrabajo) -> None:
    e = _ev("Results revealed that satisfied teachers perfom better", "p04-b01", 4)  # errata del modelo
    a = Anclador(doc, umbral_similitud=90).anclar(e, estudio=1, columna="X", indice=0)
    assert a.nivel == NivelAncla.POR_CONFIRMAR and a.bloque_id == "p04-b01" and a.similitud >= 90


def test_leido_de_figura_queda_por_confirmar(doc: DocumentoDeTrabajo) -> None:
    a = Anclador(doc).anclar(_ev("0.287", "p05-b01", 5, leido_de_figura=True), estudio=1, columna="Beta", indice=0)
    assert a.nivel == NivelAncla.POR_CONFIRMAR and a.leido_de_figura


def test_cita_inexistente_no_es_verificable(doc: DocumentoDeTrabajo) -> None:
    a = Anclador(doc).anclar(_ev("a quote that is nowhere in this paper at all", "p03-b01"), estudio=1,
                             columna="X", indice=0)
    assert a.nivel == NivelAncla.NO_VERIFICABLE


def test_texto_de_capa_tambien_ancla(doc: DocumentoDeTrabajo) -> None:
    """H1 y H3: el texto que vio el modelo (capa del PDF) sirve para anclar."""
    capa = {"p05-b02": "continues on page five with N = 219", "p05-b03": "path (b = 0.510, p < 0.001) significant"}
    et = texto_etiquetado(doc, capa)
    anclador = Anclador(doc, et.efectivo_norm)
    for cita, bloque in (("N = 219", "p05-b02"), ("(b = 0.510, p < 0.001)", "p05-b03")):
        a = anclador.anclar(_ev(cita, bloque, 5), estudio=1, columna="X", indice=0)
        assert (a.nivel, a.bloque_id) == (NivelAncla.VERIFICADA, bloque)


def test_anclar_salida_recorre_filas_columnas_y_evidencias(doc: DocumentoDeTrabajo) -> None:
    salida = [{"fila": {"Estudio": 7}, "trazabilidad": {"evidencia": {
        "Muestra": [_ev("sample of 395 teachers", "p03-b01"), _ev("nowhere to be found in the text", "p03-b01")]}}}]
    anclas = Anclador(doc).anclar_salida(salida)
    assert [(a.estudio, a.columna, a.indice_evidencia, a.nivel) for a in anclas] == [
        (7, "Muestra", 0, NivelAncla.VERIFICADA), (7, "Muestra", 1, NivelAncla.NO_VERIFICABLE)]
    assert nivel_mas_bajo([a.nivel for a in anclas]) == NivelAncla.NO_VERIFICABLE
    assert Ancla.desde_dict(anclas[0].a_dict()) == anclas[0]


def test_texto_etiquetado_formato_seccion_8_1(doc: DocumentoDeTrabajo) -> None:
    et = texto_etiquetado(doc, {"p05-b02": "texto de la capa"})
    lineas = et.texto.split("\n")
    assert lineas[0] == "[p03-b01 | parrafo] The study is based on a sample of 395 teachers working for private institutions."
    assert '[p03-b03 | tabla | Tabla 1] leyenda: Table 1 Correlations' in lineas
    assert '[p03-b03 | tabla | Tabla 1] fila "SWB" | columna "JP" = ".73**"' in lineas
    assert '[p03-b03 | tabla | Tabla 1] nota: Note: ** p<.01' in lineas
    assert "[p05-b01 | figura | imagen] (sin texto) (ver página 5 en PNG)" in lineas
    assert "[p05-b02 | parrafo] texto de la capa" in lineas
    assert not any(ln.startswith("[p05-b03") for ln in lineas)  # LaTeX sin capa: se omite
    assert doc.paginas_con_imagen() == [5]


def test_necesita_capa_y_escapes(doc: DocumentoDeTrabajo) -> None:
    assert [b.id for b in doc.bloques if necesita_capa(b)] == ["p05-b02", "p05-b03"]
    assert sin_escapes(r"\*\* p<.001 cr\_fdh") == "** p<.001 cr_fdh"

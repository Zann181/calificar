"""Descubrimiento · utilidades de texto de los adaptadores."""

from __future__ import annotations

from app.contextos.descubrimiento.adaptadores.fuentes._comun import (
    apellido_de,
    entero_o_none,
    quitar_etiquetas,
)


def test_quita_etiquetas_html_y_jats() -> None:
    assert quitar_etiquetas("<jats:p>Hola <b>mundo</b> &amp; todos</jats:p>") == "Hola mundo & todos"
    assert quitar_etiquetas(None) == ""


def test_no_borra_comparaciones_estadisticas() -> None:
    assert quitar_etiquetas("r = .31, p < .001 y luego p > .05") == "r = .31, p < .001 y luego p > .05"


def test_apellido_y_anio() -> None:
    assert apellido_de("Selin Kalender") == "Kalender" and apellido_de("") == ""
    assert entero_o_none("2026 Jun") == 2026 and entero_o_none(None) is None


def test_titulos_con_html_escapado_de_europepmc_quedan_limpios() -> None:
    assert quitar_etiquetas("&lt;i&gt;After I stayed there&lt;/i&gt;: views") == "After I stayed there: views"
    assert quitar_etiquetas("Title with <i>emphasis</i>.").rstrip(".") == "Title with emphasis"


def test_los_saltos_de_linea_y_parrafos_separan_palabras() -> None:
    assert quitar_etiquetas("uno<br>dos<p>tres</p>") == "uno dos tres"

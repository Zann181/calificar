"""norm() del núcleo es idéntica a la de recursos/validar_extraccion.py (sobre 50 cadenas)."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable

import pytest

from app.compartido.normalizacion import norm
from tests.conftest import RECURSOS


def _norm_del_validador() -> Callable[[str], str]:
    spec = importlib.util.spec_from_file_location("validar_extraccion", RECURSOS / "validar_extraccion.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    funcion: Callable[[str], str] = modulo.norm
    return funcion


CADENAS = [
    "", " ", "Hola", "  dos   espacios  ", "línea\nnueva", "tab\tuado", "well-\nbeing", "JP – Job Performance",
    "JS − Job Satisfaction", "em—dash", "‘comillas’ simples", "“comillas” dobles", "teachers’ job", "ﬁ ligadura",
    "ﬀective", "N = 219", "N = 219", "(β = .287, p < .001)", "r = .73**", "Cronbach's α = .90",
    "MAYÚSCULAS Y Tildes", "Ñandú", "ÅNGSTRÖM", "１２３ ancho completo", "x²", "H₁", "½ medio", "…", "a...b",
    "Table 1\nDescriptive statistics", "  \n\n  ", "0,87", "-0.380**", "p<.05", "SWB → JP", "«angulares»",
    "non-\nsignificant", "e-mail", "co–author", " espacio duro ", "Œuvre", "ǅ", "ﬃ ﬄ", "℃", "№ 5",
    "Ⅳ capítulo", "مرحبا", "日本語テキスト", "Ελληνικά", "Пример",
]


def test_hay_50_cadenas() -> None:
    assert len(CADENAS) == 50


@pytest.mark.parametrize("texto", CADENAS)
def test_misma_norm_que_el_validador(texto: str) -> None:
    assert norm(texto) == _norm_del_validador()(texto)

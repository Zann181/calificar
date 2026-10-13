"""ScriptValidador con el validar_extraccion.py real: V23 compara contra el texto que se le pasa (H7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contextos.extraccion.adaptadores import validador as v
from tests.conftest import RECURSOS

SCRIPT = RECURSOS / "validar_extraccion.py"


def test_sin_script_falla_antes_de_validar(tmp_path: Path) -> None:
    with pytest.raises(v.ErrorDelValidador, match="validador"):
        v.ScriptValidador(tmp_path / "validar.py").comprobar()


def test_v23_busca_la_cita_en_el_texto_del_documento() -> None:
    libro = json.loads((RECURSOS / "Libro_de_codigos_extraccion_v2.json").read_text(encoding="utf-8"))
    salida = libro["ejemplo_verificado"]["salida"]
    citas = [e["cita_textual"] for item in salida for lst in item["trazabilidad"]["evidencia"].values() for e in lst
             if not e["leido_de_figura"]]
    validador = v.ScriptValidador(SCRIPT)
    assert not [e for e in validador.validar(salida, libro, "\n".join(citas)).errores if "[V23]" in e]
    errores = validador.validar(salida, libro, "texto que no contiene ninguna cita").errores
    assert any("[V23]" in e and "no se encuentra literal" in e for e in errores)


def test_sin_cortes_une_palabras_partidas_como_el_validador() -> None:
    from app.contextos.extraccion.dominio.etiquetado import sin_cortes

    assert sin_cortes("the longitudinal facto-\nrial invariance\n[113]") == "the longitudinal factorial invariance [113]"

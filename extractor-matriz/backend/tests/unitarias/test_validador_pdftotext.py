from __future__ import annotations

from pathlib import Path

import pytest

from app.contextos.extraccion.adaptadores import validador as v


def test_sin_pdftotext_falla_antes_de_validar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(v, "buscar_pdftotext", lambda configurado="": None)
    with pytest.raises(v.ErrorDelValidador, match="pdftotext"):
        v.ScriptValidador(tmp_path / "validar.py").comprobar()


def test_pdftotext_configurado_inexistente_no_se_encuentra() -> None:
    assert v.buscar_pdftotext("no-existe-pdftotext-xyz") is None


def test_sin_cortes_une_palabras_partidas_como_el_validador() -> None:
    from app.contextos.extraccion.dominio.etiquetado import sin_cortes

    assert sin_cortes("the longitudinal facto-\nrial invariance\n[113]") == "the longitudinal factorial invariance [113]"

"""AlmacenEnDisco: guarda y lee bajo su carpeta raíz, nunca fuera de ella."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnDisco


def test_guardar_y_leer(tmp_path: Path) -> None:
    a = AlmacenEnDisco(tmp_path / "almacen")
    a.guardar("pdf/p1/abc.pdf", b"%PDF", "application/pdf")
    assert a.existe("pdf/p1/abc.pdf")
    assert a.leer("pdf/p1/abc.pdf") == b"%PDF"
    assert not a.existe("pdf/p1/otro.pdf")


@pytest.mark.parametrize("clave", ["../fuera.txt", "pdf/../../fuera.txt"])
def test_clave_fuera_del_almacen(tmp_path: Path, clave: str) -> None:
    a = AlmacenEnDisco(tmp_path / "almacen")
    with pytest.raises(ValueError):
        a.guardar(clave, b"x", "text/plain")

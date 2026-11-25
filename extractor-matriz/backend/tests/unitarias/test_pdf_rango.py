"""entregar_pdf: soporte de `Range` para pdf.js (un solo tramo)."""

from __future__ import annotations

import pytest

from app.contextos.biblioteca.api import entregar_pdf

DATOS = bytes(range(256)) * 4  # 1024 bytes


def test_sin_range_entrega_todo() -> None:
    r = entregar_pdf(DATOS, None)
    assert r.status_code == 200 and r.body == DATOS
    assert r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize(("rango", "desde", "hasta"), [
    ("bytes=0-9", 0, 9), ("bytes=10-", 10, 1023), ("bytes=-5", 1019, 1023), ("bytes=1000-5000", 1000, 1023),
])
def test_un_tramo(rango: str, desde: int, hasta: int) -> None:
    r = entregar_pdf(DATOS, rango)
    assert r.status_code == 206 and r.body == DATOS[desde:hasta + 1]
    assert r.headers["content-range"] == f"bytes {desde}-{hasta}/1024"


@pytest.mark.parametrize("rango", ["bytes=2000-3000", "bytes=9-3"])
def test_fuera_de_rango(rango: str) -> None:
    r = entregar_pdf(DATOS, rango)
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */1024"


@pytest.mark.parametrize("rango", ["bytes=a-b", "items=0-5", "bytes=0-5,10-15"])
def test_rangos_no_soportados_devuelven_todo(rango: str) -> None:
    r = entregar_pdf(DATOS, rango)
    assert r.status_code == 200 and r.body == DATOS

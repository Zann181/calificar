"""Configuración del modo nube (ADR 0009)."""

from __future__ import annotations

import pytest

from app.config import Settings


@pytest.mark.parametrize("url", [
    "postgresql://u:p%40ss@ep-x-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require",
    "postgres://u:p%40ss@ep-x-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require",
])
def test_url_de_neon_se_convierte_al_controlador_psycopg(url: str) -> None:
    ajustes = Settings(_env_file=None, database_url=url)
    assert ajustes.database_url == "postgresql+psycopg://u:p%40ss@ep-x-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"


@pytest.mark.parametrize("url", ["sqlite:///datos/extractor.db", "postgresql+psycopg://u:p@localhost/db"])
def test_otras_urls_no_se_tocan(url: str) -> None:
    assert Settings(_env_file=None, database_url=url).database_url == url


def test_modo_por_defecto_es_local() -> None:
    ajustes = Settings(_env_file=None)
    assert ajustes.modo == "local" and not ajustes.almacen_en_base


def test_modo_invalido_se_rechaza() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, modo="otro")  # type: ignore[arg-type]

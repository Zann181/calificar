"""Entorno de Alembic: toma los metadatos de todas las tablas de los contextos."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importar los módulos que declaran tablas registra cada tabla en Base.metadata.
import app.contextos.biblioteca.adaptadores.tablas  # noqa: F401
import app.contextos.extraccion.adaptadores.repositorio_sql  # noqa: F401
import app.contextos.matriz.adaptadores.repositorio_sql  # noqa: F401
import app.contextos.normas.adaptadores.repositorio_sql  # noqa: F401
from app.compartido.db import Base
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = context.get_x_argument(as_dictionary=True).get("url") or settings().database_url
config.set_main_option("sqlalchemy.url", url)
metadatos = Base.metadata


def sin_conexion() -> None:
    context.configure(url=url, target_metadata=metadatos, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def con_conexion() -> None:
    motor = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                               poolclass=pool.NullPool)
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=metadatos, compare_type=True,
                          render_as_batch=conexion.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    sin_conexion()
else:
    con_conexion()

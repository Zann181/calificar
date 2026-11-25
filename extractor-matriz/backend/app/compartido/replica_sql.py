"""Serialización de registros SQLAlchemy a «datos» de un sobre y de vuelta (ADR 0009).

Todas las columnas viajan tal como están, salvo las binarias y las que se excluyen. Las fechas se normalizan a UTC y
los UUID a texto, para que el mismo contenido dé el mismo hash en SQLite (local) y en PostgreSQL (nube).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, LargeBinary, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Uuid

from app.compartido.db import Base, RegistroProyecto
from app.compartido.sobre import Sobre, hash_de


def _columnas(clase: type[Base], excluir: Iterable[str]) -> list[tuple[str, Any]]:
    omitir = set(excluir)
    return [(a.key, a.columns[0]) for a in inspect(clase).column_attrs
            if a.key not in omitir and not isinstance(a.columns[0].type, LargeBinary)]


def _a_json(valor: Any) -> Any:
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, datetime):
        return (valor if valor.tzinfo else valor.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
    return valor


def _de_json(columna: Any, valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(columna.type, Uuid):
        return uuid.UUID(valor)
    if isinstance(columna.type, DateTime):
        return datetime.fromisoformat(valor)
    return valor


def a_datos(registro: Base, excluir: Iterable[str] = ()) -> dict[str, Any]:
    return {k: _a_json(getattr(registro, k)) for k, _ in _columnas(type(registro), excluir)}


def _llave(clase: type[Base], datos: dict[str, Any]) -> Any:
    mapeador = inspect(clase)
    partes = [_de_json(c, datos[str(c.key)]) for c in mapeador.primary_key]
    return partes[0] if len(partes) == 1 else tuple(partes)


def aplicar_registro(sesion: Session, clase: type[Base], datos: dict[str, Any], excluir: Iterable[str] = ()) -> bool:
    """Crea o actualiza el registro con esos datos. False si ya estaba idéntico (nada que escribir)."""
    registro = sesion.get(clase, _llave(clase, datos))
    if registro is not None and hash_de(a_datos(registro, excluir)) == hash_de(datos):
        return False
    if registro is None:
        registro = clase()
        sesion.add(registro)
    for k, columna in _columnas(clase, excluir):
        if k in datos:
            setattr(registro, k, _de_json(columna, datos[k]))
    sesion.flush()
    return True


def listar_proyectos(fabrica: Any) -> list[dict[str, str]]:
    with fabrica() as s:
        return [{"id": str(p.id), "nombre": p.nombre} for p in s.scalars(select(RegistroProyecto).order_by(RegistroProyecto.nombre))]


class ReplicaDeProyecto:
    """El proyecto mismo (tabla compartida `proyectos`): el primer sobre de toda réplica."""

    tipos = ("proyecto",)

    def __init__(self, fabrica: Any) -> None:
        self._fabrica = fabrica

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        with self._fabrica() as s:
            p = s.scalar(select(RegistroProyecto).where(RegistroProyecto.id == proyecto_id))
            if p is not None:
                yield Sobre("proyecto", str(p.id), str(p.id), a_datos(p))

    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        if sobre.eliminado:
            return False  # un proyecto no se borra por réplica
        assert sobre.datos is not None
        return aplicar_registro(sesion, RegistroProyecto, sobre.datos)

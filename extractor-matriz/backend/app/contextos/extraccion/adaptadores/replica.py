"""Réplica de Extracción (ADR 0009): solo las extracciones terminadas, con sus 25 columnas.

Las que siguen en curso no viajan: evita reenviar cada pocos segundos el progreso de una corrida activa.
La cola (`extraccion_cola`) tampoco se replica.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos, aplicar_registro
from app.compartido.sobre import Sobre
from app.contextos.extraccion.adaptadores.repositorio_sql import RegistroExtraccion
from app.contextos.extraccion.dominio.extraccion import EstadoExtraccion

TERMINADAS = (EstadoExtraccion.COMPLETADA.value, EstadoExtraccion.FALLIDA.value)


class ReplicaDeExtraccion:
    tipos = ("extraccion",)

    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        with self._fabrica() as s:
            q = select(RegistroExtraccion).where(RegistroExtraccion.proyecto_id == proyecto_id,
                                                 RegistroExtraccion.estado.in_(TERMINADAS))
            for e in s.scalars(q.order_by(RegistroExtraccion.iniciada_en)):
                yield Sobre("extraccion", str(e.id), str(proyecto_id), a_datos(e))

    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        if sobre.eliminado:
            r = sesion.get(RegistroExtraccion, uuid.UUID(sobre.id))
            if r is None:
                return False
            sesion.delete(r)
            sesion.flush()
            return True
        assert sobre.datos is not None
        return aplicar_registro(sesion, RegistroExtraccion, sobre.datos)

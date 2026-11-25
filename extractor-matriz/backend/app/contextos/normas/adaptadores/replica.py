"""Réplica de Normas (ADR 0009): todas las versiones del libro de códigos."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos, aplicar_registro
from app.compartido.sobre import Sobre
from app.contextos.normas.adaptadores.repositorio_sql import RegistroVersionDelLibro


class ReplicaDeNormas:
    tipos = ("libro",)

    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        with self._fabrica() as s:
            q = select(RegistroVersionDelLibro).where(RegistroVersionDelLibro.proyecto_id == proyecto_id)
            for v in s.scalars(q.order_by(RegistroVersionDelLibro.creado_en)):
                yield Sobre("libro", str(v.id), str(proyecto_id), a_datos(v))

    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        if sobre.eliminado:
            r = sesion.get(RegistroVersionDelLibro, uuid.UUID(sobre.id))
            if r is None:
                return False
            sesion.delete(r)
            sesion.flush()
            return True
        assert sobre.datos is not None
        if sobre.datos["activa"]:
            # Una sola versión activa por proyecto (índice único parcial): la anterior se apaga antes.
            sesion.execute(update(RegistroVersionDelLibro).where(
                RegistroVersionDelLibro.proyecto_id == uuid.UUID(sobre.proyecto_id),
                RegistroVersionDelLibro.id != uuid.UUID(sobre.id),
                RegistroVersionDelLibro.activa.is_(True)).values(activa=False))
        return aplicar_registro(sesion, RegistroVersionDelLibro, sobre.datos)

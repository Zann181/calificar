"""Réplica de Matriz (ADR 0009): cada fila viaja con sus celdas como un solo agregado, más el Excel base.

`matriz_secuencias` no se replica: es un contador del equipo local.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos, aplicar_registro
from app.compartido.sobre import Sobre, hash_de
from app.contextos.matriz.adaptadores.repositorio_sql import RegistroBase, RegistroCelda, RegistroFila


def _datos_de_fila(f: RegistroFila, celdas: list[RegistroCelda]) -> dict[str, Any]:
    datos = a_datos(f)
    datos["celdas"] = [a_datos(c) for c in sorted(celdas, key=lambda c: c.clave)]
    return datos


class ReplicaDeMatriz:
    tipos = ("fila", "base")

    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        with self._fabrica() as s:
            for f in s.scalars(select(RegistroFila).where(RegistroFila.proyecto_id == proyecto_id)
                               .order_by(RegistroFila.estudio)):
                celdas = list(s.scalars(select(RegistroCelda).where(RegistroCelda.fila_id == f.id)))
                yield Sobre("fila", str(f.id), str(proyecto_id), _datos_de_fila(f, celdas))
            b = s.get(RegistroBase, proyecto_id)
            if b is not None:
                yield Sobre("base", str(proyecto_id), str(proyecto_id), a_datos(b), archivos=(b.clave_almacen,))

    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        if sobre.tipo == "base":
            if sobre.eliminado:
                b = sesion.get(RegistroBase, uuid.UUID(sobre.id))
                if b is None:
                    return False
                sesion.delete(b)
                sesion.flush()
                return True
            assert sobre.datos is not None
            return aplicar_registro(sesion, RegistroBase, sobre.datos)
        return self._aplicar_fila(sesion, sobre)

    def _aplicar_fila(self, sesion: Session, sobre: Sobre) -> bool:
        fila_id = uuid.UUID(sobre.id)
        if sobre.eliminado:
            if sesion.get(RegistroFila, fila_id) is None:
                return False
            sesion.execute(delete(RegistroCelda).where(RegistroCelda.fila_id == fila_id))
            sesion.execute(delete(RegistroFila).where(RegistroFila.id == fila_id))
            sesion.flush()
            return True
        assert sobre.datos is not None
        datos = dict(sobre.datos)
        celdas: list[dict[str, Any]] = datos.pop("celdas")
        actual = sesion.get(RegistroFila, fila_id)
        if actual is not None:
            viejas = list(sesion.scalars(select(RegistroCelda).where(RegistroCelda.fila_id == fila_id)))
            if hash_de(_datos_de_fila(actual, viejas)) == sobre.hash:
                return False
        # Una fila reemplazada conserva el número de Estudio con otro id: la vieja sale antes (índice único).
        otras = list(sesion.scalars(select(RegistroFila.id).where(
            RegistroFila.proyecto_id == uuid.UUID(datos["proyecto_id"]), RegistroFila.estudio == datos["estudio"],
            RegistroFila.id != fila_id)))
        if otras:
            sesion.execute(delete(RegistroCelda).where(RegistroCelda.fila_id.in_(otras)))
            sesion.execute(delete(RegistroFila).where(RegistroFila.id.in_(otras)))
            sesion.flush()
        aplicar_registro(sesion, RegistroFila, datos)
        claves = {c["clave"] for c in celdas}
        for rc in sesion.scalars(select(RegistroCelda).where(RegistroCelda.fila_id == fila_id)):
            if rc.clave not in claves:
                sesion.delete(rc)
        sesion.flush()
        for c in celdas:
            aplicar_registro(sesion, RegistroCelda, c)
        return True

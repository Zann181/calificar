"""Réplica de Biblioteca (ADR 0009): artículos y documentos estructurados, más el listado de archivos de la nube."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos, aplicar_registro
from app.compartido.sobre import Sobre
from app.contextos.biblioteca.adaptadores.tablas import RegistroArchivo, RegistroArticulo, RegistroDocumento
from app.contextos.biblioteca.puertos import AlmacenDeArchivos

# `version` es el contador de bloqueo optimista de cada base: no se replica.
_EXCLUIR = ("version",)


class ReplicaDeBiblioteca:
    tipos = ("articulo", "documento")

    def __init__(self, fabrica: Callable[[], Session], almacen: AlmacenDeArchivos) -> None:
        self._fabrica, self._almacen = fabrica, almacen

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        with self._fabrica() as s:
            for a in s.scalars(select(RegistroArticulo).where(RegistroArticulo.proyecto_id == proyecto_id)
                               .order_by(RegistroArticulo.id)):
                archivos = [a.clave_almacen]
                crudo = f"crudo/{a.id}.zip"
                if self._almacen.existe(crudo):
                    archivos.append(crudo)
                yield Sobre("articulo", str(a.id), str(proyecto_id), a_datos(a, _EXCLUIR), archivos=tuple(archivos))
            for d in s.scalars(select(RegistroDocumento).where(RegistroDocumento.proyecto_id == proyecto_id)
                               .order_by(RegistroDocumento.id)):
                yield Sobre("documento", str(d.id), str(proyecto_id), a_datos(d))

    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        clase = RegistroArticulo if sobre.tipo == "articulo" else RegistroDocumento
        if sobre.eliminado:
            r = sesion.get(clase, uuid.UUID(sobre.id))
            if r is None:
                return False
            sesion.delete(r)
            sesion.flush()
            return True
        assert sobre.datos is not None
        return aplicar_registro(sesion, clase, sobre.datos, _EXCLUIR if sobre.tipo == "articulo" else ())

    def archivos_guardados(self) -> dict[str, str]:
        """Clave → SHA-256 de cada archivo que tiene la base (en la nube, para el manifiesto)."""
        with self._fabrica() as s:
            return {clave: sha for clave, sha in s.execute(select(RegistroArchivo.clave, RegistroArchivo.sha256))}

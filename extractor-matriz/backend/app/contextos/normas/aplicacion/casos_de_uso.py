"""Casos de uso de Normas: publicar una versión del libro y consultar el catálogo de columnas."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio
from app.contextos.normas.dominio.catalogo import derivar_protocolo
from app.contextos.normas.dominio.modelos import VersionDelLibro
from app.contextos.normas.puertos import UnidadDeTrabajoNormas

FabricaUdT = Callable[[], UnidadDeTrabajoNormas]


class SinLibroActivo(ErrorDeDominio):
    pass


class PublicarLibro:
    """Publica una versión nueva y desactiva la anterior. Publicar el mismo contenido no duplica."""

    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, contenido: dict[str, Any]) -> VersionDelLibro:
        with self._udt() as u:
            nuevo = VersionDelLibro.publicar(proyecto_id=proyecto_id, contenido=contenido)
            actual = u.libros.activa(proyecto_id)
            if actual is not None and actual.hash == nuevo.hash:
                return actual
            if actual is not None:
                actual.desactivar()
            u.libros.agregar(nuevo)
            u.confirmar()
            return nuevo


class ConsultasDeNormas:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def libro_activo(self, proyecto_id: uuid.UUID) -> VersionDelLibro:
        with self._udt() as u:
            libro = u.libros.activa(proyecto_id)
        if libro is None:
            raise SinLibroActivo("El proyecto no tiene libro de códigos publicado")
        return libro

    def columnas(self, proyecto_id: uuid.UUID) -> list[DefinicionDeColumna]:
        return self.libro_activo(proyecto_id).catalogo().columnas

    def protocolo(self, proyecto_id: uuid.UUID) -> dict[str, Any]:
        return derivar_protocolo(self.libro_activo(proyecto_id).contenido)

    def versiones(self, proyecto_id: uuid.UUID) -> list[VersionDelLibro]:
        with self._udt() as u:
            return u.libros.listar(proyecto_id)


@dataclass
class CasosDeNormas:
    publicar: PublicarLibro
    consultas: ConsultasDeNormas

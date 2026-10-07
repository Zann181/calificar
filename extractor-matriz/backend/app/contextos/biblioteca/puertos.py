"""Puertos del contexto Biblioteca."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.compartido.unidad_de_trabajo import UnidadDeTrabajo
from app.contextos.biblioteca.dominio.articulo import Articulo, EstadoArticulo
from app.contextos.biblioteca.dominio.documento import DocumentoEstructurado


@dataclass(frozen=True)
class Conversion:
    """Resultado de convertir un PDF: el documento normalizado y la salida cruda (zip) para archivarla."""

    documento: DocumentoEstructurado
    crudo: bytes


class ConversorPDF(Protocol):
    def convertir(self, pdf: bytes, nombre: str) -> Conversion: ...


class AlmacenDeArchivos(Protocol):
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...
    def leer(self, clave: str) -> bytes: ...
    def url_temporal(self, clave: str, segundos: int = 900) -> str: ...


class HuellaDuplicada(Exception):
    """La base de datos rechazó un artículo con la misma huella (carrera entre dos cargas)."""


class RepositorioDeArticulos(Protocol):
    def agregar(self, articulo: Articulo) -> None: ...
    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo: ...
    def por_huella(self, proyecto_id: uuid.UUID, huella: str) -> Articulo | None: ...
    def listar(self, proyecto_id: uuid.UUID, estado: EstadoArticulo | None = None) -> list[Articulo]: ...
    def contar_por_estado(self, proyecto_id: uuid.UUID) -> dict[str, int]: ...


class RepositorioDeDocumentos(Protocol):
    def guardar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, documento: DocumentoEstructurado) -> uuid.UUID: ...
    def obtener(self, proyecto_id: uuid.UUID, documento_id: uuid.UUID) -> DocumentoEstructurado: ...


class UnidadDeTrabajoBiblioteca(UnidadDeTrabajo, Protocol):
    # Propiedades de solo lectura: el adaptador puede exponer un subtipo del repositorio.
    @property
    def articulos(self) -> RepositorioDeArticulos: ...
    @property
    def documentos(self) -> RepositorioDeDocumentos: ...

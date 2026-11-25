"""Puertos de Descubrimiento. Las fuentes, el almacenamiento y los datos de otros contextos entran por aquí."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.contextos.descubrimiento.dominio.busqueda import Busqueda, ConsultaDeBusqueda
from app.contextos.descubrimiento.dominio.candidato import Candidato, EstadoCandidato, RegistroBibliografico
from app.contextos.descubrimiento.dominio.completitud import (
    AnalisisDeTexto,
    ColumnaDelLibro,
    PerfilDeColumnas,
)
from app.contextos.descubrimiento.dominio.sitios import EstadoDeSesion, SitioConCredenciales


class FuenteDeLiteratura(Protocol):
    """Un lugar donde buscar. Añadir una fuente es escribir un adaptador que cumpla esto.

    `buscar` devuelve registros de uno en uno (paginando por dentro) y lanza `ErrorDeFuente` si no puede seguir.
    Nunca llama a un modelo de lenguaje (ADR 0011).
    """

    @property
    def nombre(self) -> str: ...

    @property
    def etiqueta(self) -> str: ...

    @property
    def sitio_id(self) -> str | None:
        """Id del `SitioConCredenciales` si la fuente exige sesión de la persona; None si es abierta."""

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]: ...


class RepositorioDeBusquedas(Protocol):
    def guardar(self, b: Busqueda) -> None: ...
    def obtener(self, proyecto_id: uuid.UUID, busqueda_id: uuid.UUID) -> Busqueda: ...
    def listar(self, proyecto_id: uuid.UUID, cuantas: int = 50) -> list[Busqueda]: ...
    def registrar_hallazgo(self, busqueda_id: uuid.UUID, candidato_id: uuid.UUID, fuente: str, posicion: int) -> None: ...
    def candidatos_de(self, busqueda_id: uuid.UUID) -> set[uuid.UUID]: ...


class RepositorioDeCandidatos(Protocol):
    def guardar(self, c: Candidato) -> None: ...
    def obtener(self, proyecto_id: uuid.UUID, candidato_id: uuid.UUID) -> Candidato: ...
    def por_clave(self, proyecto_id: uuid.UUID, clave: str) -> Candidato | None: ...
    def por_ids(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Candidato]: ...
    def indice(self, proyecto_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str, int | None]]:
        """(id, clave, título, año) de todos los candidatos del proyecto, para reconocer repetidos sin cargarlos."""

    def listar(self, proyecto_id: uuid.UUID, *, estado: EstadoCandidato | None = None,
               busqueda_id: uuid.UUID | None = None, texto: str | None = None, en_matriz: bool | None = None,
               desde: int = 0, cuantos: int = 100) -> tuple[list[Candidato], int]: ...

    def contadores(self, proyecto_id: uuid.UUID) -> dict[str, int]: ...


class TitulosEnMatriz(Protocol):
    """Los títulos que ya están en la matriz. Lo implementa `app/composicion.py` con el contexto Matriz."""

    def titulos(self, proyecto_id: uuid.UUID) -> list[str]: ...


class CatalogoDeSitios(Protocol):
    def todos(self) -> list[SitioConCredenciales]: ...


class EstadoDeSesiones(Protocol):
    """Si la persona ya inició sesión en cada sitio. Nunca expone cookies ni contraseñas."""

    def estado(self, sitio_id: str) -> EstadoDeSesion: ...


class RepositorioDePerfiles(Protocol):
    def guardar(self, p: PerfilDeColumnas) -> PerfilDeColumnas: ...
    def obtener(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> PerfilDeColumnas: ...
    def listar(self, proyecto_id: uuid.UUID) -> list[PerfilDeColumnas]: ...
    def predeterminado(self, proyecto_id: uuid.UUID) -> PerfilDeColumnas | None: ...
    def borrar(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> None: ...


class CatalogoDeColumnas(Protocol):
    """Las columnas del libro de códigos vigente. Lo implementa `app/composicion.py` con el contexto Normas."""

    def columnas(self, proyecto_id: uuid.UUID) -> list[ColumnaDelLibro]: ...


@dataclass(frozen=True)
class ResultadoDeCarga:
    articulo_id: uuid.UUID | None
    duplicado: bool = False
    duplicado_de: str | None = None
    error: str | None = None


class ObtenerPdf(Protocol):
    """Consigue el PDF abierto de un candidato. Solo copias abiertas y legales."""

    def urls(self, doi: str | None, url_oa: str | None) -> list[str]: ...

    def descargar(self, url: str) -> bytes:
        """Bytes de un PDF verificado, o `ErrorDeFuente`."""


class CargadorDeArticulos(Protocol):
    """Entrega un PDF a Biblioteca. Lo implementa `app/composicion.py` con el caso de uso CargarPDF."""

    def cargar(self, proyecto_id: uuid.UUID, nombre_archivo: str, datos: bytes) -> ResultadoDeCarga: ...


class ExtraerTexto(Protocol):
    """Texto de un PDF, página por página."""

    def paginas(self, datos: bytes) -> list[str]: ...


class PdfsDeBiblioteca(Protocol):
    """El PDF de un artículo ya importado, para no bajarlo otra vez. Lo implementa `app/composicion.py`."""

    def leer(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> bytes | None: ...


class RepositorioDeAnalisis(Protocol):
    def guardar(self, a: AnalisisDeTexto) -> None: ...
    def por_candidatos(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, AnalisisDeTexto]: ...


class SaludDeFuentes(Protocol):
    """Qué fuentes de lectura frágil están desactivadas (tras fallos de estructura seguidos) y por qué."""

    def desactivada(self, fuente: str) -> str | None: ...
    def exito(self, fuente: str) -> None: ...
    def fallo_de_estructura(self, fuente: str, motivo: str) -> bool: ...
    def reactivar(self, fuente: str) -> None: ...

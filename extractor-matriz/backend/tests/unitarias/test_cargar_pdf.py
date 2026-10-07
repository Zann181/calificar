"""Caso de uso CargarPDF con repositorios en memoria: un PDF repetido se rechaza (aceptación de F1)."""

from __future__ import annotations

import uuid

from app.compartido.dominio import NoEncontrado
from app.compartido.unidad_de_trabajo import UnidadDeTrabajoEnMemoria
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.aplicacion.casos_de_uso import CargarPDF, huella
from app.contextos.biblioteca.dominio.articulo import Articulo, EstadoArticulo
from app.contextos.biblioteca.dominio.documento import DocumentoEstructurado
from app.contextos.biblioteca.eventos import ArticuloCargado

PDF = b"%PDF-1.7\n" + b"contenido de prueba" * 10


class ArticulosEnMemoria:
    """Como el repositorio SQL: agregar() deja el agregado seguido por la unidad de trabajo."""

    def __init__(self, udt: UnidadDeTrabajoEnMemoria) -> None:
        self._udt = udt
        self.datos: dict[uuid.UUID, Articulo] = {}

    def agregar(self, articulo: Articulo) -> None:
        self.datos[articulo.id] = articulo
        self._udt.seguir(articulo)

    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        a = self.datos.get(articulo_id)
        if a is None or a.proyecto_id != proyecto_id:
            raise NoEncontrado(str(articulo_id))
        return a

    def por_huella(self, proyecto_id: uuid.UUID, h: str) -> Articulo | None:
        return next((a for a in self.datos.values() if a.proyecto_id == proyecto_id and a.huella_sha256 == h), None)

    def listar(self, proyecto_id: uuid.UUID, estado: EstadoArticulo | None = None) -> list[Articulo]:
        return [a for a in self.datos.values() if a.proyecto_id == proyecto_id and estado in (None, a.estado)]

    def contar_por_estado(self, proyecto_id: uuid.UUID) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.listar(proyecto_id):
            conteo[a.estado.value] = conteo.get(a.estado.value, 0) + 1
        return conteo


class DocumentosEnMemoria:
    def guardar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, documento: DocumentoEstructurado) -> uuid.UUID:
        return uuid.uuid4()

    def obtener(self, proyecto_id: uuid.UUID, documento_id: uuid.UUID) -> DocumentoEstructurado:
        raise NoEncontrado(str(documento_id))


class UdTBiblioteca(UnidadDeTrabajoEnMemoria):
    def __init__(self) -> None:
        super().__init__()
        self.articulos = ArticulosEnMemoria(self)
        self.documentos = DocumentosEnMemoria()


def armar() -> tuple[CargarPDF, UdTBiblioteca, AlmacenEnMemoria]:
    udt, almacen = UdTBiblioteca(), AlmacenEnMemoria()
    return CargarPDF(lambda: udt, almacen), udt, almacen


def test_carga_nueva_guarda_pdf_y_publica_evento() -> None:
    caso, udt, almacen = armar()
    pid = uuid.uuid4()
    r = caso.ejecutar(pid, "Kumar.pdf", PDF)
    assert not r.duplicado and r.error is None and r.articulo_id is not None
    assert almacen.existe(f"pdf/{pid}/{huella(PDF)}.pdf")
    assert [type(e) for e in udt.publicados] == [ArticuloCargado]


def test_pdf_repetido_se_rechaza() -> None:
    caso, udt, _ = armar()
    pid = uuid.uuid4()
    primero = caso.ejecutar(pid, "Chunyan Li.pdf", PDF)
    segundo = caso.ejecutar(pid, "Chunyan.pdf", PDF)
    assert segundo.duplicado
    assert segundo.duplicado_de == "Chunyan Li.pdf"
    assert segundo.articulo_id == primero.articulo_id
    assert len(udt.articulos.datos) == 1
    assert len(udt.publicados) == 1


def test_mismo_pdf_en_otro_proyecto_no_es_duplicado() -> None:
    caso, udt, _ = armar()
    caso.ejecutar(uuid.uuid4(), "a.pdf", PDF)
    r = caso.ejecutar(uuid.uuid4(), "a.pdf", PDF)
    assert not r.duplicado
    assert len(udt.articulos.datos) == 2


def test_archivo_que_no_es_pdf() -> None:
    caso, udt, _ = armar()
    r = caso.ejecutar(uuid.uuid4(), "notas.docx", b"PK\x03\x04")
    assert r.error == "El archivo no es un PDF"
    assert not udt.articulos.datos

"""Biblioteca con adaptadores SQL: carga con deduplicación, conversión, outbox y aislamiento por proyecto."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.compartido.db import RegistroOutbox
from app.composicion import Contenedor
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto

KUMAR = (FIXTURES / "kumar_2022.pdf").read_bytes()


def eventos(c: Contenedor) -> list[str]:
    with c.fabrica() as s:
        return [r.nombre for r in s.scalars(select(RegistroOutbox).order_by(RegistroOutbox.id))]


def test_pdf_repetido_se_rechaza(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    primero = contenedor.biblioteca.cargar.ejecutar(proyecto, "1. Kumar 2022.pdf", KUMAR)
    segundo = contenedor.biblioteca.cargar.ejecutar(proyecto, "Kumar copia.pdf", KUMAR)
    assert not primero.duplicado
    assert segundo.duplicado and segundo.duplicado_de == "1. Kumar 2022.pdf"
    assert len(contenedor.biblioteca.consultas.listar(proyecto).articulos) == 1
    assert eventos(contenedor).count("ArticuloCargado") == 1


def test_convertir_con_salida_guardada(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    r = contenedor.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", KUMAR)
    assert r.articulo_id is not None
    estado = contenedor.biblioteca.convertir.ejecutar(proyecto, r.articulo_id)
    assert estado == EstadoArticulo.LISTO
    articulo = contenedor.biblioteca.consultas.articulo(proyecto, r.articulo_id)
    assert articulo.paginas == 8 and articulo.documento_estructurado_id is not None
    assert "ArticuloConvertido" in eventos(contenedor)


def test_conversion_fallida_queda_en_error(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    r = contenedor.biblioteca.cargar.ejecutar(proyecto, "sin_salida_guardada.pdf", b"%PDF-1.4 otro")
    assert r.articulo_id is not None
    assert contenedor.biblioteca.convertir.ejecutar(proyecto, r.articulo_id) == EstadoArticulo.ERROR
    articulo = contenedor.biblioteca.consultas.articulo(proyecto, r.articulo_id)
    assert articulo.error is not None and articulo.error.paso == EstadoArticulo.CONVIRTIENDO


def test_despachador_convierte_al_cargar(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    r = contenedor.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", KUMAR)
    assert r.articulo_id is not None
    while contenedor.despachador.despachar_pendientes():
        pass
    assert contenedor.biblioteca.consultas.articulo(proyecto, r.articulo_id).estado == EstadoArticulo.LISTO
    with contenedor.fabrica() as s:
        pendientes = s.scalars(select(RegistroOutbox).where(RegistroOutbox.despachado_en.is_(None))).all()
    assert pendientes == []


def test_aislamiento_por_proyecto(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    otro = nuevo_proyecto(contenedor, "Otra revisión")
    contenedor.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", KUMAR)
    assert contenedor.biblioteca.consultas.listar(otro).articulos == []
    # El mismo PDF en otro proyecto no es duplicado.
    assert not contenedor.biblioteca.cargar.ejecutar(otro, "kumar_2022.pdf", KUMAR).duplicado

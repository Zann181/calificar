"""Agregado Articulo: máquina de estados y eventos (sección 5.1)."""

from __future__ import annotations

import uuid

import pytest

from app.compartido.dominio import ErrorDeDominio
from app.contextos.biblioteca.dominio.articulo import Articulo, EstadoArticulo, TransicionInvalida
from app.contextos.biblioteca.eventos import (
    ArticuloCargado,
    ArticuloConvertido,
    ArticuloExcluido,
    ConversionFallida,
    EstadoDeArticuloCambiado,
)

E = EstadoArticulo


def nuevo() -> Articulo:
    return Articulo.cargar(proyecto_id=uuid.uuid4(), nombre_archivo="a.pdf", huella_sha256="a" * 64,
                           clave_almacen="pdf/a.pdf")


def listo() -> Articulo:
    a = nuevo()
    a.iniciar_conversion()
    a.completar_conversion(documento_estructurado_id=uuid.uuid4(), paginas=8)
    a.extraer_eventos()
    return a


def test_cargar_emite_evento_y_queda_nuevo() -> None:
    a = nuevo()
    assert a.estado == E.NUEVO
    assert [type(e) for e in a.extraer_eventos()] == [ArticuloCargado]


def test_huella_invalida() -> None:
    with pytest.raises(ErrorDeDominio, match="SHA-256"):
        Articulo.cargar(proyecto_id=uuid.uuid4(), nombre_archivo="a.pdf", huella_sha256="abc", clave_almacen="x")


def test_conversion_exitosa() -> None:
    a = nuevo()
    a.extraer_eventos()
    a.iniciar_conversion()
    a.completar_conversion(documento_estructurado_id=uuid.uuid4(), paginas=8)
    assert (a.estado, a.paginas) == (E.LISTO, 8)
    tipos = [type(e) for e in a.extraer_eventos()]
    assert tipos == [EstadoDeArticuloCambiado, EstadoDeArticuloCambiado, ArticuloConvertido]


def test_conversion_sin_paginas() -> None:
    a = nuevo()
    a.iniciar_conversion()
    with pytest.raises(ErrorDeDominio):
        a.completar_conversion(documento_estructurado_id=uuid.uuid4(), paginas=0)


@pytest.mark.parametrize("hacia", [E.LISTO, E.EN_COLA, E.APROBADO, E.POR_REVISAR])
def test_transiciones_invalidas_desde_nuevo(hacia: EstadoArticulo) -> None:
    with pytest.raises(TransicionInvalida):
        nuevo().transicionar(hacia)


def test_error_y_reintento_vuelven_al_paso_que_fallo() -> None:
    a = nuevo()
    a.iniciar_conversion()
    a.extraer_eventos()
    a.fallar(E.CONVIRTIENDO, "MinerU no respondió")
    assert a.estado == E.ERROR
    assert a.error is not None and a.error.paso == E.CONVIRTIENDO
    assert ConversionFallida in [type(e) for e in a.extraer_eventos()]
    a.reintentar()
    assert a.estado == E.CONVIRTIENDO


def test_reintentar_sin_error() -> None:
    with pytest.raises(TransicionInvalida):
        nuevo().reintentar()


def test_encolar_exige_documento_y_cancelar_vuelve_a_listo() -> None:
    a = listo()
    a.encolar()
    assert a.estado == E.EN_COLA
    a.cancelar()
    assert a.estado == E.LISTO


def test_reextraer_exige_confirmacion_y_motivo() -> None:
    a = listo()
    a.encolar()
    a.transicionar(E.EXTRAYENDO)
    a.transicionar(E.AUDITANDO)
    a.transicionar(E.POR_REVISAR)
    with pytest.raises(ErrorDeDominio, match="confirmación"):
        a.encolar()
    a.transicionar(E.APROBADO)
    with pytest.raises(ErrorDeDominio, match="motivo"):
        a.encolar(confirmar_reextraccion=True)
    a.encolar(confirmar_reextraccion=True, motivo="Libro v2.2")
    assert a.estado == E.EN_COLA


def test_excluir_exige_motivo_y_reactivar() -> None:
    a = nuevo()
    a.extraer_eventos()
    with pytest.raises(ErrorDeDominio, match="motivo"):
        a.excluir("  ")
    a.excluir("Duplicado de Chunyan Li")
    assert a.estado == E.EXCLUIDO
    assert ArticuloExcluido in [type(e) for e in a.extraer_eventos()]
    a.reactivar()
    assert a.estado == E.NUEVO and a.excluido_motivo is None


def test_no_se_excluye_durante_la_conversion() -> None:
    a = nuevo()
    a.iniciar_conversion()
    with pytest.raises(TransicionInvalida):
        a.excluir("no")

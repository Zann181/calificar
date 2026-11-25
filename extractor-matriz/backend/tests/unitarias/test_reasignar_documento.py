"""ReasignarDocumento: dos artículos con el mismo Documento comparten ID muestra; el caso de uso lo corrige."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.compartido.dominio import ErrorDeDominio
from app.contextos.matriz.aplicacion.casos_de_uso import ReasignarDocumento
from app.contextos.matriz.dominio.fila import Celda, FilaDeEfecto, TipoValor

PID = uuid.uuid4()


def fila(estudio: int, documento: int, articulo: uuid.UUID, id_muestra: str) -> FilaDeEfecto:
    celdas = {k: Celda(clave=k, valor=v, tipo_valor=TipoValor.CODIFICADO)
              for k, v in {"Documento": documento, "ID muestra": id_muestra}.items()}
    salida = {"fila": {"Documento": documento}, "trazabilidad": {"id_muestra": id_muestra}}
    return FilaDeEfecto.extraida(proyecto_id=PID, estudio=estudio, documento=documento, articulo_id=articulo,
                                 version_libro_id=uuid.uuid4(), celdas=celdas, trazabilidad={"salida": salida})


class _Filas:
    def __init__(self, filas: list[FilaDeEfecto]) -> None:
        self.guardadas = filas

    def todas(self, _: uuid.UUID) -> list[FilaDeEfecto]:
        return self.guardadas

    def agregar(self, f: FilaDeEfecto) -> None:
        pass


class _Udt:
    def __init__(self, filas: list[FilaDeEfecto]) -> None:
        self.filas = _Filas(filas)

    def __enter__(self) -> _Udt:
        return self

    def __exit__(self, *_: Any) -> None:
        pass

    def confirmar(self) -> None:
        pass


def caso(filas: list[FilaDeEfecto]) -> ReasignarDocumento:
    return ReasignarDocumento(lambda: _Udt(filas))  # type: ignore[arg-type,return-value]


def test_reasigna_documento_e_id_muestra_en_celdas_y_salida() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    kumar, otra1, otra2 = fila(1, 1, a, "D1-M1"), fila(139, 1, b, "D1-M1"), fila(140, 1, b, "D1-M2")
    n = caso([kumar, otra1, otra2]).ejecutar(PID, b, 48, autor="yo@x", motivo="Documento repetido")
    assert n == 2
    assert (otra1.documento, otra2.documento) == (48, 48)
    assert otra1.celdas["ID muestra"].valor == "D48-M1" and otra2.celdas["ID muestra"].valor == "D48-M2"
    assert otra1.celdas["Documento"].valor == 48
    assert otra1.trazabilidad["salida"]["fila"]["Documento"] == 48
    assert otra1.trazabilidad["salida"]["trazabilidad"]["id_muestra"] == "D48-M1"
    assert otra1.celdas["ID muestra"].historial[-1].autor == "yo@x"
    assert kumar.documento == 1 and kumar.celdas["ID muestra"].valor == "D1-M1"  # el otro artículo no se toca


def test_rechaza_un_documento_que_usa_otro_articulo() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ErrorDeDominio, match="ya lo usa"):
        caso([fila(1, 1, a, "D1-M1"), fila(139, 2, b, "D2-M1")]).ejecutar(PID, b, 1, autor="x", motivo="m")


def test_rechaza_articulo_sin_filas_y_documento_invalido() -> None:
    with pytest.raises(ErrorDeDominio, match="no tiene filas"):
        caso([]).ejecutar(PID, uuid.uuid4(), 5, autor="x", motivo="m")
    with pytest.raises(ErrorDeDominio, match="positivo"):
        caso([]).ejecutar(PID, uuid.uuid4(), 0, autor="x", motivo="m")

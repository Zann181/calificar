"""Invariantes del agregado FilaDeEfecto (sección 5.4)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio
from app.contextos.matriz.dominio.fila import (
    EstadoRevision,
    FilaDeEfecto,
    Origen,
    TipoValor,
    valor_permitido,
)
from app.contextos.matriz.eventos import CeldaAprobada, CeldaCorregida, FilaAprobada, FilaEscrita

PID = uuid.uuid4()


def fila(valores: dict[str, Any] | None = None, **kw: Any) -> FilaDeEfecto:
    base = {"Correlación Feli 1 - JP": 0.73, "Beta Fel 1- JP": 0.287, "Muestra": 395, "Pais": "India",
            "Incluir en meta análisi": "PLS"}
    return FilaDeEfecto.importar_heredada(proyecto_id=PID, estudio=kw.get("estudio", 1), documento=1,
                                          valores=valores or base, version_libro_id=None)


def test_importar_heredada_conserva_valores_y_registra_evento() -> None:
    f = fila()
    assert f.origen == Origen.HEREDADA
    assert f.valores()["Correlación Feli 1 - JP"] == 0.73
    assert all(c.estado_revision == EstadoRevision.SIN_EVIDENCIA for c in f.celdas.values())
    eventos = f.extraer_eventos()
    assert [type(e) for e in eventos] == [FilaEscrita]


def test_celda_vacia_heredada_es_faltante() -> None:
    f = fila({"Muestra": None, "Pais": "India"})
    assert f.celda("Muestra").tipo_valor == TipoValor.FALTANTE
    assert f.celda("Pais").tipo_valor is None


@pytest.mark.parametrize("estudio,documento", [(0, 1), (1, 0), (-3, 2)])
def test_estudio_y_documento_positivos(estudio: int, documento: int) -> None:
    with pytest.raises(ErrorDeDominio):
        FilaDeEfecto.importar_heredada(proyecto_id=PID, estudio=estudio, documento=documento, valores={},
                                       version_libro_id=None)


@pytest.mark.parametrize("estado", [EstadoRevision.SIN_EVIDENCIA, EstadoRevision.POR_CONFIRMAR,
                                    EstadoRevision.NO_VERIFICABLE])
def test_invariante_1_aprobar_sin_ubicacion_exige_motivo(estado: EstadoRevision) -> None:
    f = fila()
    f.celda("Pais").estado_revision = estado
    with pytest.raises(ErrorDeDominio, match="exige motivo"):
        f.aprobar_celda("Pais", autor="revisor@x", motivo="  ")
    f.aprobar_celda("Pais", autor="revisor@x", motivo="Verificado en la p. 3")
    assert f.celda("Pais").estado_revision == EstadoRevision.APROBADA


def test_aprobar_celda_pendiente_sin_motivo_y_evento() -> None:
    f = fila()
    f.extraer_eventos()
    f.celda("Pais").estado_revision = EstadoRevision.PENDIENTE
    f.aprobar_celda("Pais", autor="revisor@x")
    assert f.celda("Pais").historial[-1].accion == "APROBAR"
    assert [type(e) for e in f.extraer_eventos()] == [CeldaAprobada]


def test_toda_accion_exige_autor() -> None:
    f = fila()
    with pytest.raises(ErrorDeDominio, match="autor"):
        f.rechazar_celda("Pais", autor="", motivo="no está en el artículo")


def test_invariante_2_corregir_exige_motivo_y_guarda_valor_anterior(por_clave: dict[str, DefinicionDeColumna]) -> None:
    f = fila()
    f.extraer_eventos()
    definicion = por_clave["Muestra"]
    with pytest.raises(ErrorDeDominio, match="motivo"):
        f.corregir_celda("Muestra", autor="r", valor=390, motivo="", definicion=definicion)
    f.corregir_celda("Muestra", autor="r", valor=390, motivo="La Tabla 1 dice N = 390", definicion=definicion)
    celda = f.celda("Muestra")
    assert celda.valor == 390
    assert celda.estado_revision == EstadoRevision.CORREGIDA
    cambio = celda.historial[-1]
    assert (cambio.valor_anterior, cambio.valor_nuevo, cambio.motivo) == (395, 390, "La Tabla 1 dice N = 390")
    assert [type(e) for e in f.extraer_eventos()] == [CeldaCorregida]


def test_corregir_con_definicion_de_otra_columna_falla(por_clave: dict[str, DefinicionDeColumna]) -> None:
    with pytest.raises(ErrorDeDominio, match="no corresponde"):
        fila().corregir_celda("Muestra", autor="r", valor=1, motivo="x", definicion=por_clave["Pais"])


def test_invariante_3_fila_aprobada_solo_con_numericas_revisadas(columnas: list[DefinicionDeColumna]) -> None:
    numericas = [c for c in columnas if c.es_numerica]
    f = FilaDeEfecto.importar_heredada(proyecto_id=PID, estudio=5, documento=2,
                                       valores={c.clave: None for c in columnas}, version_libro_id=None)
    with pytest.raises(ErrorDeDominio, match="sin revisar"):
        f.aprobar(autor="r", columnas=columnas)
    for c in numericas:
        f.aprobar_celda(c.clave, autor="r", motivo="faltante confirmado en el artículo")
    f.extraer_eventos()
    f.aprobar(autor="r", columnas=columnas)
    assert f.aprobada
    assert [type(e) for e in f.extraer_eventos()] == [FilaAprobada]


def test_rechazar_o_corregir_quita_la_aprobacion_de_la_fila(columnas: list[DefinicionDeColumna],
                                                           por_clave: dict[str, DefinicionDeColumna]) -> None:
    f = FilaDeEfecto.importar_heredada(proyecto_id=PID, estudio=5, documento=2,
                                       valores={c.clave: None for c in columnas}, version_libro_id=None)
    for c in columnas:
        if c.es_numerica:
            f.aprobar_celda(c.clave, autor="r", motivo="ok")
    f.aprobar(autor="r", columnas=columnas)
    f.rechazar_celda("Pais", autor="r", motivo="el país no aparece")
    assert not f.aprobada


def test_invariante_5_valores_permitidos(por_clave: dict[str, DefinicionDeColumna]) -> None:
    incluir = por_clave["Incluir en meta análisi"]
    assert valor_permitido(incluir, "PLS")
    assert valor_permitido(incluir, None)
    assert not valor_permitido(incluir, "Tal vez")
    assert not valor_permitido(incluir, 3)


def test_invariante_5_categoria_multiple_y_otro(por_clave: dict[str, DefinicionDeColumna]) -> None:
    direccion = por_clave["Direccionalidad de la relación"]
    permitidos = list(direccion.valores_permitidos or ())
    assert valor_permitido(direccion, "; ".join(permitidos[:2]))
    tipo = por_clave["Tipo de felicidad real"]
    assert valor_permitido(tipo, "Otro: bienestar espiritual")
    assert not valor_permitido(tipo, "Otro: ")


def test_corregir_rechaza_valor_fuera_de_vocabulario(por_clave: dict[str, DefinicionDeColumna]) -> None:
    f = fila()
    with pytest.raises(ErrorDeDominio, match="valores permitidos"):
        f.corregir_celda("Incluir en meta análisi", autor="r", valor="Quizás", motivo="x",
                         definicion=por_clave["Incluir en meta análisi"])


def test_estado_dato_invalido() -> None:
    from app.contextos.matriz.dominio.fila import Celda

    with pytest.raises(ErrorDeDominio):
        Celda(clave="Muestra", estado_dato="No sé")


def test_marcar_version_solo_afecta_extraidas() -> None:
    heredada = fila()
    heredada.marcar_version(uuid.uuid4())
    assert not heredada.version_desactualizada
    extraida = FilaDeEfecto(proyecto_id=PID, estudio=9, documento=3, origen=Origen.EXTRAIDA,
                            version_libro_id=uuid.uuid4())
    extraida.marcar_version(uuid.uuid4())
    assert extraida.version_desactualizada

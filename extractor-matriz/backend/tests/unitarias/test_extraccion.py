"""Agregado Extraccion, comparación de campos críticos y lectura del validador."""

from __future__ import annotations

import uuid

import pytest

from app.compartido.dominio import ErrorDeDominio
from app.contextos.extraccion.adaptadores.validador import admite_bloque_id, clasificar, sin_bloque_id
from app.contextos.extraccion.aplicacion.roles import RespuestaInvalida, json_de
from app.contextos.extraccion.dominio.anclaje import Ancla, NivelAncla
from app.contextos.extraccion.dominio.comparacion import comparar, iguales
from app.contextos.extraccion.dominio.extraccion import (
    EstadoExtraccion,
    Extraccion,
    Veredicto,
    veredicto_de,
)
from app.contextos.extraccion.dominio.libro import regla_para_campo
from app.contextos.extraccion.eventos import CitaNoVerificable, ExtraccionCompletada, ExtraccionFallida

X = EstadoExtraccion


def _extraccion() -> Extraccion:
    return Extraccion.iniciar(proyecto_id=uuid.uuid4(), articulo_id=uuid.uuid4(), version_libro_id=uuid.uuid4(),
                              estudios_reservados=[72])


def _hasta_conciliar(e: Extraccion) -> None:
    e.registrar_salida([{"fila": {"Estudio": 72}, "trazabilidad": {}}])
    e.registrar_validacion([], [])
    e.pasar(X.ANCLANDO)
    e.registrar_anclas([Ancla(estudio=72, columna="Muestra", indice_evidencia=0, nivel=NivelAncla.NO_VERIFICABLE,
                              similitud=40)])
    e.pasar(X.AUDITANDO)
    e.registrar_hallazgos([], [])
    e.pasar(X.CONCILIANDO)


def test_flujo_completo_emite_eventos() -> None:
    e = _extraccion()
    _hasta_conciliar(e)
    e.completar(acuerdo=0.95)
    eventos = e.extraer_eventos()
    assert e.estado == X.COMPLETADA and e.terminada_en is not None
    assert [type(x) for x in eventos] == [CitaNoVerificable, ExtraccionCompletada]
    assert eventos[1].estudios == [72]  # type: ignore[attr-defined]


def test_no_se_ancla_ni_completa_con_errores_del_validador() -> None:
    e = _extraccion()
    e.registrar_salida([{"fila": {"Estudio": 72}}])
    e.registrar_validacion(["V3: falta Muestra"], [])
    with pytest.raises(ErrorDeDominio):
        e.pasar(X.AUDITANDO)  # no se saltan pasos
    e.pasar(X.ANCLANDO)
    with pytest.raises(ErrorDeDominio):
        e.registrar_anclas([])


def test_otra_iteracion_vuelve_a_extrayendo() -> None:
    e = _extraccion()
    e.registrar_salida([])
    e.registrar_validacion(["error"], [])
    e.pasar(X.EXTRAYENDO)
    e.registrar_salida([{"fila": {"Estudio": 72}}])
    e.registrar_validacion([], ["aviso"])
    assert e.iteraciones_validador == 2 and e.avisos_validador == ["aviso"]


def test_fallar_registra_el_paso_y_no_se_puede_completar_despues() -> None:
    e = _extraccion()
    e.registrar_salida([])
    e.fallar("El validador mantiene 2 errores")
    assert (e.estado, e.paso_fallido) == (X.FALLIDA, "VALIDANDO")
    assert isinstance(e.extraer_eventos()[0], ExtraccionFallida)
    with pytest.raises(ErrorDeDominio):
        e.fallar("otra vez")


def test_conciliacion_con_errores_no_se_aplica() -> None:
    e = _extraccion()
    _hasta_conciliar(e)
    antes = e.salida
    assert not e.aplicar_conciliacion(salida=[{"fila": {"Estudio": 72, "Muestra": 1}}], anclas=[], hallazgos=[],
                                      errores=["V9"], avisos=[])
    assert e.salida == antes
    assert e.aplicar_conciliacion(salida=[{"fila": {"Estudio": 72, "Muestra": 2}}], anclas=[], hallazgos=[],
                                  errores=[], avisos=[])
    assert e.salida[0]["fila"]["Muestra"] == 2


def test_iniciar_exige_estudio() -> None:
    with pytest.raises(ErrorDeDominio):
        Extraccion.iniciar(proyecto_id=uuid.uuid4(), articulo_id=uuid.uuid4(), version_libro_id=uuid.uuid4(),
                           estudios_reservados=[])


def test_uso_por_rol_se_acumula() -> None:
    e = _extraccion()
    e.registrar_uso("extractor", {"entrada": 10, "salida": 5, "costo_usd": 0.5})
    e.registrar_uso("extractor", {"entrada": 3, "salida": 1, "costo_usd": 0.25})
    r = e.uso_tokens["extractor"]
    assert (r["llamadas"], r["entrada"], r["salida"], r["costo_usd"]) == (2, 13, 6, 0.75)


def test_comparacion_tolerancia_y_numero_de_filas() -> None:
    a = [{"fila": {"Estudio": 1, "Muestra": 395, "Correlación Feli 1 - JP": 0.7301, "Nivel": "Individual"},
          "trazabilidad": {"tipo_de_efecto": "beta estandarizado"}}]
    b = [{"fila": {"Estudio": 1, "Muestra": 395, "Correlación Feli 1 - JP": 0.73, "Nivel": "Individual "},
          "trazabilidad": {"tipo_de_efecto": "beta no estandarizado"}}]
    c = comparar(a, b)
    assert [d.campo for d in c.diferencias] == ["tipo_de_efecto"]
    assert (c.coincidencias, c.total) == (21, 22)
    assert comparar(a, b + b).diferencias[0].campo == "número de filas"
    assert iguales(1, 1.0005) and not iguales(True, 1) and not iguales(1, 1.002)


def test_veredictos_del_modelo() -> None:
    assert veredicto_de("NO VERIFICABLE") == Veredicto.NO_VERIFICABLE
    assert veredicto_de("Refutado: falta fila") == Veredicto.REFUTADO
    assert veredicto_de("CONFIRMADO") == Veredicto.CONFIRMADO


def test_json_de_respuestas() -> None:
    assert json_de('Aquí está:\n```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert json_de('[{"a": 1}]\nRevisé todo.') == [{"a": 1}]
    with pytest.raises(RespuestaInvalida):
        json_de("sin json")


def test_clasificar_salida_del_validador() -> None:
    r = clasificar("ERROR   V3 fila 1: falta Muestra\nAVISO   V20 fila 1: revisar\n\n1 filas | 1 errores | 1 advertencias")
    assert (r.errores, r.avisos) == (["V3 fila 1: falta Muestra"], ["V20 fila 1: revisar"])
    r = clasificar("fila 0: 'x' is not valid\nfila 1: 'y'\n\n2 errores de esquema; corrija antes de las demás validaciones.")
    assert r.errores == ["fila 0: 'x' is not valid", "fila 1: 'y'"]


def test_bloque_id_segun_el_libro(libro: dict) -> None:  # type: ignore[type-arg]
    assert admite_bloque_id(libro)  # libro 2.2 (H5)
    salida = [{"trazabilidad": {"evidencia": {"Muestra": [{"cita_textual": "x", "bloque_id": "p01-b01"}]}}}]
    assert sin_bloque_id(salida)[0]["trazabilidad"]["evidencia"]["Muestra"] == [{"cita_textual": "x"}]
    assert salida[0]["trazabilidad"]["evidencia"]["Muestra"][0]["bloque_id"] == "p01-b01"


def test_regla_del_conciliador_para_campos_estructurales(libro: dict) -> None:  # type: ignore[type-arg]
    """H10: el número de filas se decide con regla_para_abrir_una_fila_nueva."""
    construccion = libro["como_se_construye_cada_fila"]
    assert regla_para_campo(libro, "número de filas") == construccion["regla_para_abrir_una_fila_nueva"]
    assert regla_para_campo(libro, "Muestra") == libro["columnas"]["Muestra"]["instruccion_operativa"]
    assert regla_para_campo(libro, "tipo_de_efecto") == libro["trazabilidad_por_fila"]["campos"]["tipo_de_efecto"]


def test_el_avance_sube_por_hitos_y_nunca_baja() -> None:
    e = _extraccion()
    assert (e.progreso, e.paso) == (0, "preparando")
    e.avanzar("preparando")
    e.avanzar("extrayendo")
    assert e.progreso == 8
    e.avanzar("corrigiendo")
    assert e.progreso == 45
    e.avanzar("extrayendo")  # volver a un hito anterior cambia el paso mostrado pero no baja el porcentaje
    assert e.progreso == 45
    e.avanzar("conciliando", 200)  # un valor fuera del hito se recorta a su tope
    assert e.progreso == 99


def test_completar_deja_el_avance_en_100() -> None:
    e = _extraccion()
    _hasta_conciliar(e)
    e.completar(acuerdo=0.95)
    assert (e.progreso, e.paso) == (100, "completada")

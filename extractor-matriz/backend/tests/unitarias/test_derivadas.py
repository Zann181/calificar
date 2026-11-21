"""Columnas derivadas del libro v2.3 (ADR 0008): las calcula el programa con reglas que salen del libro."""

from __future__ import annotations

from typing import Any

import pytest

from app.compartido.columnas import DefinicionDeColumna
from app.contextos.matriz.dominio.derivadas import calcular


def cultura(por_clave: dict[str, DefinicionDeColumna], pais: Any) -> Any:
    return calcular(por_clave["Cultura Hofstede"], {"Pais": pais}, {}).valor


@pytest.mark.parametrize(("pais", "esperado"), [
    ("Estados Unidos", "Individualista"), ("España", "Individualista"), ("India", "Colectivista"),
    ("China", "Colectivista"), ("Gran Bretaña", "Individualista"),  # alias de Reino Unido
    ("Francia", "Individualista"), ("Irán", "Colectivista"), ("Taiwán", "Colectivista"),
    ("Australia", "Individualista"), ("Emiratos Árabes Unidos", "Colectivista"),
    ("Multinacional", "No indica"), ("Narnia", "No indica"), (None, "No indica"), ("", "No indica"),
])
def test_cultura_hofstede_por_pais(por_clave: dict[str, DefinicionDeColumna], pais: Any, esperado: str) -> None:
    assert cultura(por_clave, pais) == esperado


def test_la_tabla_idv_cubre_todos_los_paises_de_la_matriz(por_clave: dict[str, DefinicionDeColumna]) -> None:
    tabla = por_clave["Cultura Hofstede"].derivada["tabla_idv"]  # type: ignore[index]
    for pais in ("España", "Estados Unidos", "China", "Australia", "Pakistán", "Turquía", "India", "Canadá",
                 "Reino Unido", "Países Bajos", "Emiratos Árabes Unidos", "Malasia", "Irán", "Portugal", "Francia",
                 "Japón", "Taiwán"):
        assert isinstance(tabla[pais], int), pais


def test_id_muestra_refleja_la_trazabilidad(por_clave: dict[str, DefinicionDeColumna]) -> None:
    d = calcular(por_clave["ID muestra"], {}, {"id_muestra": "D28-M2"}, documento=28)
    assert d.valor == "D28-M2"


def test_id_muestra_provisional_solo_en_filas_heredadas(por_clave: dict[str, DefinicionDeColumna]) -> None:
    col = por_clave["ID muestra"]
    assert calcular(col, {}, {}, documento=28, provisional=True).valor == "D28-M1"
    assert calcular(col, {}, {}, documento=28).valor is None


def test_metodo_obtencion_r_refleja_la_trazabilidad(por_clave: dict[str, DefinicionDeColumna]) -> None:
    col = por_clave["Método obtención r"]
    assert calcular(col, {}, {"metodo_obtencion_r": "Pearson observado"}).valor == "Pearson observado"
    assert calcular(col, {}, {}, provisional=True).valor is None


def conjunto(por_clave: dict[str, DefinicionDeColumna], condicion: int | None, enfoque: str | None = None) -> Any:
    motivo = None if condicion is None else f"Condición {condicion}: lo que sea"
    return calcular(por_clave["Conjunto MA"], {"Hedónica/eudaimónica": enfoque},
                    {"motivo_decision_inclusion": motivo}).valor


@pytest.mark.parametrize(("condicion", "enfoque", "esperado"), [
    (6, "Hedónica", "Principal_Hedonico"), (6, "Eudaimónica", "Principal_Eudaimonico"),
    (6, "Hedónica y eudaimónica", "Principal_Mixto"), (6, None, None), (6, "otra cosa", None),
    (7, "Hedónica", "Sensibilidad"), (9, "Hedónica", "Sensibilidad"),
    # Decisión del responsable (ADR 0008): Multinivel (5) y PLS (8) → Excluir; la 10 queda por confirmar.
    (5, "Hedónica", "Excluir"), (8, "Hedónica", "Excluir"), (10, "Hedónica", "Excluir"),
    (1, None, "Excluir"), (2, None, "Excluir"), (3, None, "Excluir"), (4, None, "Excluir"), (11, None, "Excluir"),
    (None, "Hedónica", None),
])
def test_conjunto_ma_segun_la_condicion_del_arbol(por_clave: dict[str, DefinicionDeColumna], condicion: int | None,
                                                  enfoque: str | None, esperado: Any) -> None:
    assert conjunto(por_clave, condicion, enfoque) == esperado


def test_conjunto_ma_da_siempre_un_valor_del_vocabulario(por_clave: dict[str, DefinicionDeColumna]) -> None:
    permitidos = set(por_clave["Conjunto MA"].valores_permitidos or ())
    for condicion in range(1, 12):
        v = conjunto(por_clave, condicion, "Hedónica y eudaimónica")
        assert v in permitidos


def test_solo_las_cuatro_derivadas_lo_son(columnas: list[DefinicionDeColumna]) -> None:
    assert {c.clave for c in columnas if c.es_derivada} == {
        "ID muestra", "Método obtención r", "Cultura Hofstede", "Conjunto MA"}
    assert {c.clave for c in columnas if c.agregada_en_version} == {
        "ID muestra", "Método obtención r", "Constructo desempeño", "Cultura Hofstede", "Conjunto MA"}


def test_compatibilidad_desempeno_y_constructo_cubre_ambos_vocabularios(libro: dict[str, Any]) -> None:
    comp = libro["vocabularios_controlados"]["columnas"]["Constructo desempeño"]["compatibilidad_con_desempeno"]
    desempenos = libro["columnas"]["Desempeño"]["instruccion_operativa"]["valores_permitidos"]
    constructos = libro["columnas"]["Constructo desempeño"]["instruccion_operativa"]["valores_permitidos"]
    assert set(comp) == set(desempenos)
    assert {x for v in comp.values() for x in v} == set(constructos)

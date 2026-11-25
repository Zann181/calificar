"""Descubrimiento · Fase 2 por la API: columnas con prioridad, perfiles, evaluación, vista previa y exportación."""
# ruff: noqa: F811  (las fixtures importadas de test_descubrimiento se «redefinen» como argumentos: así funciona pytest)

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor
from tests.conftest import MATRIZ
from tests.integracion.test_descubrimiento import (  # noqa: F401  (fixtures que se reutilizan)
    FuenteFalsa,
    buscar,
    cliente,
    ctx,
    pid,
    reg,
)

RICO = reg("a", "Happiness and job performance in hospital nurses", "10.1000/rico", anio=2023,
           resumen="This study examines happiness and job performance. A sample of 300 nurses completed the Subjective "
                   "Happiness Scale (alpha for the happiness scale = .90). Happiness predicted performance (r = .35).")
POBRE = reg("a", "Happiness at work and performance", "10.1000/pobre", anio=2021, resumen="")
REVISION = reg("a", "Happiness and performance: a systematic review", "10.1000/rev", anio=2024, resumen="A review.")


@pytest.fixture
def con_candidatos(ctx: Contenedor, pid: uuid.UUID) -> uuid.UUID:  # noqa: F811
    ctx.descubrimiento.buscar._fuentes = {"a": FuenteFalsa("a", [POBRE, RICO, REVISION])}  # type: ignore[assignment]
    buscar(ctx, pid, ("a",))
    return pid


def test_api_catalogo_de_columnas_con_su_detectabilidad(cliente: TestClient, pid: uuid.UUID) -> None:  # noqa: F811
    r = cliente.get(f"/api/v1/proyectos/{pid}/busqueda/columnas").json()
    assert len(r["columnas"]) == 59 and "Datos bibliográficos" in r["grupos"]
    por = {c["clave"]: c for c in r["columnas"]}
    assert por["Muestra"]["nivel"] == "R" and por["Muestra"]["elegible"]
    assert por["Documento"]["nivel"] == "X" and not por["Documento"]["elegible"]
    assert por["Sector"]["vocabulario"] == 15 and por["Cultura Hofstede"]["derivada"] is True


def test_api_perfiles_inicial_guardar_predeterminar_y_borrar(cliente: TestClient, pid: uuid.UUID) -> None:  # noqa: F811
    base = f"/api/v1/proyectos/{pid}/busqueda/perfiles"
    r = cliente.get(base).json()
    assert r["perfiles"] == [] and r["activo"]["nombre"] == "Esencial para metaanálisis"
    assert [c["prioridad"] for c in r["inicial"]["columnas"]][:4] == ["IMPRESCINDIBLE"] * 4

    cols = [{"clave": "Año", "prioridad": "DESEABLE"}, {"clave": "Muestra", "prioridad": "IMPRESCINDIBLE"}]
    a = cliente.put(base, json={"nombre": "Mi perfil", "columnas": cols, "predeterminado": True}).json()
    assert [c["clave"] for c in a["columnas"]] == ["Año", "Muestra"]  # el orden de la persona se conserva
    b = cliente.put(base, json={"nombre": "Otro", "columnas": cols, "predeterminado": True}).json()
    lista = cliente.get(base).json()
    assert {p["nombre"]: p["predeterminado"] for p in lista["perfiles"]} == {"Mi perfil": False, "Otro": True}
    assert lista["activo"]["id"] == b["id"]
    cols2 = [{"clave": "Pais", "prioridad": "IMPORTANTE"}]
    assert cliente.put(base, json={"nombre": "Otro", "columnas": cols2}).json()["id"] == b["id"]  # upsert por nombre
    assert len(cliente.get(base).json()["perfiles"]) == 2
    assert cliente.delete(f"{base}/{a['id']}").status_code == 200
    assert cliente.delete(f"{base}/{uuid.uuid4()}").status_code == 404


def test_api_perfil_rechaza_columnas_internas_inexistentes_y_prioridades_raras(
        cliente: TestClient, pid: uuid.UUID) -> None:  # noqa: F811
    base = f"/api/v1/proyectos/{pid}/busqueda/perfiles"
    assert cliente.put(base, json={"nombre": "x", "columnas": [{"clave": "Documento"}]}).status_code == 409
    assert cliente.put(base, json={"nombre": "x", "columnas": [{"clave": "No existe"}]}).status_code == 409
    assert cliente.put(base, json={"nombre": "x", "columnas": [{"clave": "Año", "prioridad": "MUCHA"}]}).status_code == 422
    assert cliente.put(base, json={"nombre": "x", "columnas": [{"clave": "Año"}, {"clave": "Año"}]}).status_code == 409
    assert cliente.put(base, json={"nombre": "x", "columnas": []}).status_code == 422


def test_api_candidatos_vienen_evaluados_y_se_ordenan_por_puntaje(cliente: TestClient,
                                                                   con_candidatos: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{con_candidatos}"
    cols = [{"clave": "Muestra", "prioridad": "IMPRESCINDIBLE"}, {"clave": "Beta Fel 1- JP", "prioridad": "DESEABLE"},
            {"clave": "Año", "prioridad": "DESEABLE"}]
    cliente.put(f"{base}/busqueda/perfiles", json={"nombre": "Prueba", "columnas": cols, "predeterminado": True})
    r = cliente.get(f"{base}/candidatos", params={"orden": "puntaje"}).json()
    assert r["perfil"]["nombre"] == "Prueba" and r["total"] == 3
    titulos = [c["titulo"] for c in r["candidatos"]]
    assert titulos[0] == RICO.titulo and titulos[-1] == REVISION.titulo  # la revisión («No aplica») va al final
    rico = r["candidatos"][0]["evaluacion"]
    assert rico["etiqueta"] == "PROBABLE" and rico["puntaje"] > 0.6
    estados = {c["columna"]: c["estado"] for c in rico["celdas"]}
    assert estados == {"Muestra": "INDICIO", "Beta Fel 1- JP": "PENDIENTE", "Año": "METADATO"}
    assert rico["celdas"][0]["valor"] == "300"
    assert r["candidatos"][-1]["evaluacion"]["etiqueta"] == "NO_APLICA"
    assert [c["columna"] for c in rico["celdas"]] == ["Muestra", "Beta Fel 1- JP", "Año"]  # orden del perfil


def test_api_exigir_oculta_sin_borrar(cliente: TestClient, con_candidatos: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{con_candidatos}"
    cliente.put(f"{base}/busqueda/perfiles", json={"nombre": "P", "predeterminado": True,
                                                   "columnas": [{"clave": "Muestra", "prioridad": "IMPRESCINDIBLE"}]})
    todos = cliente.get(f"{base}/candidatos", params={"exigir": "nada"}).json()
    confirmadas = cliente.get(f"{base}/candidatos", params={"exigir": "confirmadas"}).json()
    sin_ausentes = cliente.get(f"{base}/candidatos", params={"exigir": "sin_ausentes"}).json()
    assert todos["total"] == 3 and confirmadas["total"] == 1 and sin_ausentes["total"] == 2
    assert cliente.get(f"{base}/candidatos").json()["total"] == 3  # nada se borró
    assert cliente.get(f"{base}/candidatos", params={"orden": "raro"}).status_code == 422


def test_api_vista_previa_no_toca_la_matriz(cliente: TestClient, ctx: Contenedor,  # noqa: F811
                                            con_candidatos: uuid.UUID) -> None:
    ctx.matriz.importar.ejecutar(con_candidatos, MATRIZ.read_bytes(), MATRIZ.name)
    antes = len(ctx.matriz.consultas.todas(con_candidatos))
    base = f"/api/v1/proyectos/{con_candidatos}"
    ids = [c["id"] for c in cliente.get(f"{base}/candidatos").json()["candidatos"]]
    r = cliente.post(f"{base}/candidatos/vista-previa", json={"ids": ids})
    assert r.status_code == 200 and r.json()["sin_verificar"] is True and len(r.json()["candidatos"]) == 3
    primero = r.json()["candidatos"][0]
    assert primero["evaluacion"]["celdas"] and primero["titulo"]
    assert len(ctx.matriz.consultas.todas(con_candidatos)) == antes  # la regla de ubicación: nada entra a la matriz
    assert cliente.post(f"{base}/candidatos/vista-previa", json={"ids": []}).status_code == 422
    assert cliente.post(f"{base}/candidatos/vista-previa", json={"ids": [str(uuid.uuid4())]}).json()["candidatos"] == []


def test_api_exportar_csv_y_ris(cliente: TestClient, con_candidatos: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{con_candidatos}"
    ids = [c["id"] for c in cliente.get(f"{base}/candidatos").json()["candidatos"]]
    csv_ = cliente.post(f"{base}/candidatos/exportar", json={"ids": ids, "formato": "csv"})
    assert csv_.status_code == 200 and 'filename="candidatos.csv"' in csv_.headers["content-disposition"]
    assert csv_.content.startswith(b"\xef\xbb\xbfT") and b"[estado]" in csv_.content
    ris = cliente.post(f"{base}/candidatos/exportar", json={"ids": ids, "formato": "ris"})
    assert ris.status_code == 200 and ris.text.count("TY  - ") == 3 and "DO  - 10.1000/rico" in ris.text
    assert cliente.post(f"{base}/candidatos/exportar", json={"ids": ids, "formato": "pdf"}).status_code == 422

"""Filas extraídas y revisión de celdas por la API (aprobar, corregir, rechazar)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.compartido.seguridad import crear_usuario
from app.composicion import Contenedor
from app.config import Settings
from app.contextos.matriz.dominio.fila import (
    Celda,
    EstadoRevision,
    Evidencia,
    FilaDeEfecto,
    Origen,
    TipoValor,
)
from app.main import crear_app
from tests.conftest import MATRIZ

CORREO, CLAVE = "revisor@local.test", "clave-de-prueba-123"


def evidencia(nivel: str) -> Evidencia:
    return Evidencia(pagina_pdf=3, ubicacion="Tabla 1", cita_textual=".73**", bloque_id="p03-b09",
                     ancla={"nivel": nivel, "bloque_id": "p03-b09", "pagina": 3, "rect": [1, 2, 3, 4]})


def test_nivel_ancla_define_el_estado_inicial() -> None:
    def celda(*niveles: str) -> Celda:
        return Celda.extraida(clave="Muestra", valor=395, estado_dato=None, tipo_valor=TipoValor.LITERAL,
                              evidencias=[evidencia(n) for n in niveles])

    assert celda("VERIFICADA").estado_revision == EstadoRevision.PENDIENTE
    assert celda("VERIFICADA", "POR_CONFIRMAR").estado_revision == EstadoRevision.POR_CONFIRMAR
    assert celda("POR_CONFIRMAR", "NO_VERIFICABLE").nivel_ancla == "NO_VERIFICABLE"
    assert celda().estado_revision == EstadoRevision.PENDIENTE


@pytest.fixture
def con_extraida(contenedor: Contenedor, proyecto: uuid.UUID) -> uuid.UUID:
    contenedor.matriz.importar.ejecutar(proyecto, MATRIZ.read_bytes(), MATRIZ.name)
    columnas = contenedor.normas.consultas.columnas(proyecto)
    celdas = {c.clave: Celda.extraida(clave=c.clave, valor=None, estado_dato="No indica", tipo_valor=TipoValor.FALTANTE,
                                      evidencias=[]) for c in columnas if c.es_numerica}
    celdas["Correlación Feli 1 - JP"] = Celda.extraida(
        clave="Correlación Feli 1 - JP", valor=0.73, estado_dato=None, tipo_valor=TipoValor.CODIFICADO,
        evidencias=[evidencia("VERIFICADA")])
    celdas["Pais"] = Celda.extraida(clave="Pais", valor="India", estado_dato=None, tipo_valor=TipoValor.LITERAL,
                                    evidencias=[evidencia("NO_VERIFICABLE")])
    fila = FilaDeEfecto.extraida(proyecto_id=proyecto, estudio=1, documento=1, articulo_id=uuid.uuid4(),
                                 version_libro_id=contenedor.normas.consultas.libro_activo(proyecto).id, celdas=celdas,
                                 trazabilidad={"auditoria": [{"columna": "Pais", "veredicto": "REFUTADO",
                                                              "hallazgo": "x", "estado": "Pendiente"}]})
    assert contenedor.matriz.escribir_extraidas.ejecutar(proyecto, [fila]) == 1
    return proyecto


def test_extraida_reemplaza_la_heredada(contenedor: Contenedor, con_extraida: uuid.UUID) -> None:
    filas = contenedor.matriz.consultas.todas(con_extraida)
    assert len(filas) == 71
    assert contenedor.matriz.consultas.fila(con_extraida, 1).origen == Origen.EXTRAIDA


@pytest.fixture
def cliente(contenedor: Contenedor, ajustes: Settings, con_extraida: uuid.UUID) -> Iterator[TestClient]:
    with contenedor.fabrica() as s:
        crear_usuario(s, correo=CORREO, nombre="Revisor", rol="revisor", clave=CLAVE)
    with TestClient(crear_app(ajustes, contenedor)) as c:
        assert c.post("/api/v1/sesion", json={"correo": CORREO, "clave": CLAVE}).status_code == 200
        yield c


def ruta(pid: uuid.UUID, clave: str, accion: str = "") -> str:
    return f"/api/v1/proyectos/{pid}/matriz/filas/1/celdas/{clave}" + (f"/{accion}" if accion else "")


def test_resumen_trae_nivel_y_hallazgo(cliente: TestClient, con_extraida: uuid.UUID) -> None:
    fila = next(f for f in cliente.get(f"/api/v1/proyectos/{con_extraida}/matriz/filas").json()["filas"] if f["estudio"] == 1)
    assert fila["celdas"]["Correlación Feli 1 - JP"]["nivel_ancla"] == "VERIFICADA"
    assert fila["celdas"]["Pais"]["hallazgo"] is True
    detalle = cliente.get(ruta(con_extraida, "Pais")).json()
    assert detalle["hallazgos"][0]["veredicto"] == "REFUTADO"


def test_aprobar_registra_al_usuario_de_la_sesion(cliente: TestClient, con_extraida: uuid.UUID) -> None:
    r = cliente.post(ruta(con_extraida, "Correlación Feli 1 - JP", "aprobar"), json={})
    assert r.status_code == 200 and r.json()["estado_revision"] == "APROBADA"
    historial = cliente.get(ruta(con_extraida, "Correlación Feli 1 - JP")).json()["historial"]
    assert historial[-1]["autor"] == CORREO


def test_aprobar_no_verificable_exige_motivo(cliente: TestClient, con_extraida: uuid.UUID) -> None:
    assert cliente.post(ruta(con_extraida, "Pais", "aprobar"), json={}).status_code == 409
    r = cliente.post(ruta(con_extraida, "Pais", "aprobar"), json={"motivo": "Visto en la p. 3"})
    assert r.json()["estado_revision"] == "APROBADA"


def test_corregir_y_rechazar(cliente: TestClient, con_extraida: uuid.UUID) -> None:
    assert cliente.post(ruta(con_extraida, "Muestra", "corregir"), json={"valor": 390, "motivo": ""}).status_code == 409
    r = cliente.post(ruta(con_extraida, "Muestra", "corregir"), json={"valor": 390, "motivo": "Tabla 1: N = 390"})
    assert r.json()["valor"] == 390 and r.json()["estado_revision"] == "CORREGIDA"
    r = cliente.post(ruta(con_extraida, "Pais", "rechazar"), json={"motivo": "El país no aparece"})
    assert r.json()["estado_revision"] == "RECHAZADA"

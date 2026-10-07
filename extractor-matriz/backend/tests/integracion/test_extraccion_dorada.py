"""Pruebas doradas de la sección 8.5, de punta a punta.

ConversorFijo (salidas guardadas de MinerU), ScriptValidador y PyMuPDF reales, y ModeloGrabado con las
respuestas de la prueba F0 (docs/decisiones/f0/extraccion/*__claude-opus-5-5). Nada llama al modelo.
La corrida de Singh en F0 es anterior al libro 2.2: su bloque_id está en anclas.json y aquí se integra a
cada evidencia, como haría el extractor con el libro vigente.
"""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from sqlalchemy.orm import Session

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.extraccion.adaptadores.modelo_grabado import ModeloGrabado
from app.contextos.extraccion.aplicacion.casos_de_uso import OpcionesDeExtraccion
from app.contextos.extraccion.dominio.anclaje import NivelAncla
from app.contextos.extraccion.dominio.comparacion import comparar
from app.contextos.matriz.dominio.fila import EstadoRevision, Origen
from tests.conftest import FIXTURES, MATRIZ, RAIZ
from tests.integracion.conftest import nuevo_proyecto

pytestmark = pytest.mark.dorada

F0 = RAIZ / "docs" / "decisiones" / "f0" / "extraccion"
PENDIENTE = json.dumps({"decision": "PENDIENTE", "razonamiento": "Decide el responsable del dominio"})


def _salida_f0(carpeta: Path) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = json.loads((carpeta / "salida.json").read_text(encoding="utf-8"))
    anclas = carpeta / "anclas.json"
    if anclas.exists():
        for clave, bloque in json.loads(anclas.read_text(encoding="utf-8")).items():
            i, col, j = clave.split("|")
            evidencias = salida[int(i)]["trazabilidad"]["evidencia"].get(col) or []
            if int(j) < len(evidencias):
                evidencias[int(j)].setdefault("bloque_id", bloque)
    return salida


def _contenedor(fabrica: Callable[[], Session], ajustes: Settings, modelo: ModeloGrabado) -> Contenedor:
    return construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(),
                     conversor=ConversorFijo(FIXTURES / "mineru"), modelo=modelo)


def _cargar(c: Contenedor, pid: uuid.UUID, nombre: str) -> uuid.UUID:
    r = c.biblioteca.cargar.ejecutar(pid, f"{nombre}.pdf", (FIXTURES / f"{nombre}.pdf").read_bytes())
    assert r.articulo_id is not None
    assert c.biblioteca.convertir.ejecutar(pid, r.articulo_id) == EstadoArticulo.LISTO
    return r.articulo_id


def _evidencia(salida: list[dict[str, Any]], estudio: int, columna: str, indice: int) -> dict[str, Any]:
    item = next(f for f in salida if f["fila"]["Estudio"] == estudio)
    evidencia: dict[str, Any] = item["trazabilidad"]["evidencia"][columna][indice]
    return evidencia


def test_kumar(fabrica: Callable[[], Session], ajustes: Settings, libro_json: dict[str, Any]) -> None:
    carpeta = F0 / "kumar_2022__claude-opus-5-5"
    modelo = ModeloGrabado(por_rol={
        "extractor": json.dumps(_salida_f0(carpeta), ensure_ascii=False),
        "auditor": (carpeta / "auditoria_evidencia.json").read_text(encoding="utf-8"),
        "ciego": (carpeta / "codificacion_ciega.json").read_text(encoding="utf-8"),
        "conciliador": PENDIENTE,
    })
    c = _contenedor(fabrica, ajustes, modelo)
    pid = nuevo_proyecto(c, "Felicidad y desempeño")
    c.normas.publicar.ejecutar(pid, libro_json)
    c.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    aid = _cargar(c, pid, "kumar_2022")

    r = c.extraccion.extraer.ejecutar(pid, aid, OpcionesDeExtraccion(documento=1, estudio_inicial=1, covidence=671))
    ext = c.extraccion.consultas.obtener(pid, r.extraccion_id)
    assert r.estado == "COMPLETADA", r.errores
    assert ext.errores_validador == [] and ext.iteraciones_validador == 1

    # Los campos críticos coinciden con ejemplo_verificado.salida del libro.
    verificado = comparar(ext.salida, libro_json["ejemplo_verificado"]["salida"])
    assert verificado.diferencias == () and verificado.total == 22

    # Las citas que no son de tabla ni de figura quedan VERIFICADA (32 en el ejemplo verificado; 39 en esta salida).
    de_texto = [a for a in ext.anclas
                if not a.leido_de_figura and not _evidencia(ext.salida, a.estudio, a.columna, a.indice_evidencia).get("fila_tabla")]
    assert len(de_texto) >= 32
    assert {a.nivel for a in de_texto} == {NivelAncla.VERIFICADA}

    # El auditor marcó la posible fila de satisfacción laboral y el conciliador la dejó pendiente (INFORME_F0).
    assert ext.acuerdo_campos_criticos == 1.0
    assert any(h.veredicto.value == "REFUTADO" and h.estado.value == "PENDIENTE" for h in ext.hallazgos)

    # ExtraccionCompletada → Matriz escribe la fila y el artículo queda POR_REVISAR.
    while c.despachador.despachar_pendientes():
        pass
    assert c.biblioteca.consultas.articulo(pid, aid).estado == EstadoArticulo.POR_REVISAR
    fila = c.matriz.consultas.fila(pid, 1)
    assert fila.origen == Origen.EXTRAIDA and fila.articulo_id == aid
    muestra = fila.celdas["Muestra"]
    assert muestra.valor == 395 and muestra.estado_revision == EstadoRevision.PENDIENTE
    assert muestra.evidencias[0].ancla is not None and muestra.evidencias[0].ancla["nivel"] == "VERIFICADA"
    assert fila.trazabilidad["extraccion_id"] == str(ext.id)
    assert any(h["estado"] == "Pendiente" for h in fila.trazabilidad["auditoria"])

    # La exportación lleva la fila extraída y su hoja Auditoria.
    e = c.exportar.ejecutar(pid)
    libro_excel = openpyxl.load_workbook(io.BytesIO(c.exportar.leer(pid, e.id)))
    assert e.filas_extraidas == 1
    assert libro_excel["Auditoria"].max_row > 1


def test_singh(fabrica: Callable[[], Session], ajustes: Settings, libro_json: dict[str, Any]) -> None:
    salida = _salida_f0(F0 / "singh_2023__claude-opus-5-5")
    texto = json.dumps(salida, ensure_ascii=False)
    c = _contenedor(fabrica, ajustes, ModeloGrabado(por_rol={"extractor": texto, "auditor": "[]", "ciego": texto,
                                                             "conciliador": PENDIENTE}))
    pid = nuevo_proyecto(c, "Felicidad y desempeño")
    c.normas.publicar.ejecutar(pid, libro_json)
    aid = _cargar(c, pid, "singh_2023")

    r = c.extraccion.extraer.ejecutar(pid, aid, OpcionesDeExtraccion(
        documento=47, estudio_inicial=71, via="Otros métodos: búsqueda manual"))
    assert r.estado == "COMPLETADA", r.errores
    ext = c.extraccion.consultas.obtener(pid, r.extraccion_id)
    [item] = ext.salida
    fila, traz = item["fila"], item["trazabilidad"]
    assert fila["Incluir en meta análisi"] == "SEM latente"
    assert "Condición 9" in traz["motivo_decision_inclusion"]
    assert traz["confianza"] == "Baja"
    assert any(d["columna"] == "Beta Fel 1- JP" for d in traz["discrepancias_en_el_articulo"])
    assert r.anclas["NO_VERIFICABLE"] <= 1

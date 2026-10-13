"""Portero de modelos (ADR 0005): especializado o ligero según rol, artículo y campo."""

from __future__ import annotations

import json
import uuid

import pytest

from app.contextos.extraccion.adaptadores.claude_cli import ClaudeCli
from app.contextos.extraccion.adaptadores.modelo_grabado import ModeloGrabado
from app.contextos.extraccion.aplicacion.casos_de_uso import ExtraerArticulo, OpcionesDeExtraccion
from app.contextos.extraccion.dominio.documento import DocumentoDeTrabajo
from app.contextos.extraccion.dominio.portero import Nivel, decidir_ciego, decidir_conciliador, decidir_rol
from app.contextos.extraccion.puertos import ArticuloParaExtraer
from tests.unitarias.test_extraer_articulo import (
    AID,
    PID,
    SALIDA,
    Fuente,
    Lector,
    Normas,
    Numeracion,
    Udt,
    Validador,
    _salida,
)

SENCILLO = {"bloques": [
    {"id": "p03-b01", "pagina": 3, "tipo": "parrafo", "rect": [0, 0, 100, 20],
     "texto": "The study is based on a sample of 395 teachers.", "tabla": None},
    {"id": "p03-b02", "pagina": 3, "tipo": "parrafo", "rect": [0, 30, 100, 50],
     "texto": "A sample of 400 teachers was invited.", "tabla": None},
]}


def _doc(*textos: str, figura: bool = False) -> DocumentoDeTrabajo:
    bloques = [{"id": f"p01-b{i:02d}", "pagina": 1, "tipo": "parrafo", "rect": [0, 0, 1, 1], "texto": t, "tabla": None}
               for i, t in enumerate(textos)]
    if figura:
        bloques.append({"id": "p02-b01", "pagina": 2, "tipo": "figura", "rect": [0, 0, 1, 1], "texto": "", "tabla": None})
    return DocumentoDeTrabajo.desde_dict({"bloques": bloques})


@pytest.mark.parametrize("rol", ["extractor", "auditor"])
def test_extractor_y_auditor_siempre_especializados(rol: str) -> None:
    assert decidir_rol(rol).nivel == Nivel.ESPECIALIZADO


def test_ciego_ligero_en_articulo_sencillo() -> None:
    assert decidir_ciego(_doc("A sample of 395 teachers."), "A sample of 395 teachers.").nivel == Nivel.LIGERO


@pytest.mark.parametrize(("texto", "figura"), [
    ("A sample of 395 teachers.", True),
    ("We tested the model with structural equation modeling.", False),
    ("Study 2 replicated the design.", False),
    ("x" * 300_001, False),
], ids=["figura", "sem", "varios-estudios", "largo"])
def test_ciego_especializado_con_senales_de_complejidad(texto: str, figura: bool) -> None:
    assert decidir_ciego(_doc(texto, figura=figura), texto).nivel == Nivel.ESPECIALIZADO


def test_conciliador_especializado_solo_en_campos_criticos() -> None:
    assert decidir_conciliador("Tipo de felicidad real").nivel == Nivel.ESPECIALIZADO
    assert decidir_conciliador("número de filas").nivel == Nivel.ESPECIALIZADO
    assert decidir_conciliador("País").nivel == Nivel.LIGERO


def test_claude_cli_rechaza_opus() -> None:
    with pytest.raises(ValueError, match="Opus"):
        ClaudeCli({"especializado": "claude-opus-5-5", "ligero": "claude-haiku-5-5"})


class FuenteSencilla(Fuente):
    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> ArticuloParaExtraer:
        return ArticuloParaExtraer(articulo_id=articulo_id, nombre_archivo="a.pdf", pdf=b"%PDF", documento=SENCILLO)


def _ejecutar(modelo: ModeloGrabado) -> Udt:
    udt = Udt()
    ExtraerArticulo(lambda: udt, FuenteSencilla(), Normas(), Numeracion(), modelo, Validador(), Lector()).ejecutar(
        PID, AID, OpcionesDeExtraccion(documento=1))
    return udt


def test_niveles_en_una_extraccion_sencilla() -> None:
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA), "auditor": "[]", "ciego": json.dumps(SALIDA)})
    _ejecutar(modelo)
    assert dict(modelo.niveles) == {"extractor": "especializado", "auditor": "especializado", "ciego": "ligero"}


def test_ciego_ligero_ilegible_se_repite_con_especializado() -> None:
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA), "auditor": "[]",
                                    "ciego": ["No encontré el JSON", json.dumps(SALIDA)]})
    udt = _ejecutar(modelo)
    assert [n for r, n in modelo.niveles if r == "ciego"] == ["ligero", "especializado"]
    ext = next(iter(udt.guardadas.values()))
    assert ext.estado.value == "COMPLETADA" and ext.uso_tokens["ciego"]["llamadas"] == 2


def test_conciliador_de_campo_critico_usa_especializado() -> None:
    pendiente = json.dumps({"decision": "PENDIENTE", "razonamiento": "Los bloques no alcanzan"})
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(_salida(400, "sample of 400 teachers", "p03-b02")),
                                    "auditor": "[]", "ciego": json.dumps(SALIDA), "conciliador": pendiente})
    _ejecutar(modelo)
    assert [n for r, n in modelo.niveles if r == "conciliador"] == ["especializado"]  # Muestra es crítico


def test_ciego_ligero_con_acuerdo_bajo_se_confirma_con_especializado() -> None:
    ciega = _salida(400, "sample of 400 teachers", "p03-b02")
    ciega[0]["fila"].update({"Nivel": "Grupal", "Desempeño": "Otro", "Study design": "Longitudinal",
                             "Tipo de felicidad real": "Otro"})  # 5 de 22 campos distintos: acuerdo 0,77
    discrepa = json.dumps(ciega)
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA), "auditor": "[]", "ciego": [discrepa, json.dumps(SALIDA)]})
    udt = _ejecutar(modelo)
    assert [n for r, n in modelo.niveles if r == "ciego"] == ["ligero", "especializado"]
    ext = next(iter(udt.guardadas.values()))
    assert ext.acuerdo_campos_criticos == 1.0  # cuenta la codificación de Sonnet, no la de Haiku
    assert not any(r == "conciliador" for r, _ in modelo.llamadas)

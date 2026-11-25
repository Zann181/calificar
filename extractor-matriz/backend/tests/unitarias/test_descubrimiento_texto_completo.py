"""Descubrimiento · etapa B: detectores sobre el texto completo (secciones, referencias, páginas) y su combinación con la A."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.contextos.descubrimiento.adaptadores.detectores_json import cargar_config
from app.contextos.descubrimiento.dominio.candidato import Autor, Candidato, RegistroBibliografico
from app.contextos.descubrimiento.dominio.completitud import (
    AnalisisDeTexto,
    ColumnaElegida,
    Etiqueta,
    PerfilDeColumnas,
    Prioridad,
    celda_final,
    evaluar,
)
from app.contextos.descubrimiento.dominio.detectores import (
    EstadoCelda,
    MotorDeDetectores,
    segmentos_de_texto,
)
from tests.conftest import RECURSOS

PID = uuid.uuid4()
RELLENO = " The study followed standard procedures in the field and the team met every week to review progress."

PAGINA_1 = f"""Happiness and job performance in hospital nurses
Abstract
We studied nurses.{RELLENO}
1. Introduction
Hospital staff face many demands at work and previous studies of retail workers found different patterns.{RELLENO}
Self-determination theory states that autonomy supports well-being.{RELLENO}
"""
PAGINA_2 = f"""2. Method
2.1 Participants
Data were collected between March 2011 and June 2012 from a sample of 300 nurses working in a public hospital.{RELLENO}
The inclusion criteria were at least one year of experience in the unit.{RELLENO}
2.2 Measures
Happiness was measured with the Subjective Happiness Scale, a 4-item scale (Cronbach's alpha for happiness = .88).{RELLENO}
Job performance was rated with the Williams and Anderson scale of 7 items; sample items for performance include "I fulfil the responsibilities".{RELLENO}
A cross-sectional survey design was used and data were analysed with SPSS and AMOS.{RELLENO}
3. Results
Confirmatory factor analysis showed good fit (CFI = .96, RMSEA = .05).{RELLENO}
Happiness was positively correlated with job performance (r = .41, p < .001).{RELLENO}
4. Discussion
Future research should use longitudinal designs in other hospital samples.{RELLENO}
A longitudinal study of banking staff found similar effects.{RELLENO}
"""
PAGINA_3 = f"""Conclusions
We conclude that happy nurses perform better.{RELLENO}
References
Smith, J. (2010). A diary study of retail workers. Journal of Work, 1, 1-10. r = .99 SPSS Stata
"""


def cand(resumen: str = "", titulo: str = "Happiness and job performance in hospital nurses") -> Candidato:
    return Candidato.desde(PID, RegistroBibliografico(fuente="x", id_externo="x", posicion=1, titulo=titulo, anio=2022,
                                                       autores=(Autor("Ana Pérez", "Pérez"),), resumen=resumen))


@pytest.fixture(scope="module")
def motor() -> MotorDeDetectores:
    return MotorDeDetectores(cargar_config(RECURSOS))


PAGINAS = [PAGINA_1, PAGINA_2, PAGINA_3]


def test_las_oraciones_llevan_pagina_y_seccion_y_se_corta_en_referencias() -> None:
    segs = segmentos_de_texto(cand(), PAGINAS)
    cuerpo = [(o, t) for o, t in segs if o.startswith("p. ")]
    origenes = {o for o, _t in cuerpo}
    assert {"p. 1 · introducción", "p. 2 · método", "p. 2 · resultados", "p. 2 · discusión", "p. 3 · discusión"} <= origenes
    texto = " ".join(t for _o, t in cuerpo)
    assert "Stata" not in texto and "diary study of retail" not in texto  # lo que viene tras «References» no cuenta
    assert "Future research should" not in texto  # las propuestas para el futuro no son datos del estudio


def test_detecta_en_el_metodo_y_los_resultados_con_su_pagina(motor: MotorDeDetectores) -> None:
    r = motor.analizar_texto(cand(), PAGINAS)
    c = r.celdas
    assert c["Muestra"].valor == "300" and c["Muestra"].origen == "p. 2 · método"
    assert c["Start date"].valor == "march 2011" and c["End date"].valor == "june 2012"
    assert c["Inclusion criteria"].frase and "inclusion criteria" in c["Inclusion criteria"].frase
    assert c["Items instrumento1"].valor == "4" and c["# Ítems"].valor == "7"
    assert c["Fiabilidad Alfa - Omega (felicidad)"].valor == ".88"
    assert c["Instrumento felicidad"].valor and "Subjective Happiness Scale" in c["Instrumento felicidad"].valor
    assert c["Study design"].valor == "Cross sectional study"  # el «longitudinal» de la discusión no cuenta
    assert c["Software"].valor == "SPSS, AMOS"  # y el «Stata» de las referencias, tampoco
    assert c["CFA"].valor == "Si" and c["Correlación Feli 1 - JP"].valor == "r = .41"
    assert c["Correlación Feli 1 - JP"].origen == "p. 2 · resultados"
    assert "responsibilities" in (c["Ejemplo ítem desempeño"].frase or "")
    assert r.paginas == 3 and r.suficiente is False  # texto de juguete: menos de 4 000 caracteres


def test_cada_seccion_solo_aporta_a_sus_columnas(motor: MotorDeDetectores) -> None:
    solo_cita = [f"1. Introduction\nHospital staff face demands and retail workers differ.{RELLENO}\n"
                 f"2. Method\nWe surveyed 200 people in several places.{RELLENO}\n"
                 f"4. Discussion\nA study of bank employees and a longitudinal study of nurses found similar effects.{RELLENO}\n"]
    c = motor.analizar_texto(cand(titulo="Happiness and performance"), solo_cita).celdas
    assert "Sector" not in c  # «hospital», «retail» y «bank» salen en la introducción y la discusión, no en el método
    assert "Study design" not in c  # y el «longitudinal» de la discusión tampoco es el diseño de este estudio
    en_metodo = [f"2. Method\nWe surveyed 200 nurses in a public hospital.{RELLENO}\n"]
    ok = motor.analizar_texto(cand(titulo="Happiness and performance"), en_metodo).celdas
    assert ok["Sector"].valor == "Salud" and ok["Sector"].origen == "p. 1 · método"


def test_el_resumen_siempre_cuenta_aunque_no_haya_secciones(motor: MotorDeDetectores) -> None:
    r = motor.analizar_texto(cand(resumen="A sample of 250 nurses in a hospital completed the survey."),
                             ["Texto sin encabezados " * 40])
    assert r.celdas["Muestra"].valor == "250" and r.celdas["Muestra"].origen == "resumen"
    assert r.celdas["Sector"].valor == "Salud"


def analisis(motor: MotorDeDetectores, c: Candidato, paginas: list[str], *, suficiente: bool | None = None) -> AnalisisDeTexto:
    r = motor.analizar_texto(c, paginas)
    return AnalisisDeTexto(candidato_id=c.id, celdas=r.celdas, intentadas=r.intentadas, paginas=r.paginas,
                           caracteres=r.caracteres, suficiente=r.suficiente if suficiente is None else suficiente,
                           origen="prueba", analizado_en=datetime.now(UTC))


def perfil(*cols: tuple[str, Prioridad]) -> PerfilDeColumnas:
    return PerfilDeColumnas(proyecto_id=PID, nombre="p", columnas=tuple(ColumnaElegida(c, p) for c, p in cols))


def test_el_resumen_manda_sobre_el_cuerpo_y_el_cuerpo_llena_los_huecos(motor: MotorDeDetectores) -> None:
    c = cand(resumen="A sample of 120 nurses was surveyed.")
    a = analisis(motor, c, PAGINAS, suficiente=True)
    assert celda_final(motor, "Muestra", c, a).valor == "120"  # el resumen, no los 300 del método
    assert celda_final(motor, "Muestra", c, a).origen == "resumen"
    sin_resumen = cand()
    b = analisis(motor, sin_resumen, PAGINAS, suficiente=True)
    assert celda_final(motor, "Muestra", sin_resumen, b).origen == "p. 2 · método"
    assert celda_final(motor, "Beta Fel 1- JP", sin_resumen, b).estado == EstadoCelda.AUSENTE  # buscado y sin indicio


def test_ausente_solo_con_texto_suficiente_y_columna_buscada(motor: MotorDeDetectores) -> None:
    c = cand()
    corto = analisis(motor, c, PAGINAS, suficiente=False)  # PDF casi sin texto (¿escaneado?)
    assert celda_final(motor, "Beta Fel 1- JP", c, corto).estado == EstadoCelda.PENDIENTE
    largo = analisis(motor, c, PAGINAS, suficiente=True)
    assert celda_final(motor, "Beta Fel 1- JP", c, largo).estado == EstadoCelda.AUSENTE
    assert celda_final(motor, "Cultura Hofstede", c, largo).estado == EstadoCelda.NO_APLICA  # interna
    assert celda_final(motor, "Pais", c, largo).estado == EstadoCelda.PENDIENTE  # metadato: el texto no lo cambia
    assert celda_final(motor, "Columna inventada", c, largo).estado == EstadoCelda.PENDIENTE  # sin detector: no se afirma


def test_la_evaluacion_con_texto_completo_sube_el_puntaje_y_se_marca_etapa_b(motor: MotorDeDetectores) -> None:
    c = cand()
    p = perfil(("Muestra", Prioridad.IMPRESCINDIBLE), ("Correlación Feli 1 - JP", Prioridad.IMPRESCINDIBLE),
               ("Software", Prioridad.DESEABLE))
    a_ = evaluar(motor, c, p)
    b_ = evaluar(motor, c, p, analisis(motor, c, PAGINAS, suficiente=True))
    assert a_.etapa == "A" and b_.etapa == "B" and b_.a_dict()["etapa"] == "B"
    assert a_.puntaje == 0 and b_.puntaje == pytest.approx(1.0) and b_.etiqueta == Etiqueta.PROBABLE


def test_una_imprescindible_sin_indicio_en_el_texto_completo_es_incompleto(motor: MotorDeDetectores) -> None:
    c = cand()
    p = perfil(("Muestra", Prioridad.IMPRESCINDIBLE), ("Beta Fel 1- JP", Prioridad.IMPRESCINDIBLE))
    ev = evaluar(motor, c, p, analisis(motor, c, PAGINAS, suficiente=True))
    assert ev.etiqueta == Etiqueta.INCOMPLETO
    ev2 = evaluar(motor, c, p, analisis(motor, c, PAGINAS, suficiente=False))  # sin texto suficiente: no se descarta
    assert ev2.etiqueta == Etiqueta.DUDOSO

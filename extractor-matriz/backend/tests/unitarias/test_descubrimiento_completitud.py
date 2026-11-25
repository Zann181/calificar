"""Descubrimiento · Fase 2: detectabilidad, detectores de la etapa A, cobertura y puntaje (sin IA, sin red)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.compartido.columnas import DefinicionDeColumna
from app.contextos.descubrimiento.adaptadores.detectores_json import cargar_config
from app.contextos.descubrimiento.adaptadores.fuentes.openalex import OpenAlex
from app.contextos.descubrimiento.dominio.candidato import Autor, Candidato, RegistroBibliografico
from app.contextos.descubrimiento.dominio.completitud import (
    PERFIL_INICIAL,
    ColumnaElegida,
    Etiqueta,
    Exigir,
    PerfilDeColumnas,
    Prioridad,
    evaluar,
    no_aplica,
    ordenar_por_puntaje,
    pasa_exigencia,
    perfil_inicial,
)
from app.contextos.descubrimiento.dominio.detectores import (
    EstadoCelda,
    MotorDeDetectores,
    Nivel,
    formatear_cita,
)
from app.contextos.descubrimiento.dominio.exportar import a_csv, a_ris
from tests.conftest import RECURSOS

PID = uuid.uuid4()


@pytest.fixture(scope="module")
def motor() -> MotorDeDetectores:
    return MotorDeDetectores(cargar_config(RECURSOS))


def cand(titulo: str = "Happiness and job performance", resumen: str = "", anio: int = 2022,
         autores: tuple[Autor, ...] = (Autor("Ana Pérez", "Pérez", ("CO",)),), **kw: object) -> Candidato:
    r = RegistroBibliografico(fuente="openalex", id_externo="x", posicion=1, titulo=titulo, anio=anio, autores=autores,
                              resumen=resumen, doi="10.1000/x", **kw)  # type: ignore[arg-type]
    return Candidato.desde(PID, r)


def perfil(*cols: tuple[str, Prioridad]) -> PerfilDeColumnas:
    return PerfilDeColumnas(proyecto_id=PID, nombre="p", columnas=tuple(ColumnaElegida(c, p) for c, p in cols))


# ---- los datos están atados al libro de códigos -------------------------------------------------------------------------
def test_la_clasificacion_cubre_exactamente_las_columnas_del_libro(columnas: list[DefinicionDeColumna]) -> None:
    clasif = json.loads((RECURSOS / "detectabilidad_columnas.json").read_text(encoding="utf-8"))["columnas"]
    assert set(clasif) == {c.clave for c in columnas}, "el libro y detectabilidad_columnas.json no coinciden"
    assert {v["nivel"] for v in clasif.values()} <= {"M", "R", "T", "X"}


def test_las_columnas_derivadas_o_de_identificacion_son_internas(columnas: list[DefinicionDeColumna],
                                                                  motor: MotorDeDetectores) -> None:
    for c in columnas:
        if c.derivada is not None:
            assert motor.nivel(c.clave) == Nivel.X, c.clave
    assert motor.nivel("Muestra") == Nivel.R and motor.nivel("Beta Fel 1- JP") == Nivel.T


def test_los_detectores_solo_nombran_columnas_y_valores_del_libro(columnas: list[DefinicionDeColumna]) -> None:
    por_clave = {c.clave: c for c in columnas}
    det = json.loads((RECURSOS / "detectores_columnas.json").read_text(encoding="utf-8"))["detectores"]
    for clave, cfg in det.items():
        assert clave in por_clave, f"detector para una columna que no existe: {clave}"
        if cfg["tipo"] == "vocabulario":
            permitidos = set(por_clave[clave].valores_permitidos or ())
            assert set(cfg["valores"]) <= permitidos, f"{clave}: valores fuera del libro {set(cfg['valores']) - permitidos}"


def test_el_perfil_inicial_usa_columnas_que_existen(columnas: list[DefinicionDeColumna]) -> None:
    existentes = {c.clave for c in columnas}
    assert {c.clave for c in PERFIL_INICIAL} <= existentes
    p = perfil_inicial(PID, existentes)
    assert p.predeterminado and len(p.imprescindibles) == 4
    assert [c.clave for c in perfil_inicial(PID, {"Muestra"}).columnas] == ["Muestra"]  # omite lo que no existe


# ---- metadatos (M) -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("apellidos", "esperada"), [
    (["Hosie"], "Hosie (2009)"), (["Wright", "Cropanzano"], "Wright y Cropanzano (2009)"),
    (["Wright", "Cropanzano", "Denney"], "Wright et al. (2009)"), ([], None)])
def test_regla_de_cita_del_responsable(apellidos: list[str], esperada: str | None) -> None:
    assert formatear_cita(apellidos, 2009) == esperada
    assert formatear_cita(["Hosie"], None) is None


def test_metadatos_titulo_autor_anio_y_cita(motor: MotorDeDetectores) -> None:
    c = cand(autores=(Autor("Ana Pérez", "Pérez"), Autor("Luis Gómez", "Gómez"), Autor("Eva Ruiz", "Ruiz")))
    assert motor.evaluar("Title", c).valor == "Happiness and job performance"
    assert motor.evaluar("Author", c).valor == "Ana Pérez; Luis Gómez; Eva Ruiz"
    assert motor.evaluar("Año", c).valor == "2022" and motor.evaluar("Cita", c).valor == "Pérez et al. (2022)"
    assert motor.evaluar("Año", c).estado == EstadoCelda.METADATO
    sin = cand(autores=())
    assert motor.evaluar("Author", sin).estado == EstadoCelda.AUSENTE  # la fuente debería traerlo


def test_pais_por_mayoria_de_afiliaciones_y_empate_por_primer_autor(motor: MotorDeDetectores) -> None:
    mayoria = cand(autores=(Autor("A B", "B", ("ES",)), Autor("C D", "D", ("CO",)), Autor("E F", "F", ("CO",))))
    assert motor.evaluar("Pais", mayoria).valor == "Colombia"
    empate = cand(autores=(Autor("A B", "B", ("ES",)), Autor("C D", "D", ("CO",))))
    assert motor.evaluar("Pais", empate).valor == "España"
    sin = cand(autores=(Autor("A B", "B"),))
    assert motor.evaluar("Pais", sin).estado == EstadoCelda.PENDIENTE  # puede estar en el texto: no es «ausente»
    raro = cand(autores=(Autor("A B", "B", ("ZZ",)),))
    assert motor.evaluar("Pais", raro).valor == "ZZ"


def test_columnas_internas_y_nuevas_del_libro(motor: MotorDeDetectores) -> None:
    c = cand()
    assert motor.evaluar("Documento", c).estado == EstadoCelda.NO_APLICA
    assert motor.evaluar("Columna inventada", c).estado == EstadoCelda.PENDIENTE  # se trata como «solo PDF»


# ---- resumen (R) y texto (T) --------------------------------------------------------------------------------------------
def test_muestra_se_lee_de_varias_formas(motor: MotorDeDetectores) -> None:
    for texto, n in [("A total of 462 Peruvian workers answered.", "462"), ("The sample (N = 245) was drawn.", "245"),
                     ("We surveyed a sample of 1,234 employees.", "1234"), ("Data from 80 nurses were analysed.", "80")]:
        celda = motor.evaluar("Muestra", cand(resumen=texto))
        assert celda.estado == EstadoCelda.INDICIO and celda.valor == n, texto
        assert celda.origen == "resumen" and celda.frase and n[:2] in celda.frase.replace(",", "")
    assert motor.evaluar("Muestra", cand(resumen="Sin cifras de muestra.")).estado == EstadoCelda.PENDIENTE
    assert motor.evaluar("Muestra", cand(resumen="Published in 2021 with n = 3.")).estado == EstadoCelda.PENDIENTE


def test_correlacion_y_beta_solo_con_numeros(motor: MotorDeDetectores) -> None:
    c = cand(resumen="Happiness correlated with performance (r = .31, p < .001). The effect of happiness on performance was β = 0.14.")
    r = motor.evaluar("Correlación Feli 1 - JP", c)
    b = motor.evaluar("Beta Fel 1- JP", c)
    assert (r.estado, r.valor) == (EstadoCelda.INDICIO, "r = .31") and b.valor and b.valor.startswith("β = 0.14")
    assert motor.evaluar("Correlacion o Beta felicidad 1 - JP", c).estado == EstadoCelda.INDICIO
    vago = cand(resumen="Happiness was positively correlated with performance.")
    assert motor.evaluar("Correlación Feli 1 - JP", vago).estado == EstadoCelda.PENDIENTE  # sin cifra no hay indicio
    otra = cand(resumen="Age correlated with tenure (r = .45).")  # una correlación que no une felicidad y desempeño
    assert motor.evaluar("Correlación Feli 1 - JP", otra).estado == EstadoCelda.PENDIENTE


def test_fiabilidad_se_atribuye_a_la_escala_correcta(motor: MotorDeDetectores) -> None:
    c = cand(resumen="Cronbach's alpha for the happiness scale was .91. Performance was rated by supervisors.")
    f = motor.evaluar("Fiabilidad Alfa - Omega (felicidad)", c)
    assert f.estado == EstadoCelda.INDICIO and f.valor == ".91"
    assert motor.evaluar("Fiabilidad Alfa - Omega (desempeño)", c).estado == EstadoCelda.PENDIENTE


def test_instrumentos_software_y_teoria(motor: MotorDeDetectores) -> None:
    c = cand(resumen="We used the Subjective Happiness Scale and the Oxford Happiness Questionnaire. Data were "
                     "analysed with SPSS and AMOS. Based on self-determination theory and conservation of resources.")
    assert "Subjective Happiness Scale" in (motor.evaluar("Instrumento felicidad", c).valor or "")
    assert "SPSS" in (motor.evaluar("Software", c).valor or "")
    assert motor.evaluar("Teoría 1", c).valor == "self-determination theory"
    assert motor.evaluar("Teoría 2", c).valor == "conservation of resources"
    assert motor.evaluar("Teoria 3", c).estado == EstadoCelda.PENDIENTE  # solo hay dos


def test_vocabulario_devuelve_el_valor_del_libro(motor: MotorDeDetectores) -> None:
    c = cand(resumen="A longitudinal survey of hospital nurses with structural equation modeling. Randomly selected.")
    assert motor.evaluar("Study design", c).valor == "Longitudinal study"  # gana sobre «survey»
    assert motor.evaluar("Sector", c).valor == "Salud"
    assert motor.evaluar("Analysis method (principal)", c).valor == "CB-SEM"
    assert motor.evaluar("Tipo de muestreo", c).valor == "Muestreo Aleatorio"
    assert motor.evaluar("Hedónica/eudaimónica", cand(resumen="Eudaimonic well-being at work.")).valor == "Eudaimónica"


def test_las_palabras_se_buscan_enteras(motor: MotorDeDetectores) -> None:
    """«perma» no es «permanent»; «Ryff» no es «Ryffle»; el plural sí cuenta."""
    assert motor.evaluar("Tipo de felicidad real", cand(resumen="Permanent contracts were common.")).estado == \
        EstadoCelda.PENDIENTE
    assert motor.evaluar("Tipo de felicidad real", cand(resumen="We use the PERMA model.")).valor == "PERMA"
    assert motor.evaluar("Población", cand(resumen="Participants were hospital employees.")).valor == "employees"


def test_objetivo_y_conclusion_son_oraciones_del_resumen(motor: MotorDeDetectores) -> None:
    c = cand(resumen="Background text. This study examines the link between happiness and performance. We surveyed "
                     "200 staff. In conclusion, happy workers performed better.")
    assert (motor.evaluar("Aim of study", c).valor or "").startswith("This study examines")
    assert (motor.evaluar("Conclusion", c).valor or "").startswith("In conclusion")
    assert motor.evaluar("Aim of study", cand(titulo="This study examines X", resumen="")).estado == EstadoCelda.PENDIENTE


def test_sin_resumen_lo_que_solo_el_pdf_sabe_queda_pendiente(motor: MotorDeDetectores) -> None:
    c = cand(resumen="")
    for col in ("Validez CFA", "# Ítems", "Ejemplo ítem felicidad", "Inclusion criteria"):
        assert motor.evaluar(col, c).estado == EstadoCelda.PENDIENTE
        assert motor.evaluar(col, c).estado != EstadoCelda.AUSENTE  # nunca «ausente» sin el texto completo


# ---- cobertura y puntaje --------------------------------------------------------------------------------------------------
def test_cobertura_ponderada_y_maximo_posible(motor: MotorDeDetectores) -> None:
    p = perfil(("Muestra", Prioridad.IMPRESCINDIBLE), ("Pais", Prioridad.IMPORTANTE),
               ("Beta Fel 1- JP", Prioridad.DESEABLE))
    ev = evaluar(motor, cand(resumen="We surveyed 300 employees."), p)
    assert (ev.peso_total, ev.peso_cubierto, ev.peso_pendiente) == (9, 8, 1)
    assert ev.puntaje == pytest.approx(8 / 9) and ev.maximo == pytest.approx(1.0)
    assert ev.etiqueta == Etiqueta.PROBABLE  # la única imprescindible tiene indicio
    assert [c.estado for c in ev.celdas] == [EstadoCelda.INDICIO, EstadoCelda.METADATO, EstadoCelda.PENDIENTE]


def test_lo_pendiente_no_castiga_pero_se_nota(motor: MotorDeDetectores) -> None:
    p = perfil(("Beta Fel 1- JP", Prioridad.IMPRESCINDIBLE), ("Fiabilidad Alfa - Omega (felicidad)", Prioridad.IMPORTANTE))
    ev = evaluar(motor, cand(resumen=""), p)
    assert ev.puntaje == 0 and ev.maximo == 1 and ev.etiqueta == Etiqueta.DUDOSO


def test_imprescindible_ausente_es_incompleto(motor: MotorDeDetectores) -> None:
    ev = evaluar(motor, cand(autores=()), perfil(("Author", Prioridad.IMPRESCINDIBLE), ("Año", Prioridad.DESEABLE)))
    assert ev.etiqueta == Etiqueta.INCOMPLETO and ev.hay_imprescindible_perdida()


def test_las_columnas_internas_no_cuentan(motor: MotorDeDetectores) -> None:
    ev = evaluar(motor, cand(), perfil(("Documento", Prioridad.IMPRESCINDIBLE), ("Año", Prioridad.IMPORTANTE)))
    assert ev.peso_total == 3 and ev.celdas[0].estado == EstadoCelda.NO_APLICA


def test_sin_imprescindibles_probable_es_la_mitad_del_peso(motor: MotorDeDetectores) -> None:
    p = perfil(("Año", Prioridad.IMPORTANTE), ("Beta Fel 1- JP", Prioridad.IMPORTANTE))
    assert evaluar(motor, cand(), p).etiqueta == Etiqueta.PROBABLE  # 3 de 6
    p2 = perfil(("Año", Prioridad.DESEABLE), ("Beta Fel 1- JP", Prioridad.IMPORTANTE), ("Muestra", Prioridad.IMPORTANTE))
    assert evaluar(motor, cand(), p2).etiqueta == Etiqueta.DUDOSO


def test_revisiones_y_cualitativos_no_aplican() -> None:
    assert no_aplica(cand(titulo="Happiness and performance: a systematic review"))
    assert no_aplica(cand(titulo="A meta-analysis of happiness and job performance"))
    assert no_aplica(cand(tipo="review"))
    assert no_aplica(cand(resumen="This qualitative study used semi-structured interviews."))
    assert no_aplica(cand(resumen="We used semi-structured interviews and also report r = .30 and regression.")) is None
    assert no_aplica(cand(resumen="Participants rated happiness; earlier reviews exist.")) is None


def test_exigir_y_orden(motor: MotorDeDetectores) -> None:
    p = perfil(("Muestra", Prioridad.IMPRESCINDIBLE), ("Año", Prioridad.DESEABLE))
    buena = cand(titulo="Buena", resumen="A sample of 300 employees.", anio=2021)
    media = cand(titulo="Media", resumen="Sin cifras.", anio=2023)
    revision = cand(titulo="A systematic review of happiness", resumen="A sample of 300 employees.", anio=2024)
    pares = [(c, evaluar(motor, c, p)) for c in (media, revision, buena)]
    assert [c.titulo for c, _ in ordenar_por_puntaje(pares)] == ["Buena", "Media", "A systematic review of happiness"]
    por_titulo = {c.titulo: ev for c, ev in pares}
    assert pasa_exigencia(por_titulo["Media"], Exigir.SIN_AUSENTES) and not pasa_exigencia(por_titulo["Media"], Exigir.CONFIRMADAS)
    assert pasa_exigencia(por_titulo["Buena"], Exigir.CONFIRMADAS)
    assert not pasa_exigencia(por_titulo["A systematic review of happiness"], Exigir.SIN_AUSENTES)


def test_el_perfil_valida_sus_columnas() -> None:
    from app.compartido.dominio import ErrorDeDominio
    with pytest.raises(ErrorDeDominio):
        perfil(("Año", Prioridad.DESEABLE), ("Año", Prioridad.IMPORTANTE))
    with pytest.raises(ErrorDeDominio):
        PerfilDeColumnas(proyecto_id=PID, nombre="  ", columnas=(ColumnaElegida("Año", Prioridad.DESEABLE),))
    with pytest.raises(ErrorDeDominio):
        PerfilDeColumnas(proyecto_id=PID, nombre="vacío", columnas=())


# ---- con respuestas reales grabadas -----------------------------------------------------------------------------------------
def test_evalua_lo_grabado_de_openalex(motor: MotorDeDetectores) -> None:
    import httpx

    from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
    from app.contextos.descubrimiento.dominio.busqueda import consulta_inicial
    datos = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "descubrimiento" / "openalex.json")
                       .read_text(encoding="utf-8"))
    cliente = ClienteCortes(transporte=httpx.MockTransport(lambda r: httpx.Response(200, json=datos)), pausa_min_s=0)
    from datetime import date
    registros = list(OpenAlex(cliente).buscar(consulta_inicial(), 3, date(2026, 11, 25)))
    p = perfil_inicial(PID, {c.clave for c in PERFIL_INICIAL})
    for r in registros:
        ev = evaluar(motor, Candidato.desde(PID, r), p)
        assert len(ev.celdas) == len(p.columnas) and 0 <= ev.puntaje <= ev.maximo <= 1
        assert next(c for c in ev.celdas if c.columna == "Pais").estado in (EstadoCelda.METADATO, EstadoCelda.PENDIENTE)


# ---- exportar -------------------------------------------------------------------------------------------------------------
def test_csv_y_ris(motor: MotorDeDetectores) -> None:
    c = cand(resumen="A sample of 300 employees.", palabras_clave=("happiness", "performance"))
    p = perfil(("Muestra", Prioridad.IMPRESCINDIBLE), ("Beta Fel 1- JP", Prioridad.DESEABLE))
    csv_ = a_csv([(c, evaluar(motor, c, p))], ["Muestra", "Beta Fel 1- JP"])
    assert csv_.startswith("﻿Título,") and "Muestra [estado]" in csv_ and "300,INDICIO" in csv_
    assert "Beta Fel 1- JP [estado],".replace(",", "") in csv_ and "PENDIENTE" in csv_
    ris = a_ris([c])
    assert ris.startswith("TY  - JOUR") and "AU  - Ana Pérez" in ris and "KW  - happiness" in ris and ris.rstrip().endswith("ER  -")
    assert a_ris([cand(es_preprint=True)]).startswith("TY  - UNPB")

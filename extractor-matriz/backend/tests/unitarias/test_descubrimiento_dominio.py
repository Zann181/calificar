"""Descubrimiento · dominio: cadena por conceptos, identidad de los trabajos y decisiones sobre candidatos."""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from app.compartido.dominio import ErrorDeDominio
from app.contextos.descubrimiento.dominio.busqueda import (
    Busqueda,
    Concepto,
    ConsultaDeBusqueda,
    EstadoBusqueda,
    EstadoDeFuente,
    Filtros,
    consulta_inicial,
    plano,
)
from app.contextos.descubrimiento.dominio.candidato import (
    Autor,
    Candidato,
    EstadoCandidato,
    RegistroBibliografico,
    clave_de,
    mismo_trabajo,
    normalizar_doi,
)
from app.contextos.descubrimiento.dominio.sitios import SitioConCredenciales
from tests.conftest import RECURSOS

PID = uuid.uuid4()


def registro(**cambios: object) -> RegistroBibliografico:
    base: dict[str, object] = dict(fuente="openalex", id_externo="x", posicion=1, titulo="Happiness and job performance",
                                   doi="https://doi.org/10.1000/ABC.1", anio=2021,
                                   autores=(Autor("Ana Pérez", "Pérez", ("CO",)),))
    base.update(cambios)
    return RegistroBibliografico(**base)  # type: ignore[arg-type]


# ---- la cadena -------------------------------------------------------------------------------------------------
def test_cadena_booleana_une_terminos_con_or_y_conceptos_con_and() -> None:
    q = ConsultaDeBusqueda((Concepto("a", ("happiness", "subjective well-being")), Concepto("b", ("employee*",))))
    assert q.booleana() == '(happiness OR "subjective well-being") AND (employee*)'
    assert q.booleana(comodines=False) == '(happiness OR "subjective well-being") AND (employee)'


def test_los_conceptos_opcionales_no_entran_en_la_cadena() -> None:
    q = ConsultaDeBusqueda((Concepto("a", ("x",)), Concepto("b", ("y",), obligatorio=False)))
    assert q.booleana() == "(x)"


def test_una_coma_dentro_de_un_termino_no_rompe_el_filtro_de_openalex() -> None:
    assert "," not in ConsultaDeBusqueda((Concepto("a", ("a,b",)),)).booleana()


def test_coincide_ignora_tildes_mayusculas_y_respeta_palabras() -> None:
    q = ConsultaDeBusqueda((Concepto("f", ("bienestar psicológico",)), Concepto("t", ("trabajador*",))))
    assert q.coincide("El BIENESTAR psicologico de los trabajadores")
    assert not q.coincide("El bienestar psicológico de los estudiantes")
    solo = ConsultaDeBusqueda((Concepto("t", ("work",)),))
    assert not solo.coincide("a network of artworks")  # «work» no es parte de «network»


def test_cadena_inicial_es_la_que_fijo_el_responsable() -> None:
    q = consulta_inicial()
    assert q.filtros.desde == 2020 and q.filtros.hasta is None
    assert q.filtros.idiomas == ("en", "es", "pt") and q.filtros.incluir_preprints
    assert [c.nombre for c in q.obligatorios] == ["Felicidad", "Desempeño", "Contexto laboral"]
    opcional = next(c for c in q.conceptos if not c.obligatorio)
    assert set(opcional.terminos) == {"job satisfaction", "work engagement"}
    assert "felicidad" in q.booleana() and '"job performance"' in q.booleana()


def test_hasta_la_fecha_es_hoy_y_no_un_ano_fijo() -> None:
    assert Filtros().hasta_efectivo(date(2027, 3, 1)) == 2027
    assert Filtros(hasta=2024).hasta_efectivo(date(2027, 3, 1)) == 2024


def test_validaciones_de_la_consulta() -> None:
    with pytest.raises(ErrorDeDominio):
        Concepto("vacío", ("  ",))
    with pytest.raises(ErrorDeDominio):
        ConsultaDeBusqueda((Concepto("a", ("x",), obligatorio=False),))
    with pytest.raises(ErrorDeDominio):
        ConsultaDeBusqueda((Concepto("a", ("x",)),), Filtros(desde=2022, hasta=2020))


def test_la_consulta_va_y_viene_a_dict() -> None:
    q = consulta_inicial()
    assert ConsultaDeBusqueda.desde_dict(json.loads(json.dumps(q.a_dict()))) == q


def test_plano_quita_tildes() -> None:
    assert plano("  Eudaimonía   Psicológica ") == "eudaimonia psicologica"


# ---- identidad de un trabajo -----------------------------------------------------------------------------------
@pytest.mark.parametrize("crudo", ["https://doi.org/10.1000/ABC.1", "http://dx.doi.org/10.1000/abc.1",
                                   "doi:10.1000/abc.1", " 10.1000/ABC.1. "])
def test_doi_se_normaliza_igual(crudo: str) -> None:
    assert normalizar_doi(crudo) == "10.1000/abc.1"


@pytest.mark.parametrize("crudo", [None, "", "no es un doi", "https://example.com/10.1000"])
def test_lo_que_no_es_doi_da_none(crudo: str | None) -> None:
    assert normalizar_doi(crudo) is None


def test_clave_usa_doi_y_sin_doi_titulo_anio_apellido() -> None:
    assert clave_de("10.1000/X", "T", 2020, "A") == "doi:10.1000/x"
    assert clave_de(None, "Happiness, and Job!", 2020, "Pérez") == clave_de(None, "happiness and job", 2020, "perez")


def test_mismo_trabajo_tolera_pequenas_diferencias_y_un_ano() -> None:
    assert mismo_trabajo("Happiness and job performance: a study", 2021, "Happiness and Job Performance - A Study", 2022)
    assert not mismo_trabajo("Happiness and job performance", 2020, "Happiness and job performance", 2023)
    assert not mismo_trabajo("Happiness and job performance", 2021, "Burnout and turnover intention", 2021)


# ---- candidato -------------------------------------------------------------------------------------------------
def test_candidato_absorbe_lo_que_otra_fuente_sabe_sin_pisar() -> None:
    c = Candidato.desde(PID, registro(doi=None, resumen="corto", url_oa=None))
    assert c.clave.startswith("tit:")
    cambio = c.absorber(registro(fuente="crossref", doi="10.1000/abc.1", resumen="un resumen más largo", url_oa="http://oa"))
    assert cambio and c.doi == "10.1000/abc.1" and c.clave == "doi:10.1000/abc.1"
    assert c.resumen == "un resumen más largo" and c.url_oa == "http://oa" and c.fuentes == ["openalex", "crossref"]
    assert not c.absorber(registro(fuente="crossref", doi="10.1000/abc.1", resumen="x"))  # nada nuevo


def test_un_preprint_deja_de_serlo_si_otra_fuente_lo_conoce_publicado() -> None:
    c = Candidato.desde(PID, registro(es_preprint=True, tipo="preprint"))
    c.absorber(registro(fuente="europepmc", es_preprint=False))
    assert not c.es_preprint


def test_paises_de_los_autores_sin_repetir() -> None:
    c = Candidato.desde(PID, registro(autores=(Autor("A B", "B", ("CO", "ES")), Autor("C D", "D", ("CO",)))))
    assert c.paises == ["CO", "ES"]


def test_decisiones_y_sus_reglas() -> None:
    c = Candidato.desde(PID, registro())
    with pytest.raises(ErrorDeDominio):
        c.descartar("   ")
    c.priorizar()
    c.descartar("No mide desempeño")
    assert c.estado == EstadoCandidato.DESCARTADO and c.motivo == "No mide desempeño"
    with pytest.raises(ErrorDeDominio):
        c.priorizar()  # hay que reactivar primero
    c.reactivar()
    assert c.estado == EstadoCandidato.NUEVO and c.motivo is None
    c.marcar_importado(uuid.uuid4())
    with pytest.raises(ErrorDeDominio):
        c.descartar("tarde")


# ---- búsqueda --------------------------------------------------------------------------------------------------
def test_busqueda_termina_con_errores_si_alguna_fuente_fallo() -> None:
    from app.compartido.dominio import ahora
    b = Busqueda.crear(proyecto_id=PID, nombre="", consulta=consulta_inicial(), fuentes=("a", "b"))
    assert b.nombre == "Búsqueda sin nombre" and set(b.progreso) == {"a", "b"}
    b.progreso["a"].estado = EstadoDeFuente.LISTA
    b.progreso["b"].errores = 1
    b.terminar(cuando=ahora())
    assert b.estado == EstadoBusqueda.TERMINADA_CON_ERRORES and b.errores == 1


def test_busqueda_exige_fuentes() -> None:
    with pytest.raises(ErrorDeDominio):
        Busqueda.crear(proyecto_id=PID, nombre="x", consulta=consulta_inicial(), fuentes=())


# ---- sitios con credenciales -----------------------------------------------------------------------------------
def _sitios() -> list[SitioConCredenciales]:
    datos = json.loads((RECURSOS / "sitios_con_credenciales.json").read_text(encoding="utf-8"))
    return [SitioConCredenciales.desde_dict(s) for s in datos["sitios"]]


def test_la_unal_es_el_primer_sitio_y_la_lista_esta_abierta() -> None:
    sitios = _sitios()
    unal = next(s for s in sitios if s.id == "unal")
    assert unal.es_de_este_sitio("scopus.unalproxy.elogim.com") and unal.es_de_este_sitio("unalproxy.elogim.com")
    assert not unal.es_de_este_sitio("evilunalproxy.elogim.com.otro.com")
    # el presupuesto propio queda por debajo del límite publicado por el proxy (250 MB en 15 min)
    assert unal.limite.bytes_por_ventana < 250_000_000 and unal.limite.ventana_s == 900 and unal.limite.pausa_min_s >= 8


def test_el_catalogo_no_tiene_donde_guardar_credenciales() -> None:
    """Las credenciales las escribe siempre el usuario (ADR 0011): ni el esquema ni el archivo tienen campos para ellas."""
    permitidos = {"id", "nombre", "portal_url", "hosts", "acceso", "limite", "bases", "notas"}
    for s in json.loads((RECURSOS / "sitios_con_credenciales.json").read_text(encoding="utf-8"))["sitios"]:
        assert set(s) <= permitidos
    assert not {"usuario", "password", "contrasena", "contraseña", "clave", "token", "cookie"} & set(
        SitioConCredenciales.__dataclass_fields__)


def test_un_sitio_nuevo_se_agrega_solo_con_datos() -> None:
    nuevo = SitioConCredenciales.desde_dict({
        "id": "otro", "nombre": "Otra biblioteca", "hosts": ["Proxy.Otra.EDU"], "acceso": ["usuario_y_clave"],
        "limite": {"bytes_por_ventana": 50_000_000, "ventana_s": 600, "pausa_min_s": 10}})
    assert nuevo.es_de_este_sitio("bases.proxy.otra.edu")
    with pytest.raises(ErrorDeDominio):
        SitioConCredenciales.desde_dict({"id": "x", "nombre": "x", "hosts": ["x.y"], "acceso": ["magia"],
                                         "limite": {"bytes_por_ventana": 1, "ventana_s": 1, "pausa_min_s": 0}})

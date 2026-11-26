"""Descubrimiento con adaptadores SQL reales (SQLite, migración 0008) y la API: buscar, desduplicar, marcar errores, decidir."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.contextos.descubrimiento.dominio.busqueda import ConsultaDeBusqueda
from app.contextos.descubrimiento.dominio.candidato import Autor, RegistroBibliografico
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.main import crear_app
from tests.conftest import FIXTURES, MATRIZ


class FuenteFalsa:
    """Una fuente con lo que se le dé; `falla_en` simula que se cae a mitad de camino."""

    sitio_id: str | None = None

    def __init__(self, nombre: str, registros: list[RegistroBibliografico], falla_en: int | None = None) -> None:
        self.nombre, self.etiqueta = nombre, nombre.capitalize()
        self._registros, self._falla_en = registros, falla_en

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]:
        for i, r in enumerate(self._registros):
            if self._falla_en is not None and i == self._falla_en:
                raise ErrorDeFuente(self.nombre, "límite de uso de la API (HTTP 429)", estado_http=429)
            yield r


def reg(fuente: str, titulo: str, doi: str | None, anio: int = 2022, **kw: object) -> RegistroBibliografico:
    return RegistroBibliografico(fuente=fuente, id_externo=doi or titulo, posicion=1, titulo=titulo, doi=doi, anio=anio,
                                 autores=(Autor("Ana Pérez", "Pérez", ("CO",)),), **kw)  # type: ignore[arg-type]


A = reg("a", "Happiness and job performance in hospital staff", "10.1000/uno", resumen="breve")
A_EN_B = reg("b", "Happiness and Job Performance in Hospital Staff", "https://doi.org/10.1000/UNO",
             resumen="un resumen bastante más largo", url_oa="http://oa/uno.pdf")
B_SIN_DOI = reg("b", "Happiness and job performance in hospital staff.", None)
OTRO = reg("b", "Subjective well-being and task performance among teachers", "10.1000/dos")
VIEJO = reg("a", "Old study of happiness", "10.1000/viejo", anio=2005)


@pytest.fixture
def ctx(fabrica, ajustes: Settings) -> Iterator[Contenedor]:  # type: ignore[no-untyped-def]
    fuentes = {"a": FuenteFalsa("a", [A, VIEJO]), "b": FuenteFalsa("b", [A_EN_B, OTRO, B_SIN_DOI])}
    yield construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                    fuentes_de_busqueda=fuentes, lanzar_busqueda=lanzar_aqui)


@pytest.fixture
def pid(ctx: Contenedor, libro_json: dict) -> uuid.UUID:  # type: ignore[type-arg]
    from tests.integracion.conftest import nuevo_proyecto
    p = nuevo_proyecto(ctx, "Felicidad y desempeño")
    ctx.normas.publicar.ejecutar(p, libro_json)
    return p


def buscar(ctx: Contenedor, pid: uuid.UUID, fuentes: tuple[str, ...] = ("a", "b")):  # type: ignore[no-untyped-def]
    d = ctx.descubrimiento
    b = d.buscar.iniciar(pid, "prueba", d.consultas.consulta_inicial(), fuentes)
    return d.consultas.busqueda(pid, b.id)


def test_busca_en_varias_fuentes_y_desduplica_por_doi_y_por_titulo(ctx: Contenedor, pid: uuid.UUID) -> None:
    b = buscar(ctx, pid)
    assert b.estado.value == "TERMINADA" and b.errores == 0
    lista = ctx.descubrimiento.consultas.candidatos(pid)
    titulos = sorted(c.titulo for c in lista.candidatos)
    # A (fuente a), A_EN_B (mismo DOI en otra grafía) y B_SIN_DOI (mismo título, sin DOI) son un solo trabajo;
    # VIEJO (2005) queda fuera del filtro 2020–hoy.
    assert len(titulos) == 2 and lista.total == 2
    uno = next(c for c in lista.candidatos if c.doi == "10.1000/uno")
    assert uno.fuentes == ["a", "b"] and uno.resumen == "un resumen bastante más largo" and uno.url_oa == "http://oa/uno.pdf"
    assert b.progreso["a"].encontrados == 1 and b.progreso["b"].encontrados == 3 and b.total_unicos == 2


def test_repetir_la_busqueda_no_duplica_candidatos(ctx: Contenedor, pid: uuid.UUID) -> None:
    buscar(ctx, pid)
    segunda = buscar(ctx, pid)
    assert ctx.descubrimiento.consultas.candidatos(pid).total == 2
    assert segunda.progreso["a"].nuevos == 0 and segunda.progreso["b"].nuevos == 0
    assert len(ctx.descubrimiento.consultas.busquedas(pid)) == 2  # cada búsqueda queda en el historial


def test_una_fuente_que_falla_se_marca_como_error_y_las_demas_siguen(ctx: Contenedor, pid: uuid.UUID,
                                                                    caplog: pytest.LogCaptureFixture) -> None:
    ctx.descubrimiento.buscar._fuentes = {  # type: ignore[assignment]
        "a": FuenteFalsa("a", [A, OTRO], falla_en=1), "b": FuenteFalsa("b", [OTRO])}
    with caplog.at_level(logging.INFO, logger="descubrimiento"):
        b = buscar(ctx, pid)
    assert b.estado.value == "TERMINADA_CON_ERRORES" and b.errores == 1
    assert b.progreso["a"].estado.value == "ERROR" and "429" in (b.progreso["a"].ultimo_error or "")
    assert b.progreso["a"].encontrados == 1 and b.progreso["b"].estado.value == "LISTA"  # lo hallado antes del fallo se conserva
    errores = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "descubrimiento"]
    assert errores and any("incompleta" in r.getMessage() for r in errores)


def test_una_excepcion_inesperada_tampoco_tumba_la_busqueda(ctx: Contenedor, pid: uuid.UUID) -> None:
    class Rota(FuenteFalsa):
        def buscar(self, consulta, limite, hoy):  # type: ignore[no-untyped-def]
            raise RuntimeError("el sitio cambió")
            yield  # pragma: no cover

    ctx.descubrimiento.buscar._fuentes = {"a": Rota("a", []), "b": FuenteFalsa("b", [OTRO])}  # type: ignore[assignment]
    b = buscar(ctx, pid)
    assert b.progreso["a"].estado.value == "ERROR" and "RuntimeError" in (b.progreso["a"].ultimo_error or "")
    assert ctx.descubrimiento.consultas.candidatos(pid).total == 1


def test_fuente_desconocida_se_rechaza(ctx: Contenedor, pid: uuid.UUID) -> None:
    from app.compartido.dominio import ErrorDeDominio
    d = ctx.descubrimiento
    with pytest.raises(ErrorDeDominio, match="Fuente desconocida"):
        d.buscar.iniciar(pid, "x", d.consultas.consulta_inicial(), ("no_existe",))


def test_marca_los_que_ya_estan_en_la_matriz(ctx: Contenedor, pid: uuid.UUID) -> None:
    ctx.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    en_matriz = ctx.descubrimiento.buscar._titulos.titulos(pid)
    assert len(en_matriz) >= 40  # los ~47 documentos de la matriz
    titulo_real = en_matriz[0]
    ctx.descubrimiento.buscar._fuentes = {  # type: ignore[assignment]
        "a": FuenteFalsa("a", [reg("a", titulo_real.upper(), None, anio=2022), OTRO])}
    buscar(ctx, pid, ("a",))
    lista = ctx.descubrimiento.consultas.candidatos(pid)
    marcados = {c.titulo: c.en_matriz for c in lista.candidatos}
    assert marcados[titulo_real.upper()] is True and marcados[OTRO.titulo] is False
    assert [c.titulo for c in ctx.descubrimiento.consultas.candidatos(pid, en_matriz=False).candidatos] == [OTRO.titulo]
    assert lista.contadores["EN_MATRIZ"] == 1


def test_priorizar_descartar_con_motivo_y_reactivar(ctx: Contenedor, pid: uuid.UUID) -> None:
    buscar(ctx, pid)
    ids = [c.id for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos]
    d = ctx.descubrimiento
    r = d.decidir.ejecutar(pid, ids[:1], "priorizar")
    assert [c.estado.value for c in r.cambiados] == ["PRIORIZADO"]
    r = d.decidir.ejecutar(pid, ids, "descartar", "No mide desempeño")
    assert len(r.cambiados) == 2 and not r.rechazados
    assert d.consultas.candidatos(pid).contadores["DESCARTADO"] == 2
    r = d.decidir.ejecutar(pid, ids, "priorizar")  # un descartado debe reactivarse antes
    assert not r.cambiados and len(r.rechazados) == 2
    r = d.decidir.ejecutar(pid, ids + [uuid.uuid4()], "reactivar")
    assert len(r.cambiados) == 2 and len(r.rechazados) == 1


def test_los_candidatos_son_de_su_proyecto(ctx: Contenedor, pid: uuid.UUID) -> None:
    from tests.integracion.conftest import nuevo_proyecto
    buscar(ctx, pid)
    otro = nuevo_proyecto(ctx, "Otro proyecto")
    assert ctx.descubrimiento.consultas.candidatos(otro).total == 0
    ids = [c.id for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos]
    assert ctx.descubrimiento.decidir.ejecutar(otro, ids, "priorizar").cambiados == []


# ---- API -------------------------------------------------------------------------------------------------------
@pytest.fixture
def cliente(ctx: Contenedor, ajustes: Settings, pid: uuid.UUID) -> Iterator[TestClient]:
    with TestClient(crear_app(ajustes, ctx)) as c:
        yield c


def test_api_configuracion_trae_la_cadena_inicial_las_fuentes_y_los_sitios(cliente: TestClient, pid: uuid.UUID) -> None:
    r = cliente.get(f"/api/v1/proyectos/{pid}/busqueda/configuracion").json()
    assert r["consulta_inicial"]["filtros"]["desde"] == 2020
    assert {f["id"] for f in r["fuentes"]} == {"a", "b"} and all(f["utilizable"] for f in r["fuentes"])
    unal = next(s for s in r["sitios"] if s["id"] == "unal")
    assert unal["sesion"] == "NO_CONECTADA" and unal["limite"]["pausa_min_s"] >= 8
    assert "usuario" not in unal and "password" not in unal


def test_api_ciclo_completo(cliente: TestClient, pid: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{pid}"
    r = cliente.post(f"{base}/busquedas", json={"nombre": "mi búsqueda", "fuentes": ["a", "b"]})
    assert r.status_code == 202, r.text
    b = r.json()
    assert b["estado"] == "TERMINADA" and b["total_unicos"] == 2 and b["errores"] == 0
    assert "happiness" in b["cadena"] and b["consulta"]["filtros"]["idiomas"] == ["en", "es", "pt"]
    assert cliente.get(f"{base}/busquedas/{b['id']}").json()["nombre"] == "mi búsqueda"
    assert len(cliente.get(f"{base}/busquedas").json()["busquedas"]) == 1

    lista = cliente.get(f"{base}/candidatos", params={"busqueda_id": b["id"], "q": "teachers"}).json()
    assert lista["total"] == 1 and lista["candidatos"][0]["doi"] == "10.1000/dos"
    ids = [c["id"] for c in cliente.get(f"{base}/candidatos").json()["candidatos"]]
    assert cliente.post(f"{base}/candidatos/decision", json={"ids": ids, "accion": "descartar"}).status_code == 409  # sin motivo
    r = cliente.post(f"{base}/candidatos/decision", json={"ids": ids, "accion": "descartar", "motivo": "fuera de alcance"})
    assert r.status_code == 200 and len(r.json()["cambiados"]) == 2
    assert cliente.get(f"{base}/candidatos", params={"estado": "DESCARTADO"}).json()["total"] == 2


def test_api_valida_la_entrada(cliente: TestClient, pid: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{pid}"
    assert cliente.post(f"{base}/busquedas", json={"fuentes": ["no_existe"]}).status_code == 409
    assert cliente.post(f"{base}/busquedas", json={"filtros": {"desde": 2024, "hasta": 2020}}).status_code == 409
    assert cliente.post(f"{base}/busquedas", json={"filtros": {"idiomas": ["fr"]}}).status_code == 422
    assert cliente.get(f"{base}/busquedas/{uuid.uuid4()}").status_code == 404
    assert cliente.get(f"/api/v1/proyectos/{uuid.uuid4()}/candidatos").status_code == 404


def test_api_cancelar_una_busqueda_que_existe(cliente: TestClient, pid: uuid.UUID) -> None:
    base = f"/api/v1/proyectos/{pid}"
    b = cliente.post(f"{base}/busquedas", json={"fuentes": ["a"]}).json()
    assert cliente.post(f"{base}/busquedas/{b['id']}/cancelar").json() == {"cancelando": True}
    assert cliente.post(f"{base}/busquedas/{uuid.uuid4()}/cancelar").status_code == 404


def test_capacidades_ofrecen_la_busqueda(cliente: TestClient) -> None:
    assert cliente.get("/api/v1/capacidades").json()["busqueda"] is True


def test_en_la_nube_la_pestana_existe_pero_pide_sesion(fabrica, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """ADR 0012. El detalle (paridad, 405, réplica, buscar en la web) está en `test_descubrimiento_nube.py`."""
    ajustes = Settings(_env_file=None, modo="nube", despachador_en_servidor=False, lectores_permitidos="l@ejemplo.co",
                       google_client_id="id", google_client_secret="s", secreto_sesion="x" * 40,
                       sync_token_hash="h", url_publica="https://nube.ejemplo.co")
    c = construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"))
    with TestClient(crear_app(ajustes, c)) as cli:
        capacidades = cli.get("/api/v1/capacidades").json()
        assert capacidades["busqueda"] is True and capacidades["puede_buscar"] is True
        assert capacidades["escritura"] is False
        assert cli.post(f"/api/v1/proyectos/{uuid.uuid4()}/busquedas", json={}).status_code == 401
        assert cli.get(f"/api/v1/proyectos/{uuid.uuid4()}/candidatos").status_code == 401


# ---- «sin IA» y «sin credenciales» ----------------------------------------------------------------------------------
def test_descubrimiento_no_usa_modelos_ni_subprocesos() -> None:
    """ADR 0011: la pestaña es determinista. Además de import-linter, un vistazo al texto de los módulos."""
    raiz = Path(__file__).resolve().parents[2] / "app" / "contextos" / "descubrimiento"
    prohibido = re.compile(r"\b(anthropic|claude|subprocess|ModeloDeLenguaje|modelo_ligero|modelo_especializado)\b", re.I)
    ofensores = []
    for py in raiz.rglob("*.py"):
        for n, linea in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if prohibido.search(linea) and not linea.lstrip().startswith(("#", '"""', "-")) and "sin IA" not in linea:
                ofensores.append(f"{py.name}:{n}: {linea.strip()[:80]}")
    assert not ofensores, "\n".join(ofensores)

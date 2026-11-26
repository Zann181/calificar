"""Descubrimiento · Fase 4 con adaptadores reales: una fuente de lectura frágil se apaga sola y se reactiva; las no disponibles se explican."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.adaptadores.salud_fuentes import SaludDeFuentes
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.contextos.descubrimiento.dominio.errores import ErrorDeEstructura, ErrorDeFuente
from app.main import crear_app
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_descubrimiento import FuenteFalsa, PdfsQueResponden, buscar, reg


class Fragil(FuenteFalsa):
    """Una fuente que se lee sin API documentada: puede romperse por estructura o por red."""

    autodesactivable = True

    def __init__(self, nombre: str) -> None:
        super().__init__(nombre, [reg(nombre, "Felicidad y desempeño en docentes", "10.1000/fr", anio=2022)])
        self.modo = "bien"

    def buscar(self, consulta, limite, hoy):  # type: ignore[no-untyped-def]
        if self.modo == "estructura":
            raise ErrorDeEstructura(self.nombre, "la respuesta ya no trae «resultados»: el sitio cambió")
        if self.modo == "red":
            raise ErrorDeFuente(self.nombre, "límite de uso de la API (HTTP 429)", estado_http=429)
        yield from super().buscar(consulta, limite, hoy)


@pytest.fixture
def fragil() -> Fragil:
    return Fragil("fragil")


@pytest.fixture
def ctx(fabrica, fragil: Fragil) -> Contenedor:  # type: ignore[no-untyped-def]
    logging.getLogger("descubrimiento").disabled = False
    return construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica,
                     almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda={"abierta": FuenteFalsa("abierta", []), "fragil": fragil},
                     lanzar_busqueda=lanzar_aqui, comprobador_pdf=PdfsQueResponden(), salud_de_fuentes=SaludDeFuentes())


@pytest.fixture
def pid(ctx: Contenedor, libro_json: dict) -> uuid.UUID:  # type: ignore[type-arg]
    p = nuevo_proyecto(ctx, "Felicidad y desempeño")
    ctx.normas.publicar.ejecutar(p, libro_json)
    return p


@pytest.fixture
def cliente(ctx: Contenedor) -> Iterator[TestClient]:
    with TestClient(crear_app(Settings(_env_file=None, despachador_en_servidor=False), ctx)) as c:
        yield c


def test_tres_busquedas_seguidas_con_cambio_de_estructura_la_apagan_y_queda_marcado(
        ctx: Contenedor, pid: uuid.UUID, fragil: Fragil, caplog: pytest.LogCaptureFixture) -> None:
    fragil.modo = "estructura"
    with caplog.at_level(logging.INFO, logger="descubrimiento"):
        for _ in range(3):
            b = buscar(ctx, pid, ("fragil",))
            assert b.progreso["fragil"].estado.value == "ERROR"
        assert any("se desactivó sola" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)
        fragil.modo = "bien"  # el sitio vuelve a responder bien, pero sigue apagada hasta que la persona la reactive
        cuarta = buscar(ctx, pid, ("fragil",))
    p = cuarta.progreso["fragil"]
    assert p.estado.value == "OMITIDA" and "Desactivada" in (p.ultimo_error or "") and p.errores == 1
    fuentes = {f.nombre: f for f in ctx.descubrimiento.consultas.fuentes()}
    assert fuentes["fragil"].desactivada and not fuentes["fragil"].utilizable and fuentes["abierta"].utilizable
    assert ctx.descubrimiento.consultas.candidatos(pid).total == 0  # nada de basura de una fuente rota


def test_un_corte_de_red_no_desactiva_nada_y_un_exito_reinicia_la_cuenta(ctx: Contenedor, pid: uuid.UUID,
                                                                          fragil: Fragil) -> None:
    fragil.modo = "red"
    for _ in range(5):
        assert buscar(ctx, pid, ("fragil",)).progreso["fragil"].estado.value == "ERROR"
    assert ctx.descubrimiento.consultas.fuentes()[1].desactivada is None  # 429 no es «el sitio cambió»
    fragil.modo = "estructura"
    buscar(ctx, pid, ("fragil",))
    buscar(ctx, pid, ("fragil",))
    fragil.modo = "bien"
    assert buscar(ctx, pid, ("fragil",)).progreso["fragil"].estado.value == "LISTA"  # un éxito: la cuenta vuelve a cero
    fragil.modo = "estructura"
    buscar(ctx, pid, ("fragil",))
    buscar(ctx, pid, ("fragil",))
    assert ctx.descubrimiento.consultas.fuentes()[1].desactivada is None  # dos seguidos: todavía no


def test_la_configuracion_muestra_lo_apagado_y_lo_que_no_se_ofrece_y_se_reactiva(
        cliente: TestClient, ctx: Contenedor, pid: uuid.UUID, fragil: Fragil) -> None:
    base = f"/api/v1/proyectos/{pid}/busqueda"
    fragil.modo = "estructura"
    for _ in range(3):
        buscar(ctx, pid, ("fragil",))
    cfg = cliente.get(f"{base}/configuracion").json()
    f = next(x for x in cfg["fuentes"] if x["id"] == "fragil")
    assert f["utilizable"] is False and "fallos seguidos" in f["desactivada"]
    no = {x["id"]: x for x in cfg["no_disponibles"]}
    assert {"scielo", "dialnet"} <= set(no) and "robots.txt" in no["dialnet"]["motivo"] and "robots.txt" in no["scielo"]["motivo"]

    assert cliente.post(f"{base}/fuentes/fragil/reactivar").json() == {"reactivada": True}
    cfg2 = cliente.get(f"{base}/configuracion").json()
    f2 = next(x for x in cfg2["fuentes"] if x["id"] == "fragil")
    assert f2["utilizable"] is True and f2["desactivada"] is None
    assert cliente.post(f"{base}/fuentes/no_existe/reactivar").status_code == 409


def test_redalyc_se_ofrece_como_fuente_abierta_y_fragil(fabrica) -> None:  # type: ignore[no-untyped-def]
    real = construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica, almacen=AlmacenEnMemoria(),
                     conversor=ConversorFijo(FIXTURES / "mineru"), salud_de_fuentes=SaludDeFuentes())
    fuentes = {f.nombre: f for f in real.descubrimiento.consultas.fuentes()}
    assert {"openalex", "europepmc", "crossref", "redalyc"} <= set(fuentes)
    assert fuentes["redalyc"].sitio_id is None and fuentes["redalyc"].utilizable

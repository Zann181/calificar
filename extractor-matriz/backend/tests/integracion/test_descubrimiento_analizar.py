"""Descubrimiento · etapa B con adaptadores reales: analizar el texto completo de un PDF abierto y evaluar con lo hallado."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.compartido.dominio import ErrorDeDominio
from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.main import crear_app
from tests.conftest import FIXTURES, MATRIZ
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_descubrimiento import FuenteFalsa, buscar, reg
from tests.integracion.test_descubrimiento_importar import CON_PDF, FALLA, OTRO_PDF, SIN_COPIA, PdfFalso
from tests.unitarias.test_descubrimiento_texto_completo import PAGINAS


class TextoFalso:
    """Devuelve páginas fijas (o falla): así se prueba sin depender del contenido de un PDF real."""

    def __init__(self, paginas: list[str] | None = None, error: str | None = None) -> None:
        self.paginas_, self.error = paginas, error
        self.leidos = 0

    def paginas(self, datos: bytes) -> list[str]:
        self.leidos += 1
        if self.error:
            raise ErrorDeDominio(self.error)
        return self.paginas_ or []


@pytest.fixture
def descargador() -> PdfFalso:
    return PdfFalso()


@pytest.fixture
def texto() -> TextoFalso:
    return TextoFalso(PAGINAS)


@pytest.fixture
def ctx(fabrica, descargador: PdfFalso, texto: TextoFalso) -> Contenedor:  # type: ignore[no-untyped-def]
    logging.getLogger("descubrimiento").disabled = False
    fuentes = {"a": FuenteFalsa("a", [CON_PDF, OTRO_PDF, SIN_COPIA, FALLA])}
    return construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica,
                     almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda=fuentes, lanzar_busqueda=lanzar_aqui, obtener_pdf=descargador,
                     extraer_texto=texto)


@pytest.fixture
def pid(ctx: Contenedor, libro_json: dict) -> uuid.UUID:  # type: ignore[type-arg]
    p = nuevo_proyecto(ctx, "Felicidad y desempeño")
    ctx.normas.publicar.ejecutar(p, libro_json)
    buscar(ctx, p, ("a",))
    return p


@pytest.fixture
def cliente(ctx: Contenedor) -> Iterator[TestClient]:
    with TestClient(crear_app(Settings(_env_file=None, despachador_en_servidor=False), ctx)) as c:
        yield c


def id_de(ctx: Contenedor, pid: uuid.UUID, doi: str) -> uuid.UUID:
    return next(c.id for c in ctx.descubrimiento.consultas.candidatos(pid).candidatos if c.doi == doi)


def analizar(cliente: TestClient, pid: uuid.UUID, *ids: uuid.UUID) -> dict[str, dict]:  # type: ignore[type-arg]
    r = cliente.post(f"/api/v1/proyectos/{pid}/candidatos/analizar", json={"ids": [str(i) for i in ids]})
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()["resultados"]}


def perfil_de_prueba(cliente: TestClient, pid: uuid.UUID) -> None:
    cols = [{"clave": "Muestra", "prioridad": "IMPRESCINDIBLE"},
            {"clave": "Correlación Feli 1 - JP", "prioridad": "IMPRESCINDIBLE"},
            {"clave": "Software", "prioridad": "DESEABLE"}, {"clave": "Beta Fel 1- JP", "prioridad": "DESEABLE"}]
    cliente.put(f"/api/v1/proyectos/{pid}/busqueda/perfiles", json={"nombre": "P", "columnas": cols, "predeterminado": True})


def evaluacion(cliente: TestClient, pid: uuid.UUID, cid: uuid.UUID) -> dict:  # type: ignore[type-arg]
    lista = cliente.get(f"/api/v1/proyectos/{pid}/candidatos").json()["candidatos"]
    return next(c["evaluacion"] for c in lista if c["id"] == str(cid))


def test_analizar_guarda_indicios_con_pagina_y_cambia_la_evaluacion(cliente: TestClient, ctx: Contenedor,
                                                                    pid: uuid.UUID, descargador: PdfFalso) -> None:
    perfil_de_prueba(cliente, pid)
    cid = id_de(ctx, pid, "10.1000/uno")
    antes = evaluacion(cliente, pid, cid)
    assert antes["etapa"] == "A" and antes["puntaje"] == 0
    r = analizar(cliente, pid, cid)[str(cid)]
    assert r["estado"] == "TEXTO_INSUFICIENTE" or r["estado"] == "ANALIZADO"  # el texto de juguete es corto
    assert r["con_indicio"] >= 5 and descargador.pedidas == ["https://oa.test/kumar.pdf"]
    despues = evaluacion(cliente, pid, cid)
    celdas = {c["columna"]: c for c in despues["celdas"]}
    assert despues["etapa"] == "B" and celdas["Muestra"]["valor"] == "300" and celdas["Muestra"]["origen"] == "p. 2 · método"
    assert celdas["Correlación Feli 1 - JP"]["valor"] == "r = .41" and celdas["Software"]["valor"] == "SPSS, AMOS"
    assert despues["puntaje"] > antes["puntaje"] and despues["etiqueta"] == "PROBABLE"


def test_no_se_guarda_el_texto_ni_el_archivo(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID) -> None:
    analizar(cliente, pid, id_de(ctx, pid, "10.1000/uno"))
    from sqlalchemy import text
    with ctx.fabrica() as s:
        filas = s.execute(text("select celdas, intentadas, origen from descubrimiento_analisis")).all()
    assert len(filas) == 1
    contenido = " ".join(str(c) for c in filas[0])
    assert "the team met every week" not in contenido  # el texto de relleno, que ningún detector usó, no se guarda
    assert len(contenido) < 20_000
    assert not ctx.biblioteca.consultas.listar(pid).articulos  # analizar no importa el artículo


def test_si_el_articulo_ya_esta_importado_se_lee_ese_pdf_y_no_se_baja_otra_vez(
        cliente: TestClient, ctx: Contenedor, pid: uuid.UUID, descargador: PdfFalso, texto: TextoFalso) -> None:
    cid = id_de(ctx, pid, "10.1000/uno")
    cliente.post(f"/api/v1/proyectos/{pid}/candidatos/importar", json={"ids": [str(cid)]})
    assert len(descargador.pedidas) == 1
    r = analizar(cliente, pid, cid)[str(cid)]
    assert "PDF ya importado" in r["mensaje"] and len(descargador.pedidas) == 1 and texto.leidos == 1


def test_sin_copia_error_de_descarga_y_pdf_ilegible(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID,
                                                    texto: TextoFalso, caplog: pytest.LogCaptureFixture) -> None:
    sin, falla, bueno = (id_de(ctx, pid, d) for d in ("10.1000/cuatro", "10.1000/cinco", "10.1000/dos"))
    with caplog.at_level(logging.INFO, logger="descubrimiento"):
        r = analizar(cliente, pid, sin, falla)
        assert r[str(sin)]["estado"] == "SIN_COPIA_ABIERTA" and r[str(falla)]["estado"] == "ERROR"
        assert "403" in r[str(falla)]["mensaje"]
        texto.error = "FileDataError: no es un PDF"
        r2 = analizar(cliente, pid, bueno)[str(bueno)]
    assert r2["estado"] == "ERROR" and "no se pudo leer" in r2["mensaje"]
    assert sum(1 for x in caplog.records if x.levelno == logging.ERROR and "Analizar" in x.getMessage()) >= 2


def test_un_pdf_sin_texto_no_afirma_que_falte_nada(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID,
                                                    texto: TextoFalso) -> None:
    perfil_de_prueba(cliente, pid)
    texto.paginas_ = ["", ""]  # PDF escaneado
    cid = id_de(ctx, pid, "10.1000/uno")
    r = analizar(cliente, pid, cid)[str(cid)]
    assert r["estado"] == "TEXTO_INSUFICIENTE" and "escaneado" in r["mensaje"]
    ev = evaluacion(cliente, pid, cid)
    assert ev["etapa"] == "B" and not any(c["estado"] == "AUSENTE" for c in ev["celdas"])
    assert ev["etiqueta"] != "INCOMPLETO"


def test_limites_y_la_matriz_no_cambia(cliente: TestClient, ctx: Contenedor, pid: uuid.UUID) -> None:
    ctx.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    filas = len(ctx.matriz.consultas.todas(pid))
    base = f"/api/v1/proyectos/{pid}/candidatos/analizar"
    assert cliente.post(base, json={"ids": [str(uuid.uuid4()) for _ in range(11)]}).status_code == 409
    assert cliente.post(base, json={"ids": []}).status_code == 422
    assert cliente.post(base, json={"ids": [str(uuid.uuid4())]}).json()["resultados"][0]["estado"] == "ERROR"
    analizar(cliente, pid, id_de(ctx, pid, "10.1000/uno"))
    assert len(ctx.matriz.consultas.todas(pid)) == filas


def test_el_lector_real_lee_un_pdf_de_verdad_y_rechaza_un_archivo_roto() -> None:
    from app.contextos.descubrimiento.adaptadores.texto_pdf import LectorDeTextoPymupdf
    paginas = LectorDeTextoPymupdf().paginas((FIXTURES / "kumar_2022.pdf").read_bytes())
    assert len(paginas) >= 5 and sum(len(p) for p in paginas) > 10_000
    with pytest.raises(ErrorDeDominio):
        LectorDeTextoPymupdf().paginas(b"%PDF-1.4 esto no es un pdf")


def test_importar_y_analizar_un_pdf_real_de_punta_a_punta(fabrica, ctx: Contenedor,  # type: ignore[no-untyped-def]
                                                          descargador: PdfFalso) -> None:
    from app.contextos.descubrimiento.adaptadores.texto_pdf import LectorDeTextoPymupdf
    real = construir(Settings(_env_file=None, despachador_en_servidor=False), fabrica=fabrica, almacen=AlmacenEnMemoria(),
                     conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda={"a": FuenteFalsa("a", [reg("a", "Is happiness a determinant of job performance",
                                                                   "10.1000/kumar", anio=2022, url_oa="https://oa.test/kumar.pdf")])},
                     lanzar_busqueda=lanzar_aqui, obtener_pdf=descargador, extraer_texto=LectorDeTextoPymupdf())
    p = nuevo_proyecto(real, "Real")
    real.normas.publicar.ejecutar(p, __import__("json").loads((FIXTURES.parent / "Libro_de_codigos_extraccion_v2.json")
                                                              .read_text(encoding="utf-8")))
    buscar(real, p, ("a",))
    cid = real.descubrimiento.consultas.candidatos(p).candidatos[0].id
    r = real.descubrimiento.analizar.ejecutar(p, [cid])[0]
    assert r.estado.value == "ANALIZADO" and r.con_indicio >= 3  # el PDF real tiene texto de sobra

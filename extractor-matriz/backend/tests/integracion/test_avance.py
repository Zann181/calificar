"""Avance de extracciones: endpoint de avance y lanzamiento desde la API (sin llamar al modelo real)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.compartido.dominio import ErrorDeDominio
from app.composicion import Contenedor
from app.contextos.extraccion.aplicacion.casos_de_uso import OpcionesDeExtraccion
from app.contextos.extraccion.aplicacion.ejecutor import (
    CONVIRTIENDO,
    EjecutorDeExtracciones,
    PedidoDeExtraccion,
    Pendiente,
)
from app.contextos.extraccion.dominio.extraccion import Extraccion
from app.contextos.extraccion.puertos import PedidoGuardado
from tests.conftest import FIXTURES
from tests.integracion.test_api import cliente, entrar  # noqa: F401


class EjecutorFalso:
    """Registra los pedidos en lugar de correr la extracción: nada de llamadas al modelo en las pruebas."""

    def __init__(self) -> None:
        self.pedidos: list[PedidoDeExtraccion] = []

    def encolar(self, pedido: PedidoDeExtraccion) -> int:
        self.pedidos.append(pedido)
        return len(self.pedidos) - 1

    def pendientes(self, proyecto_id: uuid.UUID) -> list[Pendiente]:
        return [Pendiente(p.articulo_id, i + 1, "en_cola", 0.0) for i, p in enumerate(self.pedidos[1:])]

    def cerrar(self) -> None:
        pass


def _articulo_listo(c: Contenedor, proyecto: uuid.UUID, nombre: str) -> uuid.UUID:
    r = c.biblioteca.cargar.ejecutar(proyecto, f"{nombre}.pdf", (FIXTURES / f"{nombre}.pdf").read_bytes())
    assert r.articulo_id is not None
    c.biblioteca.convertir.ejecutar(proyecto, r.articulo_id)
    return r.articulo_id


def test_lanzar_encola_y_valida(cliente: TestClient, contenedor: Contenedor, proyecto: uuid.UUID) -> None:  # noqa: F811
    falso = EjecutorFalso()
    contenedor.ejecutor = falso  # type: ignore[assignment]
    listo = _articulo_listo(contenedor, proyecto, "kumar_2022")
    nuevo = contenedor.biblioteca.cargar.ejecutar(proyecto, "x.pdf", b"%PDF-1.4 sin convertir").articulo_id
    assert nuevo is not None
    excluido = contenedor.biblioteca.cargar.ejecutar(proyecto, "y.pdf", b"%PDF-1.4 otro").articulo_id
    assert excluido is not None
    contenedor.biblioteca.excluir.ejecutar(proyecto, excluido, "fuera del alcance")
    entrar(cliente)
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/extracciones", json={"articulos": [
        {"articulo_id": str(listo), "documento": 1, "covidence": 671},
        {"articulo_id": str(nuevo), "documento": 2, "via": "Otros métodos: búsqueda manual"},
        {"articulo_id": str(excluido), "documento": 3},
    ]})
    assert r.status_code == 200, r.text
    a, b, c = r.json()
    assert a["encolado"] and a["posicion"] == 1
    assert b["encolado"], b  # un PDF sin convertir se acepta: el pedido lo convierte primero
    assert not c["encolado"] and "EXCLUIDO" in c["error"]
    assert [p.opciones.documento for p in falso.pedidos] == [1, 2]
    assert cliente.post(f"/api/v1/proyectos/{proyecto}/extracciones",
                        json={"articulos": [{"articulo_id": str(listo), "documento": 0}]}).status_code == 422


def test_sin_covidence_ni_otra_via_no_se_encola(cliente: TestClient, contenedor: Contenedor,  # noqa: F811
                                                proyecto: uuid.UUID) -> None:
    """V06: sin Covidence # la vía no puede ser Covidence; se rechaza antes de pagar al modelo."""
    falso = EjecutorFalso()
    contenedor.ejecutor = falso  # type: ignore[assignment]
    listo = _articulo_listo(contenedor, proyecto, "kumar_2022")
    entrar(cliente)
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/extracciones",
                     json={"articulos": [{"articulo_id": str(listo), "documento": 1}]})
    assert not r.json()[0]["encolado"] and "Covidence #" in r.json()[0]["error"]
    assert falso.pedidos == []


def test_avance_lista_extracciones_en_curso(cliente: TestClient, contenedor: Contenedor, proyecto: uuid.UUID) -> None:  # noqa: F811
    contenedor.ejecutor = EjecutorFalso()  # type: ignore[assignment]
    aid = _articulo_listo(contenedor, proyecto, "singh_2023")
    ext = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=uuid.uuid4(),
                             estudios_reservados=[7])
    ext.avanzar("extrayendo")
    with contenedor.fabrica() as s:
        from app.contextos.extraccion.adaptadores.repositorio_sql import UnidadDeTrabajoExtraccionSql

        with UnidadDeTrabajoExtraccionSql(lambda: s) as u:  # type: ignore[arg-type]
            u.extracciones.agregar(ext)
            u.confirmar()
    entrar(cliente)
    datos: dict[str, Any] = cliente.get(f"/api/v1/proyectos/{proyecto}/extracciones/avance").json()
    (e,) = datos["extracciones"]
    assert e["articulo_id"] == str(aid) and e["estado"] == "EXTRAYENDO"
    assert e["progreso"] == 8 and e["paso"] == "extrayendo" and e["hasta"] == 45 and e["segundos_tipicos"] == 300
    assert not e["fallida"] and not e["inactiva"] and e["terminada_en"] is None


class ExtraerFalso:
    """Sustituye al motor: anota con qué estado encontró el artículo cuando le tocó extraer."""

    def __init__(self, contenedor: Contenedor) -> None:
        self.contenedor = contenedor
        self.vistos: list[str] = []
        self.opciones: list[Any] = []

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, opciones: object) -> Any:
        self.opciones.append(opciones)
        self.vistos.append(self.contenedor.biblioteca.consultas.articulo(proyecto_id, articulo_id).estado.value)
        return type("R", (), {"estado": "COMPLETADA"})()


def test_extraer_un_pdf_sin_convertir_lo_convierte_primero(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    import time

    pdf = (FIXTURES / "kumar_2022.pdf").read_bytes()
    aid = contenedor.biblioteca.cargar.ejecutar(proyecto, "kumar_2022.pdf", pdf).articulo_id
    assert aid is not None
    assert contenedor.biblioteca.consultas.articulo(proyecto, aid).estado.value == "NUEVO"
    falso = ExtraerFalso(contenedor)
    fases: list[str] = []
    preparar = contenedor.ejecutor._preparar  # el de la composición: convierte con el conversor de pruebas
    assert preparar is not None

    def con_registro(pedido: PedidoDeExtraccion, informar: Any) -> None:
        preparar(pedido, lambda f: (fases.append(f), informar(f))[1])

    ejecutor = EjecutorDeExtracciones(falso, 1, con_registro)  # type: ignore[arg-type]
    pedido = PedidoDeExtraccion(proyecto, aid, "kumar_2022.pdf", OpcionesDeExtraccion(documento=1))
    ejecutor.encolar(pedido)
    with pytest.raises(ErrorDeDominio):  # el mismo artículo no entra dos veces
        ejecutor.encolar(pedido)
    for _ in range(100):
        if falso.vistos:
            break
        time.sleep(0.1)
    assert falso.vistos == ["LISTO"]  # ya convertido cuando empezó la extracción
    assert CONVIRTIENDO in fases
    ejecutor.cerrar()


def test_un_error_al_extraer_se_puede_reintentar(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    from app.contextos.biblioteca.dominio.articulo import EstadoArticulo

    aid = _articulo_listo(contenedor, proyecto, "kumar_2022")
    contenedor.biblioteca.extraccion.fallar(proyecto, aid, EstadoArticulo.EXTRAYENDO, "CLI sin sesión")
    assert contenedor.biblioteca.consultas.articulo(proyecto, aid).estado == EstadoArticulo.ERROR
    preparar = contenedor.ejecutor._preparar
    assert preparar is not None
    pedido = PedidoDeExtraccion(proyecto, aid, "kumar_2022.pdf", OpcionesDeExtraccion(documento=1))
    preparar(pedido, lambda fase: None)  # no lo trata como error de conversión: la extracción lo retoma


class ConversorQueFalla:
    def convertir(self, pdf: bytes, nombre: str) -> Any:
        raise RuntimeError("MinerU devolvió 500")


def test_si_la_conversion_falla_se_informa(fabrica: Any, ajustes: Any, libro_json: dict[str, Any]) -> None:
    from app.compartido.dominio import ErrorDeDominio
    from app.composicion import construir
    from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
    from tests.integracion.conftest import nuevo_proyecto

    c = construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorQueFalla())
    pid = nuevo_proyecto(c, "Conversión que falla")
    aid = c.biblioteca.cargar.ejecutar(pid, "k.pdf", (FIXTURES / "kumar_2022.pdf").read_bytes()).articulo_id
    assert aid is not None
    preparar = c.ejecutor._preparar
    assert preparar is not None
    with pytest.raises(ErrorDeDominio, match="conversión falló"):
        preparar(PedidoDeExtraccion(pid, aid, "k.pdf", OpcionesDeExtraccion(documento=1)), lambda fase: None)



def test_al_abrir_se_retoma_lo_que_quedo_pendiente(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    """La cola se guarda en la base: lo encolado o a medias al cerrar se vuelve a lanzar al abrir."""
    import time

    from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
    from app.contextos.extraccion.adaptadores.repositorio_sql import ColaDeExtraccionesSql

    aid = _articulo_listo(contenedor, proyecto, "kumar_2022")
    otro = _articulo_listo(contenedor, proyecto, "singh_2023")
    opciones = OpcionesDeExtraccion(documento=5, estudio_inicial=72, covidence=None, via="Otros métodos: manual")
    # Primera sesión: una extracción a medias (el proceso murió) y otro artículo esperando en cola.
    contenedor.biblioteca.extraccion.iniciar(proyecto, aid)
    libro = contenedor.normas.consultas.libro_activo(proyecto)
    huerfana = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=libro.id,
                                  estudios_reservados=[72])
    with contenedor.extraccion.extraer._udt() as u:
        u.extracciones.agregar(huerfana)
        u.confirmar()
    cola = ColaDeExtraccionesSql(contenedor.fabrica)
    cola.guardar(PedidoGuardado(proyecto, aid, "kumar_2022.pdf", asdict(opciones)))
    cola.guardar(PedidoGuardado(proyecto, otro, "singh_2023.pdf", asdict(OpcionesDeExtraccion(documento=6))))

    # Segunda sesión.
    falso = ExtraerFalso(contenedor)
    falso.cerrar_interrumpidas = contenedor.extraccion.extraer.cerrar_interrumpidas  # type: ignore[attr-defined]
    ejecutor = EjecutorDeExtracciones(falso, 1, None, cola)  # type: ignore[arg-type]
    assert ejecutor.reanudar(30 * 60) == 2
    for _ in range(100):
        if len(falso.vistos) == 2 and not cola.pendientes():
            break
        time.sleep(0.1)
    # La huérfana quedó fallida y el artículo en ERROR, del que la extracción se retoma.
    assert contenedor.extraccion.consultas.obtener(proyecto, huerfana.id).estado.value == "FALLIDA"
    assert falso.vistos == [EstadoArticulo.ERROR.value, EstadoArticulo.LISTO.value]
    assert [o.documento for o in falso.opciones] == [5, 6]
    assert falso.opciones[0] == opciones
    assert cola.pendientes() == []  # terminadas, salen de la cola
    ejecutor.cerrar()


def test_una_extraccion_de_la_cli_en_marcha_no_se_toca(contenedor: Contenedor, proyecto: uuid.UUID) -> None:
    aid = _articulo_listo(contenedor, proyecto, "kumar_2022")
    contenedor.biblioteca.extraccion.iniciar(proyecto, aid)
    libro = contenedor.normas.consultas.libro_activo(proyecto)
    viva = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=libro.id,
                              estudios_reservados=[1])
    with contenedor.extraccion.extraer._udt() as u:
        u.extracciones.agregar(viva)
        u.confirmar()
    assert contenedor.ejecutor.reanudar(30 * 60) == 0
    assert contenedor.extraccion.consultas.obtener(proyecto, viva.id).estado.value == "EXTRAYENDO"
    assert contenedor.extraccion.extraer.cerrar_interrumpidas(set(), 0) == 1  # ya sin actividad: se cierra
    assert contenedor.extraccion.consultas.obtener(proyecto, viva.id).estado.value == "FALLIDA"


def test_extraer_sobre_un_error_reutiliza_los_datos_del_intento_anterior(
        cliente: TestClient, contenedor: Contenedor, proyecto: uuid.UUID) -> None:  # noqa: F811
    falso = EjecutorFalso()
    contenedor.ejecutor = falso  # type: ignore[assignment]
    aid = _articulo_listo(contenedor, proyecto, "kumar_2022")
    entrar(cliente)
    url = f"/api/v1/proyectos/{proyecto}/extracciones/retomar"
    r = cliente.post(url, json={"articulos": [str(aid)]}).json()[0]
    assert not r["encolado"] and r["sin_datos"]  # sin intento anterior: el diálogo pide los datos
    libro = contenedor.normas.consultas.libro_activo(proyecto)
    previo = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=libro.id,
                                estudios_reservados=[72], datos_del_equipo={
                                    "documento": 5, "estudio_inicial": 72, "covidence": 405, "via": "Covidence"})
    previo.fallar("Interrumpida")
    with contenedor.extraccion.extraer._udt() as u:
        u.extracciones.agregar(previo)
        u.confirmar()
    from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
    contenedor.biblioteca.extraccion.fallar(proyecto, aid, EstadoArticulo.EXTRAYENDO, "Interrumpida")
    r = cliente.post(url, json={"articulos": [str(aid)]}).json()[0]
    assert r["encolado"] and not r["sin_datos"]
    assert falso.pedidos[0].opciones == OpcionesDeExtraccion(documento=5, estudio_inicial=72, covidence=405,
                                                             via="Covidence")

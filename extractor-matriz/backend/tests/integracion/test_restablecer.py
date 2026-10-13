"""Botón «Restablecer errores» y modelos por artículo (ADR 0005 y 0006), sin llamar al modelo real."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.composicion import Contenedor
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.extraccion.adaptadores.repositorio_sql import UnidadDeTrabajoExtraccionSql
from app.contextos.extraccion.dominio.extraccion import Extraccion
from tests.integracion.test_api import cliente  # noqa: F401
from tests.integracion.test_avance import EjecutorFalso, _articulo_listo


def test_restablecer_todos_los_errores(cliente: TestClient, contenedor: Contenedor, proyecto: uuid.UUID) -> None:  # noqa: F811
    contenedor.ejecutor = EjecutorFalso()  # type: ignore[assignment]
    con_error = _articulo_listo(contenedor, proyecto, "kumar_2022")
    sano = _articulo_listo(contenedor, proyecto, "singh_2023")
    contenedor.biblioteca.extraccion.fallar(proyecto, con_error, EstadoArticulo.EXTRAYENDO, "CLI sin sesión")
    r = cliente.post(f"/api/v1/proyectos/{proyecto}/articulos/restablecer", json={})
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [str(con_error)]
    assert contenedor.biblioteca.consultas.articulo(proyecto, con_error).estado == EstadoArticulo.LISTO
    assert contenedor.biblioteca.consultas.articulo(proyecto, sano).estado == EstadoArticulo.LISTO
    assert contenedor.ejecutor.pedidos == []  # type: ignore[attr-defined]  # el reset no lanza extracciones


def test_modelos_de_la_ultima_extraccion(cliente: TestClient, contenedor: Contenedor, proyecto: uuid.UUID) -> None:  # noqa: F811
    aid = _articulo_listo(contenedor, proyecto, "singh_2023")
    ext = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=uuid.uuid4(),
                             estudios_reservados=[7])
    ext.registrar_uso("extractor", {"modelo": "claude-sonnet-5-5"})
    ext.registrar_uso("ciego", {"modelo": "claude-haiku-5-5"})
    ext.registrar_uso("ciego", {"modelo": "claude-sonnet-5-5"})
    with contenedor.fabrica() as s, UnidadDeTrabajoExtraccionSql(lambda: s) as u:  # type: ignore[arg-type]
        u.extracciones.agregar(ext)
        u.confirmar()
    datos: dict[str, Any] = cliente.get(f"/api/v1/proyectos/{proyecto}/extracciones/modelos").json()
    m = datos[str(aid)]
    assert m["registrado"] and m["roles"]["extractor"] == {"claude-sonnet-5-5": 1}
    assert m["roles"]["ciego"] == {"claude-haiku-5-5": 1, "claude-sonnet-5-5": 1}
    assert m["roles"]["auditor"] == {}


def _guardar(contenedor: Contenedor, ext: Extraccion) -> None:
    with contenedor.fabrica() as s, UnidadDeTrabajoExtraccionSql(lambda: s) as u:  # type: ignore[arg-type]
        u.extracciones.agregar(ext)
        u.confirmar()


def test_continuar_relanza_una_extraccion_detenida_sin_restablecerla(cliente: TestClient, contenedor: Contenedor,  # noqa: F811
                                                                    proyecto: uuid.UUID) -> None:
    contenedor.ejecutor = EjecutorFalso()  # type: ignore[assignment]
    aid = _articulo_listo(contenedor, proyecto, "kumar_2022")
    contenedor.biblioteca.extraccion.iniciar(proyecto, aid)
    contenedor.biblioteca.extraccion.auditar(proyecto, aid)  # quedó en AUDITANDO y la aplicación se cerró
    ext = Extraccion.iniciar(proyecto_id=proyecto, articulo_id=aid, version_libro_id=uuid.uuid4(),
                             estudios_reservados=[90], datos_del_equipo={"documento": 17, "via": "Otros métodos: experto"})
    _guardar(contenedor, ext)
    url = f"/api/v1/proyectos/{proyecto}/extracciones"
    assert cliente.get(f"{url}/avance").json()["detenidos"] == [str(aid)]
    (r,) = cliente.post(f"{url}/continuar", json={}).json()
    assert r["accion"] == "extraer" and r["encolado"], r
    (pedido,) = contenedor.ejecutor.pedidos  # type: ignore[attr-defined]
    assert pedido.opciones.documento == 17 and pedido.opciones.via == "Otros métodos: experto"
    assert contenedor.extraccion.consultas.obtener(proyecto, ext.id).estado.value == "FALLIDA"  # el colgado se cerró


def test_continuar_termina_una_conversion_cortada(cliente: TestClient, contenedor: Contenedor,  # noqa: F811
                                                 proyecto: uuid.UUID) -> None:
    contenedor.ejecutor = EjecutorFalso()  # type: ignore[assignment]
    r = contenedor.biblioteca.cargar.ejecutar(proyecto, "b.pdf", b"%PDF-1.4 x")
    assert r.articulo_id is not None
    terminadas: list[uuid.UUID] = []
    contenedor.terminar_conversion = lambda pid, aid: terminadas.append(aid)  # type: ignore[method-assign]
    with contenedor.biblioteca.convertir._udt() as u:  # type: ignore[attr-defined]
        a = u.articulos.obtener(proyecto, r.articulo_id)
        a.iniciar_conversion()  # la conversión quedó cortada
        u.confirmar()
    (item,) = cliente.post(f"/api/v1/proyectos/{proyecto}/extracciones/continuar", json={}).json()
    assert item["accion"] == "convertir" and item["encolado"] and terminadas == [r.articulo_id]
    assert contenedor.ejecutor.pedidos == []  # type: ignore[attr-defined]  # convertir no gasta créditos

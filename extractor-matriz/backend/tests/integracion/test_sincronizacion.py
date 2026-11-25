"""Nube de solo lectura (ADR 0009, Fase 1): réplica completa del equipo local en una segunda base.

La «nube» es otra base de datos con su propia aplicación en MODO=nube (`AlmacenEnBase` real); el agente local le habla
por HTTP a través del TestClient. Corre sobre SQLite y, con PRUEBAS_POSTGRES_URL, sobre PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos
from app.compartido.sobre import hash_de
from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.extraccion.adaptadores.modelo_grabado import ModeloGrabado
from app.contextos.extraccion.adaptadores.repositorio_sql import RegistroExtraccion
from app.contextos.extraccion.aplicacion.casos_de_uso import OpcionesDeExtraccion
from app.contextos.matriz.adaptadores.repositorio_sql import RegistroCelda, RegistroFila
from app.contextos.sincronizacion.adaptadores.cliente_http import ClienteHttp, CredencialesEnMemoria
from app.contextos.sincronizacion.api import hash_de_token
from app.contextos.sincronizacion.dominio.plan import Opciones
from app.contextos.sincronizacion.puertos import Destino
from app.main import crear_app
from tests.conftest import FIXTURES, MATRIZ
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_extraccion_dorada import F0, PENDIENTE, _cargar, _salida_f0

URL = "https://nube.test"
TOKEN = "token-de-servicio-de-prueba"
LECTOR = "lector@ejemplo.co"
SECRETO = "s" * 48


@dataclass
class Mundo:
    local: Contenedor
    nube: Contenedor
    pid: uuid.UUID
    aid: uuid.UUID
    ext_id: uuid.UUID
    http_nube: TestClient  # el agente (sin sesión)
    lector: TestClient  # un lector con sesión
    web_local: TestClient
    ajustes_nube: Settings
    creds: CredencialesEnMemoria


def _ajustes_nube() -> Settings:
    return Settings(_env_file=None, modo="nube", despachador_en_servidor=False, lectores_permitidos=LECTOR,
                    google_client_id="id-de-google", google_client_secret="secreto-de-google",
                    secreto_sesion=SECRETO, sync_token_hash=hash_de_token(TOKEN), url_publica=URL)


def _cookie_de_sesion(correo: str = LECTOR) -> str:
    return URLSafeTimedSerializer(SECRETO, salt="sesion").dumps({"correo": correo})


@pytest.fixture
def mundo(fabrica: Callable[[], Session], fabrica_nube: Callable[[], Session],
          libro_json: dict[str, Any]) -> Mundo:
    carpeta = F0 / "kumar_2022__claude-opus-5-5"
    modelo = ModeloGrabado(por_rol={
        "extractor": json.dumps(_salida_f0(carpeta), ensure_ascii=False),
        "auditor": (carpeta / "auditoria_evidencia.json").read_text(encoding="utf-8"),
        "ciego": (carpeta / "codificacion_ciega.json").read_text(encoding="utf-8"),
        "conciliador": PENDIENTE})
    ajustes_nube = _ajustes_nube()
    nube = construir(ajustes_nube, fabrica=fabrica_nube, conversor=ConversorFijo(FIXTURES / "mineru"))
    app_nube = crear_app(ajustes_nube, contenedor=nube)
    http_nube = TestClient(app_nube, base_url=URL)
    lector = TestClient(app_nube, base_url=URL)
    lector.cookies.set("sesion", _cookie_de_sesion())

    def destino(d: Destino, token: str) -> ClienteHttp:
        return ClienteHttp(d.url, token, d.instalacion_id, cliente=http_nube)

    creds = CredencialesEnMemoria()
    ajustes = Settings(_env_file=None, despachador_en_servidor=False)
    local = construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                      modelo=modelo, credenciales=creds, fabrica_de_destino=destino)  # type: ignore[arg-type]
    pid = nuevo_proyecto(local, "Felicidad y desempeño")
    local.normas.publicar.ejecutar(pid, libro_json)
    local.matriz.importar.ejecutar(pid, MATRIZ.read_bytes(), MATRIZ.name)
    aid = _cargar(local, pid, "kumar_2022")
    r = local.extraccion.extraer.ejecutar(pid, aid, OpcionesDeExtraccion(documento=1, estudio_inicial=1, covidence=671))
    assert r.estado == "COMPLETADA", r.errores
    while local.despachador.despachar_pendientes():
        pass
    local.destinos.guardar(Destino(proyecto_id=pid, url=URL, instalacion_id="equipo-1"))
    creds.guardar(pid, TOKEN)
    return Mundo(local, nube, pid, aid, r.extraccion_id, http_nube, lector, TestClient(crear_app(ajustes, contenedor=local)),
                 ajustes_nube, creds)


def _datos_extraccion(c: Contenedor, ext_id: uuid.UUID) -> dict[str, Any]:
    with c.fabrica() as s:
        r = s.get(RegistroExtraccion, ext_id)
        assert r is not None
        return a_datos(r)


def _manifiesto(c: Contenedor, pid: uuid.UUID) -> dict[str, str]:
    return c.ingesta.manifiesto(pid).items


# ------------------------------------------------------------------------------------------------ la réplica
def test_primera_pasada_y_segunda_sin_envios(mundo: Mundo) -> None:
    c1 = mundo.local.sincronizador.pasada(mundo.pid, motivo="manual")
    assert c1.estado == "ok", c1.detalle
    assert c1.sobres > 70 and c1.archivos >= 3  # 71 filas + libro + artículo + documento + extracción + base…
    assert c1.revision and c1.revision >= 1
    # La nube quedó con exactamente lo mismo que el equipo.
    local = {k: v for k, v in _manifiesto(mundo.local, mundo.pid).items()}
    assert _manifiesto(mundo.nube, mundo.pid) == local
    c2 = mundo.local.sincronizador.pasada(mundo.pid, motivo="manual")
    assert (c2.estado, c2.sobres, c2.archivos, c2.eliminados) == ("ok", 0, 0, 0)  # segunda pasada = 0 envíos
    assert c2.revision == c1.revision  # sin cambios, la revisión no sube


def test_extraccion_completa_bit_a_bit(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    a = _datos_extraccion(mundo.local, mundo.ext_id)
    b = _datos_extraccion(mundo.nube, mundo.ext_id)
    assert len(a) >= 25 and hash_de(a) == hash_de(b)
    assert a["salida"] and a["anclas"] and a["hallazgos"] and a["uso_tokens"]
    assert a == b


def test_paridad_de_la_api_local_y_nube(mundo: Mundo) -> None:
    """La central: las respuestas de lectura son idénticas en el equipo y en la nube."""
    mundo.local.sincronizador.pasada(mundo.pid)
    p = f"/api/v1/proyectos/{mundo.pid}"
    rutas = [f"{p}/matriz/filas?pagina=1&tam=500", f"{p}/articulos", f"{p}/articulos/{mundo.aid}",
             f"{p}/articulos/{mundo.aid}/documento", f"{p}/normas/columnas", f"{p}/normas/libros",
             f"{p}/extracciones", f"{p}/extracciones/{mundo.ext_id}", f"{p}/extracciones/modelos",
             f"{p}/matriz/filas/1/celdas/Muestra", f"{p}/matriz/filas/1/celdas/Correlación Feli 1 - JP",
             f"{p}/matriz/filas/2/celdas/Muestra", "/api/v1/proyectos"]
    for ruta in rutas:
        a, b = mundo.web_local.get(ruta), mundo.lector.get(ruta)
        assert (a.status_code, b.status_code) == (200, 200), (ruta, a.text[:200], b.text[:200])
        assert a.json() == b.json(), ruta
    # Todas las celdas de la fila extraída (con evidencias, anclas e historial).
    columnas = [c["clave"] for c in mundo.web_local.get(f"{p}/normas/columnas").json()]
    for k in columnas:
        ruta = f"{p}/matriz/filas/1/celdas/{k}"
        assert mundo.web_local.get(ruta).json() == mundo.lector.get(ruta).json(), k
    # El PDF, entero y por tramos.
    pdf = f"{p}/articulos/{mundo.aid}/pdf"
    assert mundo.web_local.get(pdf).content == mundo.lector.get(pdf).content
    tramo = mundo.lector.get(pdf, headers={"Range": "bytes=0-99"})
    assert tramo.status_code == 206 and tramo.content == mundo.web_local.get(pdf).content[:100]


def test_los_59_registros_se_ven_en_la_lista_y_completos(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    p = f"/api/v1/proyectos/{mundo.pid}"
    lista = mundo.lector.get(f"{p}/extracciones", params={"articulo": str(mundo.aid)}).json()
    assert [e["id"] for e in lista] == [str(mundo.ext_id)] and lista[0]["estado"] == "COMPLETADA"
    assert "salida" not in lista[0]  # la lista no lleva cuerpos
    completa = mundo.lector.get(f"{p}/extracciones/{mundo.ext_id}").json()
    assert {"salida", "codificacion_ciega", "anclas", "hallazgos", "errores_validador", "avisos_validador",
            "uso_tokens", "datos_del_equipo"} <= set(completa)


def test_cambio_de_una_celda_llega_y_sube_la_revision(mundo: Mundo) -> None:
    c1 = mundo.local.sincronizador.pasada(mundo.pid)
    mundo.web_local.post(f"/api/v1/proyectos/{mundo.pid}/matriz/filas/1/celdas/Muestra/aprobar", json={"motivo": "ok"})
    c2 = mundo.local.sincronizador.pasada(mundo.pid)
    assert c2.estado == "ok" and c2.sobres == 1 and c2.archivos == 0
    assert c2.revision == (c1.revision or 0) + 1
    celda = mundo.lector.get(f"/api/v1/proyectos/{mundo.pid}/matriz/filas/1/celdas/Muestra").json()
    assert celda["estado_revision"] == "APROBADA" and celda["historial"]


def test_nube_vaciada_o_alterada_se_repara_sola(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    con_celdas = mundo.nube
    with con_celdas.fabrica() as s:  # alguien altera una celda y borra una fila en la nube
        s.execute(update(RegistroCelda).where(RegistroCelda.clave == "Muestra").values(valor=999))
        fila = s.scalars(select(RegistroFila).where(RegistroFila.estudio == 2)).one()
        s.execute(delete(RegistroCelda).where(RegistroCelda.fila_id == fila.id))
        s.execute(delete(RegistroFila).where(RegistroFila.id == fila.id))
        s.commit()
    assert _manifiesto(mundo.nube, mundo.pid) != _manifiesto(mundo.local, mundo.pid)
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "ok" and c.sobres >= 2
    assert _manifiesto(mundo.nube, mundo.pid) == _manifiesto(mundo.local, mundo.pid)


def test_reenviar_todo_manda_todo_de_nuevo(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    c = mundo.local.sincronizador.pasada(mundo.pid, todo=True, tomar_control=True)
    assert c.estado == "ok" and c.sobres > 70 and c.archivos >= 3
    assert _manifiesto(mundo.nube, mundo.pid) == _manifiesto(mundo.local, mundo.pid)


def test_una_fila_eliminada_desaparece_de_la_nube(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    with mundo.local.fabrica() as s:
        fila = s.scalars(select(RegistroFila).where(RegistroFila.estudio == 5)).one()
        s.execute(delete(RegistroCelda).where(RegistroCelda.fila_id == fila.id))
        s.execute(delete(RegistroFila).where(RegistroFila.id == fila.id))
        s.commit()
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "ok" and c.eliminados == 1
    filas = mundo.lector.get(f"/api/v1/proyectos/{mundo.pid}/matriz/filas?pagina=1&tam=500").json()
    assert 5 not in [f["estudio"] for f in filas["filas"]] and filas["total"] == 70


def test_fila_reemplazada_con_el_mismo_estudio(mundo: Mundo) -> None:
    """Una fila que vuelve con otro id y el mismo número de Estudio (índice único): la vieja sale, la nueva entra."""
    mundo.local.sincronizador.pasada(mundo.pid)
    nuevo_id = uuid.uuid4()
    with mundo.local.fabrica() as s:
        vieja = s.scalars(select(RegistroFila).where(RegistroFila.estudio == 3)).one()
        celdas = list(s.scalars(select(RegistroCelda).where(RegistroCelda.fila_id == vieja.id)))
        copia = {k: getattr(vieja, k) for k in ("proyecto_id", "estudio", "documento", "articulo_id", "origen",
                                                "version_libro_id", "version_desactualizada", "aprobada",
                                                "trazabilidad", "creado_en", "actualizado_en")}
        datos_celdas = [{k: getattr(c, k) for k in ("clave", "valor", "estado_dato", "tipo_valor", "evidencias",
                                                    "inferencia", "estado_revision", "historial")} for c in celdas]
        s.execute(delete(RegistroCelda).where(RegistroCelda.fila_id == vieja.id))
        s.execute(delete(RegistroFila).where(RegistroFila.id == vieja.id))
        s.flush()
        s.add(RegistroFila(id=nuevo_id, **copia))
        s.flush()
        for d in datos_celdas:
            s.add(RegistroCelda(fila_id=nuevo_id, **d))
        s.commit()
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "ok", c.detalle
    assert _manifiesto(mundo.nube, mundo.pid) == _manifiesto(mundo.local, mundo.pid)
    filas = mundo.lector.get(f"/api/v1/proyectos/{mundo.pid}/matriz/filas?pagina=1&tam=500").json()
    assert [f["id"] for f in filas["filas"] if f["estudio"] == 3] == [str(nuevo_id)] and filas["total"] == 71


def test_extraccion_en_curso_no_se_envia_hasta_terminar(mundo: Mundo) -> None:
    with mundo.local.fabrica() as s:
        s.execute(update(RegistroExtraccion).where(RegistroExtraccion.id == mundo.ext_id).values(
            estado="EXTRAYENDO", terminada_en=None))
        s.commit()
    mundo.local.sincronizador.pasada(mundo.pid)
    assert f"extraccion/{mundo.ext_id}" not in _manifiesto(mundo.nube, mundo.pid)
    with mundo.local.fabrica() as s:
        s.execute(update(RegistroExtraccion).where(RegistroExtraccion.id == mundo.ext_id).values(estado="COMPLETADA"))
        s.commit()
    mundo.local.sincronizador.pasada(mundo.pid)
    assert f"extraccion/{mundo.ext_id}" in _manifiesto(mundo.nube, mundo.pid)


def test_opciones_apagadas_no_suben_ni_borran(mundo: Mundo) -> None:
    mundo.web_local.post(f"/api/v1/proyectos/{mundo.pid}/matriz/filas/1/celdas/Muestra/aprobar", json={"motivo": "ok"})
    mundo.local.sincronizador.pasada(mundo.pid)
    d = mundo.local.destinos.obtener(mundo.pid)
    assert d is not None
    d.opciones = Opciones(extraccion=False, crudo=False, historial=False)
    mundo.local.destinos.guardar(d)
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "ok" and c.eliminados == 0
    assert f"extraccion/{mundo.ext_id}" in _manifiesto(mundo.nube, mundo.pid)  # lo ya subido se queda
    assert c.sobres == 1  # la fila con historial cambió su hash (sin historial) y se reenvió
    assert mundo.local.sincronizador.pasada(mundo.pid).sobres == 0  # y la siguiente pasada vuelve a estar en paz


def test_otro_equipo_recibe_409_y_reenviar_toma_el_control(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    d = mundo.local.destinos.obtener(mundo.pid)
    assert d is not None
    d.instalacion_id = "equipo-2"
    mundo.local.destinos.guardar(d)
    mundo.web_local.post(f"/api/v1/proyectos/{mundo.pid}/matriz/filas/1/celdas/Muestra/aprobar", json={})
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "error" and "Otro equipo" in c.detalle
    assert mundo.local.sincronizador.pasada(mundo.pid, todo=True, tomar_control=True).estado == "ok"


def test_nube_caida_es_sin_conexion_y_la_app_sigue(mundo: Mundo) -> None:
    d = mundo.local.destinos.obtener(mundo.pid)
    assert d is not None
    d.url = "https://no-existe.invalid"
    mundo.local.destinos.guardar(d)

    def caida(destino: Destino, token: str) -> ClienteHttp:
        import httpx

        def rota(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sin red")

        return ClienteHttp(destino.url, token, destino.instalacion_id, cliente=httpx.Client(transport=httpx.MockTransport(rota)))

    mundo.local.sincronizador._fabrica = caida
    c = mundo.local.sincronizador.pasada(mundo.pid)
    assert c.estado == "sin_conexion" and "No se pudo hablar" in c.detalle
    assert mundo.web_local.get(f"/api/v1/proyectos/{mundo.pid}/articulos").status_code == 200  # la app local sigue


# ---------------------------------------------------------------------------------------- protocolo de la nube
def _sobre_de_prueba(pid: uuid.UUID) -> dict[str, Any]:
    return {"esquema": 1, "sobres": []}


def test_lote_idempotente_y_esquema_mayor(mundo: Mundo) -> None:
    mundo.local.sincronizador.pasada(mundo.pid)
    cab = {"Authorization": f"Bearer {TOKEN}", "X-Instalacion": "equipo-1", "Idempotency-Key": "k1"}
    sobres = [s.a_json() for f in mundo.local.sincronizador._fuentes for s in f.sobres(mundo.pid) if s.tipo == "libro"]
    r1 = mundo.http_nube.put("/api/v1/sync/lote", json={"esquema": 1, "sobres": sobres}, headers=cab)
    r2 = mundo.http_nube.put("/api/v1/sync/lote", json={"esquema": 1, "sobres": sobres}, headers=cab)
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert r1.json()["aplicados"] == 0 and r1.json()["iguales"] == len(sobres)
    r3 = mundo.http_nube.put("/api/v1/sync/lote", json={"esquema": 2, "sobres": sobres}, headers=cab)
    assert r3.status_code == 426
    r4 = mundo.http_nube.put("/api/v1/sync/lote", json={"esquema": 1, "sobres": [
        {"tipo": "otra-cosa", "id": "x", "proyecto_id": str(mundo.pid), "datos": {}}]}, headers={**cab, "Idempotency-Key": "k2"})
    assert r4.status_code == 422


def test_archivo_alterado_se_rechaza(mundo: Mundo) -> None:
    cab = {"Authorization": f"Bearer {TOKEN}", "X-Sha256": hashlib.sha256(b"uno").hexdigest()}
    r = mundo.http_nube.put("/api/v1/sync/archivos", params={"clave": "pdf/x/y.pdf"}, content=b"otro", headers=cab)
    assert r.status_code == 422
    r = mundo.http_nube.put("/api/v1/sync/archivos", params={"clave": "../../etc/passwd"}, content=b"uno", headers=cab)
    assert r.status_code == 422


def test_lote_a_medias_no_deja_nada(mundo: Mundo) -> None:
    """Una transacción por lote: si un sobre falla, ninguno queda aplicado."""
    cab = {"Authorization": f"Bearer {TOKEN}"}
    mundo.local.sincronizador.pasada(mundo.pid)
    antes = _manifiesto(mundo.nube, mundo.pid)
    rev = mundo.nube.ingesta.revision()
    sobres = [s for f in mundo.local.sincronizador._fuentes for s in f.sobres(mundo.pid) if s.tipo == "libro"]
    malo = sobres[0].a_json()
    malo["datos"] = {**malo["datos"], "contenido": {"otro": 1}, "hash": "x" * 64, "version": "9.9"}
    malo2 = {"tipo": "fila", "id": str(uuid.uuid4()), "proyecto_id": str(mundo.pid),
             "datos": {"id": "no-es-uuid"}}  # falla al leer el UUID
    r = mundo.http_nube.put("/api/v1/sync/lote", json={"esquema": 1, "sobres": [malo, malo2]}, headers=cab)
    assert r.status_code >= 400
    assert _manifiesto(mundo.nube, mundo.pid) == antes and mundo.nube.ingesta.revision() == rev


# ------------------------------------------------------------------------------------------------ seguridad
def test_sin_sesion_401_con_token_de_servicio_tampoco_lee(mundo: Mundo) -> None:
    p = f"/api/v1/proyectos/{mundo.pid}/articulos"
    mundo.local.sincronizador.pasada(mundo.pid)
    anonimo = TestClient(mundo.http_nube.app, base_url=URL)
    assert anonimo.get(p).status_code == 401
    assert anonimo.get(p, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 401  # el token no lee
    assert anonimo.get("/api/v1/revision").status_code == 401
    assert anonimo.get("/api/v1/salud").status_code == 200  # el keepalive no pide sesión
    assert mundo.lector.get(p).status_code == 200


def test_el_lector_no_escribe_y_no_usa_sync(mundo: Mundo) -> None:
    p = f"/api/v1/proyectos/{mundo.pid}"
    for metodo, ruta in (("post", f"{p}/matriz/filas/1/celdas/Muestra/aprobar"), ("post", f"{p}/articulos/restablecer"),
                         ("post", f"{p}/extracciones"), ("post", f"{p}/exportaciones"),
                         ("delete", f"{p}/articulos/{mundo.aid}")):
        r = mundo.lector.request(metodo.upper(), ruta, json={}) if metodo != "delete" else mundo.lector.delete(ruta)
        assert r.status_code == 405, (ruta, r.status_code)
    assert mundo.lector.get("/api/v1/sync/manifiesto", params={"proyecto": str(mundo.pid)}).status_code == 401
    assert mundo.lector.put("/api/v1/sync/lote", json={"esquema": 1, "sobres": []}).status_code == 401


def test_token_de_servicio_incorrecto(mundo: Mundo) -> None:
    r = mundo.http_nube.get("/api/v1/sync/salud", headers={"Authorization": "Bearer otro"})
    assert r.status_code == 401
    assert mundo.http_nube.get("/api/v1/sync/salud").status_code == 401
    assert mundo.http_nube.get("/api/v1/sync/salud", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_lector_de_otro_correo_o_cookie_falsa(mundo: Mundo) -> None:
    p = f"/api/v1/proyectos/{mundo.pid}/articulos"
    ajeno = TestClient(mundo.http_nube.app, base_url=URL)
    ajeno.cookies.set("sesion", _cookie_de_sesion("intruso@ejemplo.co"))
    assert ajeno.get(p).status_code == 401  # firmada bien, pero el correo no está en la lista
    falso = TestClient(mundo.http_nube.app, base_url=URL)
    falso.cookies.set("sesion", "inventada")
    assert falso.get(p).status_code == 401


def test_nube_sin_configuracion_de_acceso_no_arranca(fabrica_nube: Callable[[], Session]) -> None:
    ajustes = Settings(_env_file=None, modo="nube", despachador_en_servidor=False)
    c = construir(ajustes, fabrica=fabrica_nube, conversor=ConversorFijo(FIXTURES / "mineru"))
    with pytest.raises(RuntimeError, match="LECTORES_PERMITIDOS"):
        crear_app(ajustes, contenedor=c)
    assert set(ajustes.faltantes_de_nube()) == {"LECTORES_PERMITIDOS", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
                                                "SECRETO_SESION", "SYNC_TOKEN_HASH", "URL_PUBLICA"}


def test_capacidades_y_revision_con_etag(mundo: Mundo) -> None:
    cap = mundo.lector.get("/api/v1/capacidades").json()
    assert (cap["modo"], cap["escritura"], cap["autenticado"], cap["lector"]) == ("nube", False, True, LECTOR)
    anonimo = TestClient(mundo.http_nube.app, base_url=URL).get("/api/v1/capacidades").json()
    assert (anonimo["modo"], anonimo["autenticado"], anonimo["lector"]) == ("nube", False, None)
    assert mundo.web_local.get("/api/v1/capacidades").json()["escritura"] is True
    mundo.local.sincronizador.pasada(mundo.pid)
    r = mundo.lector.get("/api/v1/revision")
    assert r.json()["revision"] == mundo.nube.ingesta.revision() >= 1
    assert mundo.lector.get("/api/v1/revision", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_inicio_de_sesion_con_google(mundo: Mundo) -> None:
    import time

    reclamos = {"email": LECTOR, "email_verified": True, "aud": "id-de-google", "iss": "https://accounts.google.com",
                "exp": time.time() + 600}
    mundo.local.sincronizador.pasada(mundo.pid)
    app = crear_app(mundo.ajustes_nube, contenedor=mundo.nube, intercambiar_codigo=lambda code, uri: reclamos)
    c = TestClient(app, base_url=URL, follow_redirects=False)
    r = c.get("/api/v1/auth/google/entrar")
    assert r.status_code == 302 and r.headers["location"].startswith("https://accounts.google.com/")
    estado = r.headers["location"].split("state=")[1].split("&")[0]
    ok = c.get("/api/v1/auth/google/retorno", params={"code": "c", "state": estado})
    assert ok.status_code == 302 and "sesion" in ok.headers["set-cookie"]
    assert c.get("/api/v1/auth/yo").json() == {"correo": LECTOR}
    assert c.get(f"/api/v1/proyectos/{mundo.pid}/articulos").status_code == 200
    # Estado distinto (intento ajeno) y correo no permitido: se rechazan.
    c2 = TestClient(app, base_url=URL, follow_redirects=False)
    c2.get("/api/v1/auth/google/entrar")
    assert c2.get("/api/v1/auth/google/retorno", params={"code": "c", "state": "otro"}).status_code == 400
    reclamos["email"] = "intruso@ejemplo.co"
    c3 = TestClient(app, base_url=URL, follow_redirects=False)
    estado3 = c3.get("/api/v1/auth/google/entrar").headers["location"].split("state=")[1].split("&")[0]
    assert c3.get("/api/v1/auth/google/retorno", params={"code": "c", "state": estado3}).status_code == 403
    assert c3.get("/api/v1/auth/yo").status_code == 401


# --------------------------------------------------------------------------------------- panel local (API)
def test_api_local_ajustes_probar_y_el_token_no_se_devuelve(mundo: Mundo) -> None:
    p = f"/api/v1/proyectos/{mundo.pid}/sincronizacion"
    r = mundo.web_local.put(f"{p}/ajustes", json={"url": URL, "token": "otro-token-secreto", "pausado": True,
                                                  "opciones": {"crudo": False}})
    assert r.status_code == 200
    cuerpo = r.text + mundo.web_local.get(f"{p}/ajustes").text
    assert "otro-token-secreto" not in cuerpo and r.json()["token_guardado"] is True
    assert r.json()["opciones"]["crudo"] is False and r.json()["opciones"]["pdf"] is True
    assert mundo.web_local.put(f"{p}/ajustes", json={"url": "http://remoto.com"}).status_code == 422  # solo https
    mundo.web_local.put(f"{p}/ajustes", json={"token": TOKEN, "pausado": False})
    pr = mundo.web_local.post(f"{p}/probar").json()
    assert pr["ok"] is True, pr
    assert [x["nombre"] for x in pr["pasos"]][-3:] == ["Token aceptado", "Versión de esquema", "Base de datos"]
    mundo.web_local.put(f"{p}/ajustes", json={"token": "equivocado"})
    pr = mundo.web_local.post(f"{p}/probar").json()
    assert pr["ok"] is False and any(x["nombre"] == "Token aceptado" and not x["ok"] for x in pr["pasos"])
    mundo.web_local.put(f"{p}/ajustes", json={"token": TOKEN})
    v = mundo.web_local.post(f"{p}/verificar").json()
    assert v["ok"] is False and v["por_subir"] > 70  # nada se ha enviado aún
    mundo.local.sincronizador.pasada(mundo.pid)
    assert mundo.web_local.post(f"{p}/verificar").json()["ok"] is True
    corridas = mundo.web_local.get(f"{p}/corridas").json()
    assert corridas and corridas[0]["estado"] == "ok"
    assert TOKEN not in mundo.web_local.get(f"{p}/corridas").text

"""«Buscar» en la nube (ADR 0012): lo hecho en el equipo viaja a la nube y allí se lee igual; desde la web solo se puede
buscar, y lo buscado allí vuelve al equipo sin borrarse ni duplicarse.

Igual que `test_sincronizacion.py`, la «nube» es otra base con su propia aplicación en MODO=nube y el agente local le
habla por HTTP a través del TestClient. Las fuentes y los PDF son falsos: nada sale a internet.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compartido.sobre import ESQUEMA, ORDEN_DE_TIPOS
from app.composicion import Contenedor, construir
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnMemoria
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo
from app.contextos.descubrimiento.adaptadores.replica import ReplicaDeDescubrimiento
from app.contextos.descubrimiento.adaptadores.tablas import (
    RegistroCandidato,
    RegistroHallazgo,
    RegistroPerfil,
)
from app.contextos.descubrimiento.aplicacion.casos_de_uso import lanzar_aqui
from app.contextos.descubrimiento.dominio.candidato import Candidato, RegistroBibliografico
from app.contextos.sincronizacion.adaptadores.cliente_http import ClienteHttp, CredencialesEnMemoria
from app.contextos.sincronizacion.dominio.plan import Opciones
from app.contextos.sincronizacion.puertos import Destino
from app.main import crear_app
from tests.conftest import FIXTURES
from tests.integracion.conftest import nuevo_proyecto
from tests.integracion.test_descubrimiento import FuenteFalsa, PdfsQueResponden, buscar, reg
from tests.integracion.test_descubrimiento_analizar import TextoFalso, analizar, id_de, perfil_de_prueba
from tests.integracion.test_descubrimiento_importar import (
    CON_PDF,
    FALLA,
    IGUAL,
    OTRO_PDF,
    SIN_COPIA,
    PdfFalso,
)
from tests.integracion.test_sincronizacion import TOKEN, URL, _ajustes_nube, _cookie_de_sesion
from tests.unitarias.test_descubrimiento_texto_completo import PAGINAS

TIPOS = ("busqueda", "candidato", "perfil")


@dataclass
class Mundo:
    local: Contenedor
    nube: Contenedor
    pid: uuid.UUID
    p: str  # prefijo de las rutas del proyecto
    web: TestClient  # el equipo local
    lector: TestClient  # un lector con sesión en la nube
    anonimo: TestClient  # la nube sin sesión
    uno: uuid.UUID  # candidato con texto analizado
    dos: uuid.UUID  # candidato descartado
    ajustes_nube: Settings

    def la_web_encuentra(self, *registros: RegistroBibliografico) -> None:
        self.nube.descubrimiento.buscar._fuentes = {"a": FuenteFalsa("a", list(registros))}  # type: ignore[assignment]

    def el_equipo_encuentra(self, *registros: RegistroBibliografico) -> None:
        self.local.descubrimiento.buscar._fuentes = {"a": FuenteFalsa("a", list(registros))}  # type: ignore[assignment]


@pytest.fixture
def mundo(fabrica: Callable[[], Session], fabrica_nube: Callable[[], Session], libro_json: dict[str, Any]) -> Mundo:
    ajustes_nube = _ajustes_nube()
    nube = construir(ajustes_nube, fabrica=fabrica_nube, conversor=ConversorFijo(FIXTURES / "mineru"),
                     fuentes_de_busqueda={"a": FuenteFalsa("a", [CON_PDF, IGUAL, FALLA])}, lanzar_busqueda=lanzar_aqui,
                     comprobador_pdf=PdfsQueResponden())
    app_nube = crear_app(ajustes_nube, contenedor=nube)
    anonimo = TestClient(app_nube, base_url=URL)
    lector = TestClient(app_nube, base_url=URL)
    lector.cookies.set("sesion", _cookie_de_sesion())
    agente = TestClient(app_nube, base_url=URL)

    def destino(d: Destino, token: str) -> ClienteHttp:
        return ClienteHttp(d.url, token, d.instalacion_id, cliente=agente)

    creds = CredencialesEnMemoria()
    ajustes = Settings(_env_file=None, despachador_en_servidor=False)
    local = construir(ajustes, fabrica=fabrica, almacen=AlmacenEnMemoria(), conversor=ConversorFijo(FIXTURES / "mineru"),
                      credenciales=creds, fabrica_de_destino=destino,  # type: ignore[arg-type]
                      fuentes_de_busqueda={"a": FuenteFalsa("a", [CON_PDF, OTRO_PDF, SIN_COPIA])},
                      lanzar_busqueda=lanzar_aqui, comprobador_pdf=PdfsQueResponden(), obtener_pdf=PdfFalso(),
                      extraer_texto=TextoFalso(PAGINAS))
    pid = nuevo_proyecto(local, "Felicidad y desempeño")
    local.normas.publicar.ejecutar(pid, libro_json)
    local.destinos.guardar(Destino(proyecto_id=pid, url=URL, instalacion_id="equipo-1"))
    creds.guardar(pid, TOKEN)
    web = TestClient(crear_app(ajustes, contenedor=local))

    buscar(local, pid, ("a",))
    perfil_de_prueba(web, pid)
    uno, dos = id_de(local, pid, "10.1000/uno"), id_de(local, pid, "10.1000/dos")
    analizar(web, pid, uno)
    r = web.post(f"/api/v1/proyectos/{pid}/candidatos/decision",
                 json={"ids": [str(dos)], "accion": "descartar", "motivo": "no mide desempeño"})
    assert r.status_code == 200, r.text
    return Mundo(local, nube, pid, f"/api/v1/proyectos/{pid}", web, lector, anonimo, uno, dos, ajustes_nube)


def sincronizar(m: Mundo) -> tuple[str, int, int]:
    c = m.local.sincronizador.pasada(m.pid)
    assert c.estado == "ok", c.detalle
    return c.estado, c.sobres, c.eliminados


def de_buscar(c: Contenedor, pid: uuid.UUID) -> dict[str, str]:
    return {k: v for k, v in c.ingesta.manifiesto(pid).items.items() if k.split("/")[0] in TIPOS}


def cuantos(items: dict[str, str]) -> dict[str, int]:
    return {t: sum(1 for k in items if k.startswith(t + "/")) for t in TIPOS}


# ------------------------------------------------------------------------------------------------ la réplica
def test_los_tipos_nuevos_van_despues_de_lo_que_referencian_y_suben_la_version_del_formato() -> None:
    assert ORDEN_DE_TIPOS.index("proyecto") < ORDEN_DE_TIPOS.index("busqueda") < ORDEN_DE_TIPOS.index("candidato")
    assert ESQUEMA == 3  # una nube sin actualizar responde 426 en vez de rechazar tipos que no conoce


def test_la_busqueda_llega_a_la_nube_y_la_segunda_pasada_no_envia_nada(mundo: Mundo) -> None:
    sincronizar(mundo)
    local = de_buscar(mundo.local, mundo.pid)
    assert cuantos(local) == {"busqueda": 1, "candidato": 3, "perfil": 1}
    assert de_buscar(mundo.nube, mundo.pid) == local
    assert sincronizar(mundo) == ("ok", 0, 0)


def test_la_nube_responde_lo_mismo_que_el_equipo(mundo: Mundo) -> None:
    sincronizar(mundo)
    p = mundo.p
    for ruta in (f"{p}/candidatos?orden=puntaje", f"{p}/candidatos?estado=DESCARTADO", f"{p}/busquedas",
                 f"{p}/busqueda/columnas"):
        nube, local = mundo.lector.get(ruta), mundo.web.get(ruta)
        assert nube.status_code == 200, f"{ruta}: {nube.text}"
        assert nube.json() == local.json(), ruta
    perfiles_nube, perfiles_local = (c.get(f"{p}/busqueda/perfiles").json() for c in (mundo.lector, mundo.web))
    for respuesta in (perfiles_nube, perfiles_local):
        del respuesta["inicial"]["id"]  # la propuesta inicial no se guarda: su id cambia en cada consulta
    assert perfiles_nube == perfiles_local
    # El análisis del texto completo (etapa B) también llegó, con su página.
    uno = next(c for c in mundo.lector.get(f"{p}/candidatos").json()["candidatos"] if c["id"] == str(mundo.uno))
    muestra = next(x for x in uno["evaluacion"]["celdas"] if x["columna"] == "Muestra")
    assert uno["evaluacion"]["etapa"] == "B" and muestra["origen"] == "p. 2 · método"
    assert mundo.lector.get(f"{p}/busqueda/configuracion").status_code == 200


def test_las_fechas_viajan_con_zona(mundo: Mundo) -> None:
    sincronizar(mundo)
    creada = mundo.lector.get(f"{mundo.p}/busquedas").json()["busquedas"][0]["creada_en"]
    assert creada.endswith("+00:00")  # sin zona, el navegador la leería como hora local


def test_en_la_nube_se_puede_ver_la_vista_previa_y_exportar(mundo: Mundo) -> None:
    sincronizar(mundo)
    perfil = mundo.web.get(f"{mundo.p}/busqueda/perfiles").json()["perfiles"][0]["id"]
    seleccion = {"ids": [str(mundo.uno), str(mundo.dos)], "perfil_id": perfil}
    ruta = f"{mundo.p}/candidatos/vista-previa"
    nube = mundo.lector.post(ruta, json=seleccion)
    assert nube.status_code == 200, nube.text
    assert nube.json() == mundo.web.post(ruta, json=seleccion).json()
    for formato in ("csv", "ris"):
        ruta = f"{mundo.p}/candidatos/exportar"
        cuerpo = {**seleccion, "formato": formato}
        nube = mundo.lector.post(ruta, json=cuerpo)
        assert nube.status_code == 200 and nube.content == mundo.web.post(ruta, json=cuerpo).content, formato


def test_en_la_nube_fuera_de_buscar_nada_se_escribe(mundo: Mundo) -> None:
    sincronizar(mundo)
    antes = de_buscar(mundo.nube, mundo.pid)
    p, uno = mundo.p, str(mundo.uno)
    perfil = mundo.web.get(f"{p}/busqueda/perfiles").json()["perfiles"][0]["id"]
    escrituras: list[tuple[str, str, Any]] = [
        ("POST", f"{p}/candidatos/decision", {"ids": [uno], "accion": "priorizar"}),
        ("POST", f"{p}/candidatos/importar", {"ids": [uno]}),
        ("POST", f"{p}/candidatos/analizar", {"ids": [uno]}),
        ("PUT", f"{p}/busqueda/perfiles", {"nombre": "Otro", "columnas": [{"clave": "Muestra"}]}),
        ("DELETE", f"{p}/busqueda/perfiles/{perfil}", None),
        ("PUT", f"{p}/candidatos/vista-previa", {"ids": [uno]}),  # las excepciones son solo POST y solo esas rutas
        ("PUT", f"{p}/busquedas", {}),
        ("DELETE", f"{p}/busquedas", None),
        ("POST", f"{p}/candidatos/exportar/otra", {"ids": [uno]}),
    ]
    for metodo, ruta, cuerpo in escrituras:
        assert mundo.lector.request(metodo, ruta, json=cuerpo).status_code == 405, (metodo, ruta)
    assert de_buscar(mundo.nube, mundo.pid) == antes


def test_sin_sesion_no_se_lee_nada_ni_con_el_token_del_agente(mundo: Mundo) -> None:
    sincronizar(mundo)
    p, cuerpo = mundo.p, {"ids": [str(mundo.uno)]}
    for cabeceras in ({}, {"Authorization": f"Bearer {TOKEN}"}):
        for ruta in (f"{p}/candidatos", f"{p}/busquedas", f"{p}/busqueda/perfiles"):
            assert mundo.anonimo.get(ruta, headers=cabeceras).status_code == 401, ruta
        for ruta in (f"{p}/candidatos/vista-previa", f"{p}/candidatos/exportar"):
            assert mundo.anonimo.post(ruta, json=cuerpo, headers=cabeceras).status_code == 401, ruta


def test_los_cambios_y_los_borrados_se_propagan(mundo: Mundo) -> None:
    sincronizar(mundo)
    viejo = mundo.web.get(f"{mundo.p}/busqueda/perfiles").json()["perfiles"][0]["id"]
    mundo.web.post(f"{mundo.p}/candidatos/decision", json={"ids": [str(mundo.dos)], "accion": "reactivar"})
    assert mundo.web.delete(f"{mundo.p}/busqueda/perfiles/{viejo}").status_code == 200
    perfil_de_prueba(mundo.web, mundo.pid)  # mismo nombre, otro id
    _, enviados, eliminados = sincronizar(mundo)
    assert enviados == 2 and eliminados == 1  # el candidato y el perfil nuevo; el perfil viejo se borra
    assert de_buscar(mundo.nube, mundo.pid) == de_buscar(mundo.local, mundo.pid)


def test_cada_cambio_avisa_al_agente_de_sincronizacion(mundo: Mundo, monkeypatch: pytest.MonkeyPatch) -> None:
    avisos: list[uuid.UUID] = []
    monkeypatch.setattr(mundo.local.agente, "notificar", avisos.append)
    buscar(mundo.local, mundo.pid, ("a",))
    assert avisos == [mundo.pid]  # al terminar la búsqueda
    mundo.web.post(f"{mundo.p}/candidatos/decision", json={"ids": [str(mundo.uno)], "accion": "priorizar"})
    perfil_de_prueba(mundo.web, mundo.pid)
    analizar(mundo.web, mundo.pid, mundo.uno)
    mundo.web.post(f"{mundo.p}/candidatos/importar", json={"ids": [str(mundo.uno)]})
    perfil = mundo.web.get(f"{mundo.p}/busqueda/perfiles").json()["perfiles"][0]["id"]
    mundo.web.delete(f"{mundo.p}/busqueda/perfiles/{perfil}")
    assert avisos == [mundo.pid] * 6


def test_apagar_la_opcion_deja_de_subir_y_no_borra(mundo: Mundo) -> None:
    sincronizar(mundo)
    antes = de_buscar(mundo.nube, mundo.pid)
    d = mundo.local.destinos.obtener(mundo.pid)
    assert d is not None and d.opciones.busqueda is True  # encendida por defecto
    d.opciones = Opciones(busqueda=False)
    mundo.local.destinos.guardar(d)
    mundo.web.post(f"{mundo.p}/candidatos/decision", json={"ids": [str(mundo.uno)], "accion": "priorizar"})
    assert sincronizar(mundo) == ("ok", 0, 0)
    assert de_buscar(mundo.nube, mundo.pid) == antes


def test_una_busqueda_en_curso_espera_y_una_interrumpida_se_cierra(mundo: Mundo) -> None:
    sincronizar(mundo)
    d = mundo.local.descubrimiento
    d.buscar._lanzar = lambda _tarea: None  # queda «en curso», como si la aplicación se hubiera cerrado en la mitad
    b = d.buscar.iniciar(mundo.pid, "cortada", d.consultas.consulta_inicial(), ("a",))
    nuevo = Candidato.desde(mundo.pid, reg("a", "Gratitude and teacher performance", "10.1000/nuevo"))
    d.buscar._candidatos.guardar(nuevo)
    d.buscar._busquedas.registrar_hallazgo(b.id, nuevo.id, "a", 1)
    assert sincronizar(mundo) == ("ok", 0, 0)  # ni la búsqueda ni lo que apenas va encontrando
    assert d.buscar.cerrar_interrumpidas() == 1
    cerrada = d.consultas.busqueda(mundo.pid, b.id)
    assert cerrada.estado.value == "TERMINADA_CON_ERRORES" and cerrada.total_unicos == 1
    assert "Interrumpida" in (cerrada.progreso["a"].ultimo_error or "")
    assert d.buscar.cerrar_interrumpidas() == 0
    _, enviados, _ = sincronizar(mundo)
    assert enviados == 2
    assert cuantos(de_buscar(mundo.nube, mundo.pid)) == {"busqueda": 2, "candidato": 4, "perfil": 1}


def test_un_registro_rehecho_con_otro_id_reemplaza_al_anterior(mundo: Mundo) -> None:
    """Restaurar sobre datos propios: misma clave (o mismo nombre de perfil) con otro id no choca con el índice único."""
    replica = ReplicaDeDescubrimiento(mundo.local.fabrica)
    sobres = {s.tipo: s for s in replica.sobres(mundo.pid) if s.tipo != "candidato" or s.id == str(mundo.uno)}
    sincronizar(mundo)
    for tipo, modelo in (("perfil", RegistroPerfil), ("candidato", RegistroCandidato)):
        nuevo = uuid.uuid4()
        datos = {**(sobres[tipo].datos or {}), "id": str(nuevo)}
        if datos.get("analisis"):
            datos["analisis"] = {**datos["analisis"], "candidato_id": str(nuevo)}
        sobre = replace(sobres[tipo], id=str(nuevo), datos=datos)
        with mundo.nube.fabrica() as s:
            antes = s.scalar(select(func.count()).select_from(modelo))
            assert replica.aplicar(s, sobre) is True
            s.commit()
            assert s.scalar(select(func.count()).select_from(modelo)) == antes
            assert s.get(modelo, nuevo) is not None and s.get(modelo, uuid.UUID(sobres[tipo].id)) is None
            assert replica.aplicar(s, sobre) is False  # idéntico: nada que escribir
    with mundo.nube.fabrica() as s:
        assert s.scalar(select(func.count()).select_from(RegistroHallazgo)) == 3


def test_restaurar_un_equipo_vacio_recupera_la_busqueda(mundo: Mundo, fabrica_nuevo: Callable[[], Session]) -> None:
    sincronizar(mundo)
    ajustes = Settings(_env_file=None, despachador_en_servidor=False)
    nuevo = construir(ajustes, fabrica=fabrica_nuevo, almacen=AlmacenEnMemoria(),
                      conversor=ConversorFijo(FIXTURES / "mineru"))
    nube = ClienteHttp(URL, TOKEN, "equipo-nuevo", cliente=TestClient(mundo.anonimo.app, base_url=URL))
    nuevo.restaurador.ejecutar(nube, mundo.pid, nube.manifiesto(mundo.pid), reemplazar=False)
    assert de_buscar(nuevo, mundo.pid) == de_buscar(mundo.local, mundo.pid)
    web = TestClient(crear_app(ajustes, contenedor=nuevo))
    ruta = f"{mundo.p}/candidatos?orden=puntaje"
    assert web.get(ruta).json() == mundo.web.get(ruta).json()


# ------------------------------------------------------------------------------------------------ buscar en la web
def buscar_en_la_web(m: Mundo, nombre: str = "desde el celular") -> dict[str, Any]:
    r = m.lector.post(f"{m.p}/busquedas", json={"nombre": nombre, "fuentes": ["a"]})
    assert r.status_code == 202, r.text
    resultado: dict[str, Any] = r.json()
    return resultado


def listado(cliente: TestClient, m: Mundo) -> dict[str, dict[str, Any]]:
    r = cliente.get(f"{m.p}/candidatos?cuantos=500")
    assert r.status_code == 200, r.text
    por_titulo = {c["titulo"]: c for c in r.json()["candidatos"]}
    assert len(por_titulo) == r.json()["total"], "hay candidatos repetidos"
    return por_titulo


def hallazgos_de(c: Contenedor, candidato_id: str) -> int:
    with c.fabrica() as s:
        q = select(func.count()).select_from(RegistroHallazgo).where(RegistroHallazgo.candidato_id == uuid.UUID(candidato_id))
        return int(s.scalar(q) or 0)


def test_buscar_en_la_web_no_toca_lo_del_equipo_hasta_que_se_recoge(mundo: Mundo) -> None:
    sincronizar(mundo)
    antes = de_buscar(mundo.nube, mundo.pid)
    b = buscar_en_la_web(mundo)
    assert (b["estado"], b["origen"]) == ("TERMINADA", "nube")
    assert len(listado(mundo.lector, mundo)) == 5  # los 3 del equipo y 2 nuevos; CON_PDF ya estaba
    assert de_buscar(mundo.nube, mundo.pid) == antes  # nada de lo pendiente entra en el manifiesto
    ruta = f"/api/v1/sync/pendientes?proyecto={mundo.pid}"
    assert mundo.lector.get(ruta).status_code == 401  # el buzón es del agente, no de los lectores
    r = mundo.anonimo.get(ruta, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and len(r.json()["paquetes"]) == 1


def test_lo_buscado_en_la_web_llega_al_equipo_sin_duplicados(mundo: Mundo) -> None:
    sincronizar(mundo)
    b = buscar_en_la_web(mundo)
    sincronizar(mundo)
    recibida = mundo.local.descubrimiento.consultas.busqueda(mundo.pid, uuid.UUID(b["id"]))
    assert recibida.origen.value == "equipo" and recibida.total_unicos == 3 and recibida.nombre == "desde el celular"
    local, nube = listado(mundo.web, mundo), listado(mundo.lector, mundo)
    assert len(local) == 5 and local == nube
    assert de_buscar(mundo.nube, mundo.pid) == de_buscar(mundo.local, mundo.pid)
    assert [x["origen"] for x in mundo.lector.get(f"{mundo.p}/busquedas").json()["busquedas"]] == ["equipo", "equipo"]
    # Lo que la persona ya había hecho en el equipo sigue intacto.
    assert local[OTRO_PDF.titulo]["estado"] == "DESCARTADO" and local[CON_PDF.titulo]["evaluacion"]["etapa"] == "B"
    assert hallazgos_de(mundo.local, str(mundo.uno)) == 2  # ahora lo trajeron las dos búsquedas
    assert sincronizar(mundo) == ("ok", 0, 0)
    assert mundo.anonimo.get(f"/api/v1/sync/pendientes?proyecto={mundo.pid}",
                             headers={"Authorization": f"Bearer {TOKEN}"}).json() == {"paquetes": []}


def test_el_equipo_une_lo_que_ya_tenia_aunque_la_web_le_diera_otro_id(mundo: Mundo) -> None:
    sincronizar(mundo)
    nuevo = reg("a", "Gratitude and teacher performance", "10.1000/nuevo")
    parecido = reg("a", OTRO_PDF.titulo + ".", None, anio=OTRO_PDF.anio)  # sin DOI: se reconoce por el título
    mundo.el_equipo_encuentra(nuevo)
    buscar(mundo.local, mundo.pid, ("a",))  # el equipo lo encuentra y aún no lo ha enviado
    variante = reg("a", nuevo.titulo + ".", None, anio=nuevo.anio)
    mundo.la_web_encuentra(variante, parecido)
    web = buscar_en_la_web(mundo)
    # En la web «parecido» se une con el que ya conoce, pero «variante» es otro: aún no sabe del que halló el equipo.
    assert len(listado(mundo.lector, mundo)) == 4
    sincronizar(mundo)
    local, nube = listado(mundo.web, mundo), listado(mundo.lector, mundo)
    assert len(local) == 4 and local == nube
    assert hallazgos_de(mundo.local, local[nuevo.titulo]["id"]) == 2
    assert hallazgos_de(mundo.local, str(mundo.dos)) == 2
    assert local[OTRO_PDF.titulo]["estado"] == "DESCARTADO"
    assert mundo.local.descubrimiento.consultas.busqueda(mundo.pid, uuid.UUID(web["id"])).total_unicos == 2
    assert sincronizar(mundo) == ("ok", 0, 0)


def test_si_el_envio_llega_antes_que_la_recogida_no_se_pierde_nada(mundo: Mundo, monkeypatch: pytest.MonkeyPatch) -> None:
    """Una búsqueda web que termina entre la recogida y el envío: el envío no la borra, ni por clave repetida."""
    sincronizar(mundo)
    nuevo = reg("a", "Gratitude and teacher performance", "10.1000/nuevo")
    mundo.el_equipo_encuentra(nuevo)
    buscar(mundo.local, mundo.pid, ("a",))
    mundo.la_web_encuentra(nuevo, FALLA)
    web = buscar_en_la_web(mundo)
    with monkeypatch.context() as m:
        m.setattr(mundo.local.sincronizador, "_buzon", None)
        sincronizar(mundo)
    nube = listado(mundo.lector, mundo)
    assert len(nube) == 5 and nube[nuevo.titulo]["id"] == listado(mundo.web, mundo)[nuevo.titulo]["id"]
    assert hallazgos_de(mundo.nube, nube[nuevo.titulo]["id"]) == 2  # conserva lo que falta por recoger
    de_la_web = mundo.lector.get(f"{mundo.p}/candidatos?busqueda_id={web['id']}").json()
    assert de_la_web["total"] == 2
    sincronizar(mundo)
    assert listado(mundo.web, mundo) == listado(mundo.lector, mundo) and len(listado(mundo.web, mundo)) == 5
    assert sincronizar(mundo) == ("ok", 0, 0)


def test_apagar_la_opcion_no_recoge_ni_borra_lo_de_la_web(mundo: Mundo) -> None:
    sincronizar(mundo)
    d = mundo.local.destinos.obtener(mundo.pid)
    assert d is not None
    d.opciones = Opciones(busqueda=False)
    mundo.local.destinos.guardar(d)
    buscar_en_la_web(mundo)
    assert sincronizar(mundo) == ("ok", 0, 0)
    assert len(listado(mundo.lector, mundo)) == 5 and len(listado(mundo.web, mundo)) == 3
    d.opciones = Opciones()
    mundo.local.destinos.guardar(d)
    sincronizar(mundo)
    assert len(listado(mundo.web, mundo)) == 5


def test_recibir_dos_veces_no_duplica(mundo: Mundo) -> None:
    sincronizar(mundo)
    buscar_en_la_web(mundo)
    buzon = mundo.local.sincronizador._buzon
    assert buzon is not None
    paquetes = mundo.nube.ingesta.pendientes(mundo.pid)
    assert buzon.recibir(mundo.pid, paquetes) == 1
    primero = de_buscar(mundo.local, mundo.pid)
    assert buzon.recibir(mundo.pid, paquetes) == 1
    assert de_buscar(mundo.local, mundo.pid) == primero and len(listado(mundo.web, mundo)) == 5


def test_en_la_web_una_busqueda_a_la_vez_y_la_cortada_se_cierra_al_reiniciar(mundo: Mundo) -> None:
    sincronizar(mundo)
    mundo.nube.descubrimiento.buscar._lanzar = lambda _tarea: None  # queda en curso
    primera = buscar_en_la_web(mundo)
    r = mundo.lector.post(f"{mundo.p}/busquedas", json={"fuentes": ["a"]})
    assert r.status_code == 409 and "en curso" in r.json()["detail"]
    assert mundo.lector.post(f"{mundo.p}/busquedas/{primera['id']}/cancelar").status_code == 200
    assert mundo.nube.ingesta.pendientes(mundo.pid) == []  # en curso no se recoge
    with TestClient(crear_app(mundo.ajustes_nube, contenedor=mundo.nube), base_url=URL):
        pass  # el servidor de la nube arranca de nuevo
    cerrada = mundo.lector.get(f"{mundo.p}/busquedas/{primera['id']}").json()
    assert cerrada["estado"] == "TERMINADA_CON_ERRORES"
    sincronizar(mundo)
    assert mundo.web.get(f"{mundo.p}/busquedas/{primera['id']}").status_code == 200


def test_buscar_en_la_web_exige_sesion_y_venir_de_la_propia_pagina(mundo: Mundo) -> None:
    sincronizar(mundo)
    ruta, cuerpo = f"{mundo.p}/busquedas", {"fuentes": ["a"]}
    assert mundo.anonimo.post(ruta, json=cuerpo).status_code == 401
    assert mundo.anonimo.post(ruta, json=cuerpo, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 401
    for ajeno in ("https://otro.sitio", "null"):
        assert mundo.lector.post(ruta, json=cuerpo, headers={"Origin": ajeno}).status_code == 403, ajeno
    assert mundo.lector.get(ruta).json()["busquedas"][0]["origen"] == "equipo"  # no se creó ninguna
    assert mundo.lector.post(ruta, json=cuerpo, headers={"Origin": URL}).status_code == 202
    capacidades = mundo.lector.get("/api/v1/capacidades").json()
    assert capacidades["puede_buscar"] is True and capacidades["escritura"] is False


def test_la_web_anota_el_pdf_de_uno_que_el_equipo_tenia_sin_comprobar(mundo: Mundo) -> None:
    """Candidatos de antes de la regla del PDF: ocultos; una búsqueda web los comprueba sin pisar nada más."""
    with mundo.local.fabrica() as s:
        r = s.get(RegistroCandidato, mundo.uno)
        assert r is not None
        r.url_pdf = None
        s.commit()
    sobre = next(x for x in ReplicaDeDescubrimiento(mundo.local.fabrica).sobres(mundo.pid) if x.id == str(mundo.uno))
    assert "url_pdf" not in (sobre.datos or {})  # sin PDF viaja igual que antes de existir la columna
    sincronizar(mundo)
    assert len(listado(mundo.lector, mundo)) == 2  # oculto en los dos lados
    buscar_en_la_web(mundo)
    nube = listado(mundo.lector, mundo)
    assert nube[CON_PDF.titulo]["url_pdf"] == "https://oa.test/kumar.pdf" and len(nube) == 5
    sincronizar(mundo)
    assert listado(mundo.web, mundo) == listado(mundo.lector, mundo)
    assert listado(mundo.web, mundo)[CON_PDF.titulo]["evaluacion"]["etapa"] == "B"  # lo del equipo sigue
    assert sincronizar(mundo) == ("ok", 0, 0)

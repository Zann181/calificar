"""Lógica pura de la sincronización (plan, lotes, opciones, hash) y el agente con reloj falso."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.compartido.sobre import Sobre, hash_de, json_canonico
from app.contextos.sincronizacion.aplicacion.agente import AgenteDeSincronizacion
from app.contextos.sincronizacion.dominio.plan import Manifiesto, Opciones, calcular_plan, en_lotes, filtrar
from app.contextos.sincronizacion.puertos import Corrida, Destino

PID = str(uuid.uuid4())


def s(tipo: str, id_: str, datos: dict[str, Any] | None = None, archivos: tuple[str, ...] = ()) -> Sobre:
    return Sobre(tipo, id_, PID, datos if datos is not None else {"id": id_}, archivos=archivos)


def test_hash_canonico_no_depende_del_orden_de_las_claves() -> None:
    assert hash_de({"b": 1, "a": [1, 2]}) == hash_de({"a": [1, 2], "b": 1})
    assert json_canonico({"b": 1, "a": "ñ"}) == '{"a":"ñ","b":1}'
    assert hash_de({"a": 1}) != hash_de({"a": 2})


def test_plan_sube_lo_nuevo_y_lo_distinto_y_elimina_lo_que_sobra() -> None:
    local = [s("articulo", "a1"), s("articulo", "a2", {"id": "a2", "x": 2}), s("fila", "f1")]
    nube = Manifiesto(3, {"articulo/a1": local[0].hash, "articulo/a2": "sha256:viejo", "fila/f9": "sha256:z",
                          "documento/d9": "sha256:y"}, {})
    plan = calcular_plan(local, {}, nube, Opciones(), PID)
    assert [x.id for x in plan.subir] == ["a2", "f1"]
    # Los eliminados salen en el orden inverso de las dependencias: primero lo último que se crea.
    assert [(x.tipo, x.id) for x in plan.eliminar] == [("fila", "f9"), ("documento", "d9")]
    assert all(x.eliminado for x in plan.eliminar) and plan.pendientes == 4


def test_plan_vacio_cuando_todo_coincide() -> None:
    local = [s("articulo", "a1", archivos=("pdf/p/a.pdf",))]
    nube = Manifiesto(1, {"articulo/a1": local[0].hash}, {"pdf/p/a.pdf": "abc"})
    assert calcular_plan(local, {"pdf/p/a.pdf": "abc"}, nube, Opciones(), PID).vacio


def test_plan_manda_los_archivos_que_faltan_o_cambiaron() -> None:
    local = [s("articulo", "a1", archivos=("pdf/p/a.pdf", "crudo/a1.zip"))]
    nube = Manifiesto(1, {"articulo/a1": local[0].hash}, {"pdf/p/a.pdf": "distinto"})
    plan = calcular_plan(local, {"pdf/p/a.pdf": "abc", "crudo/a1.zip": "def"}, nube, Opciones(), PID)
    assert plan.archivos == ["pdf/p/a.pdf", "crudo/a1.zip"] and not plan.subir


def test_opciones_filtran_tipos_archivos_e_historial() -> None:
    fila = s("fila", "f1", {"id": "f1", "celdas": [{"clave": "A", "historial": [{"x": 1}]}]})
    base = [s("articulo", "a1", archivos=("pdf/a.pdf", "crudo/a.zip")), s("documento", "d1"), fila,
            s("extraccion", "e1"), s("base", PID, archivos=("matrices/p/b.xlsx",))]
    out = filtrar(base, Opciones(documento=False, extraccion=False, crudo=False, excel=False, historial=False))
    assert [x.tipo for x in out] == ["articulo", "fila", "base"]
    assert out[0].archivos == ("pdf/a.pdf",) and out[2].archivos == ()
    assert out[1].datos is not None and out[1].datos["celdas"][0]["historial"] == []
    assert Opciones().tipos() >= {"proyecto", "libro", "articulo", "documento", "fila", "extraccion", "base"}


def test_opciones_desde_dict_ignora_claves_desconocidas() -> None:
    o = Opciones.desde_dict({"pdf": False, "inventada": True})
    assert o.pdf is False and o.matriz is True and "inventada" not in o.a_dict()


def test_lotes_de_hasta_un_mega_y_uno_enorme_viaja_solo() -> None:
    chicos = [s("fila", str(i), {"id": str(i), "relleno": "x" * 100_000}) for i in range(25)]
    lotes = en_lotes(chicos, 1_000_000)
    assert sum(len(x) for x in lotes) == 25 and all(sum(y.tamano() for y in x) <= 1_000_000 for x in lotes)
    grande = s("documento", "g", {"id": "g", "relleno": "x" * 1_500_000})
    assert en_lotes([chicos[0], grande, chicos[1]], 1_000_000) == [[chicos[0]], [grande], [chicos[1]]]


# ------------------------------------------------------------------------------------------------- el agente
class RepoFalso:
    def __init__(self, d: Destino) -> None:
        self.d = d

    def obtener(self, proyecto_id: uuid.UUID) -> Destino | None:
        return self.d

    def activos(self) -> list[Destino]:
        return [self.d]


class SincronizadorFalso:
    def __init__(self, estados: list[str]) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self._estados = estados

    def pasada(self, proyecto_id: uuid.UUID, **kw: Any) -> Corrida:
        self.llamadas.append(kw)
        estado = self._estados.pop(0) if self._estados else "ok"
        return Corrida(id=uuid.uuid4(), proyecto_id=proyecto_id, iniciada_en=datetime.now(UTC), estado=estado,
                       detalle="" if estado == "ok" else "falló", revision=7)


def _agente(estados: list[str] | None = None, **ajustes: Any) -> tuple[AgenteDeSincronizacion, SincronizadorFalso, list[float], Destino]:
    d = Destino(proyecto_id=uuid.uuid4(), url="https://nube.test", **ajustes)
    sinc = SincronizadorFalso(estados or [])
    reloj = [1000.0]
    agente = AgenteDeSincronizacion(sinc, RepoFalso(d), reloj=lambda: reloj[0])  # type: ignore[arg-type]
    return agente, sinc, reloj, d


def test_agente_agrupa_varios_eventos_en_una_pasada() -> None:
    agente, sinc, reloj, d = _agente(agrupar_s=5)
    for _ in range(4):
        agente.notificar(d.proyecto_id)
    agente._una_vuelta()
    assert sinc.llamadas == []  # todavía dentro de los 5 s de agrupación
    assert agente.estado(d.proyecto_id).eventos_sin_enviar == 4
    reloj[0] += 5.1
    agente._una_vuelta()
    assert len(sinc.llamadas) == 1
    e = agente.estado(d.proyecto_id)
    assert (e.estado, e.revision, e.eventos_sin_enviar) == ("sincronizado", 7, 0)


def test_agente_reconcilia_con_el_temporizador_y_respeta_la_pausa() -> None:
    agente, sinc, reloj, d = _agente(reconciliar_s=600)
    agente._una_vuelta()
    reloj[0] += 1
    agente._una_vuelta()  # la primera vez pide una pasada por temporizador y la agrupa
    reloj[0] += 6
    agente._una_vuelta()
    assert len(sinc.llamadas) == 1
    reloj[0] += 599
    agente._una_vuelta()
    assert len(sinc.llamadas) == 1  # aún no vence la reconciliación
    reloj[0] += 10
    agente._una_vuelta()
    reloj[0] += 6
    agente._una_vuelta()
    assert len(sinc.llamadas) == 2
    d.pausado = True
    reloj[0] += 5000
    agente._una_vuelta()
    reloj[0] += 10
    agente._una_vuelta()
    assert len(sinc.llamadas) == 2 and agente.estado(d.proyecto_id).estado == "pausado"
    agente.ahora(d.proyecto_id)  # «Sincronizar ahora» funciona aunque esté en pausa
    agente._una_vuelta()
    assert len(sinc.llamadas) == 3 and sinc.llamadas[-1]["motivo"] == "manual"


def test_agente_reintenta_con_espera_creciente_tras_un_error_de_red() -> None:
    agente, sinc, reloj, d = _agente(["sin_conexion", "sin_conexion", "ok"], reconciliar_s=86400)
    agente.ahora(d.proyecto_id)
    agente._una_vuelta()
    assert agente.estado(d.proyecto_id).estado == "sin_conexion"
    reloj[0] += 4
    agente._una_vuelta()
    assert len(sinc.llamadas) == 1  # espera 5 s
    reloj[0] += 2
    agente._una_vuelta()
    assert len(sinc.llamadas) == 2  # segundo intento; la siguiente espera es de 10 s
    reloj[0] += 9
    agente._una_vuelta()
    assert len(sinc.llamadas) == 2
    reloj[0] += 2
    agente._una_vuelta()
    assert len(sinc.llamadas) == 3 and agente.estado(d.proyecto_id).estado == "sincronizado"


def test_agente_pasa_reenviar_todo_y_tomar_control() -> None:
    agente, sinc, _, d = _agente()
    agente.ahora(d.proyecto_id, todo=True, tomar_control=True)
    agente._una_vuelta()
    assert sinc.llamadas[0]["todo"] is True and sinc.llamadas[0]["tomar_control"] is True

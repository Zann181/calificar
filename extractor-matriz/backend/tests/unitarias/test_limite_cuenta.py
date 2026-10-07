"""Uso de la cuenta de Claude leído del stream-json de la CLI (ventana de 5 horas y su reinicio)."""

from __future__ import annotations

import json

from app.contextos.extraccion.adaptadores.claude_cli import LimiteDeCuenta, leer_flujo

EVENTO = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1791414600, "rateLimitType": "five_hour",
    "unifiedWindows": {"five_hour": {"utilization": 0.12, "resetsAt": 1791414600},
                       "seven_day": {"utilization": 0.21, "resetsAt": 1791644400}}}}


def test_lee_resultado_y_limite_del_flujo() -> None:
    flujo = "\n".join(json.dumps(o) for o in [
        {"type": "system", "subtype": "init"}, EVENTO,
        {"type": "assistant", "message": {}},
        {"type": "result", "is_error": False, "result": "ok", "usage": {"input_tokens": 9}, "num_turns": 1},
    ]) + "\nbasura que no es JSON\n"
    resultado, limite = leer_flujo(flujo)
    assert resultado is not None and resultado["result"] == "ok"
    assert limite == EVENTO["rate_limit_info"]


def test_sin_resultado_devuelve_none() -> None:
    assert leer_flujo("Error: sin sesión") == (None, None)


def test_limite_en_porcentaje_y_fecha_de_reinicio() -> None:
    lim = LimiteDeCuenta()
    assert lim.actual() is None and lim.antiguedad() == float("inf")
    lim.registrar(EVENTO["rate_limit_info"])
    a = lim.actual()
    assert a is not None
    assert a["cinco_horas"] == {"usado": 12.0, "restablece": "2026-10-07T23:10:00+00:00"}
    assert a["siete_dias"]["usado"] == 21.0
    assert not a["bloqueada"]
    assert lim.antiguedad() < 5


def test_cuenta_bloqueada() -> None:
    lim = LimiteDeCuenta()
    lim.registrar({"status": "rejected", "rateLimitType": "five_hour", "utilization": 1.0, "resetsAt": 1791414600})
    a = lim.actual()
    assert a is not None and a["bloqueada"] and a["cinco_horas"]["usado"] == 100.0

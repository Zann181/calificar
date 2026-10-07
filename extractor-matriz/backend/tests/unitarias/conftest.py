"""Las pruebas unitarias corren sin red (aceptación de F1): cualquier conexión de socket falla."""

from __future__ import annotations

import socket
from typing import Any

import pytest


class RedProhibida(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    def prohibido(*_: Any, **__: Any) -> None:
        raise RedProhibida("Las pruebas unitarias no usan red ni base de datos")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)

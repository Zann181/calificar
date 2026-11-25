"""Errores de las fuentes. Sin dependencias de infraestructura: los adaptadores traducen sus fallos a esto."""

from __future__ import annotations

from app.compartido.dominio import ErrorDeDominio


class ErrorDeFuente(ErrorDeDominio):
    """Una fuente no pudo responder. Se registra como ERROR y la búsqueda sigue con las demás."""

    def __init__(self, fuente: str, causa: str, *, estado_http: int | None = None) -> None:
        super().__init__(f"{fuente}: {causa}")
        self.fuente, self.causa, self.estado_http = fuente, causa, estado_http


class ErrorDeEstructura(ErrorDeFuente):
    """La fuente respondió, pero con una forma que ya no entendemos (el sitio cambió). Tres seguidos la desactivan sola."""

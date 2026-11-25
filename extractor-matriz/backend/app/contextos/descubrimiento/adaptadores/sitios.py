"""Catálogo de sitios con credenciales (desde `recursos/sitios_con_credenciales.json`) y estado de sus sesiones.

Fase 1: ninguna sesión se maneja todavía, así que todo sitio figura «no conectado». La captura de la sesión (Fase 5) se
añadirá como otro `EstadoDeSesiones`; el catálogo y los puertos no cambian al agregar sitios.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.contextos.descubrimiento.dominio.sitios import EstadoDeSesion, SitioConCredenciales


class CatalogoDeSitiosJson:
    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta

    def todos(self) -> list[SitioConCredenciales]:
        if not self._ruta.exists():
            return []
        datos = json.loads(self._ruta.read_text(encoding="utf-8"))
        sitios = [SitioConCredenciales.desde_dict(s) for s in datos.get("sitios", [])]
        ids = [s.id for s in sitios]
        if len(ids) != len(set(ids)):
            raise ValueError("sitios_con_credenciales.json repite un id")
        return sitios


class SesionesNoConectadas:
    """Estado de sesión de la Fase 1: todavía no se conecta ningún sitio."""

    def estado(self, sitio_id: str) -> EstadoDeSesion:
        return EstadoDeSesion.NO_CONECTADA

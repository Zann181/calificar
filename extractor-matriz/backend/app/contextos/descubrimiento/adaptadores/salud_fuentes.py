"""Salud de las fuentes que se leen sin API documentada: tras fallos de estructura seguidos se desactivan solas.

Se guarda en un archivo (`datos/estado_fuentes.json`) para que sobreviva al reinicio: una fuente rota no debe volver a molestar
(ni a ensuciar los resultados) hasta que la persona la reactive. Solo cuentan los fallos de **estructura** (el sitio cambió); un
corte de red o un 429 no desactivan nada.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

UMBRAL_DE_FALLOS = 3
log = logging.getLogger("descubrimiento")


class SaludDeFuentes:
    def __init__(self, ruta: Path | None = None, umbral: int = UMBRAL_DE_FALLOS) -> None:
        self._ruta, self._umbral = ruta, umbral
        self._cerrojo = threading.Lock()
        self._estado: dict[str, dict[str, Any]] = self._leer()

    def _leer(self) -> dict[str, dict[str, Any]]:
        if self._ruta is None or not self._ruta.exists():
            return {}
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            return {str(k): dict(v) for k, v in datos.items()}
        except (OSError, ValueError):
            log.error("No se pudo leer %s: se parte sin historial de fallos", self._ruta.name)
            return {}

    def _guardar(self) -> None:
        if self._ruta is None:
            return
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            self._ruta.write_text(json.dumps(self._estado, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            log.error("No se pudo guardar el estado de las fuentes en %s", self._ruta.name)

    def desactivada(self, fuente: str) -> str | None:
        """El motivo si la fuente está desactivada; None si está activa."""
        with self._cerrojo:
            e = self._estado.get(fuente, {})
            return str(e.get("motivo") or "desactivada") if e.get("desactivada") else None

    def exito(self, fuente: str) -> None:
        with self._cerrojo:
            if self._estado.get(fuente, {}).get("fallos"):
                self._estado[fuente] = {"fallos": 0, "desactivada": False}
                self._guardar()

    def fallo_de_estructura(self, fuente: str, motivo: str) -> bool:
        """Cuenta un fallo; True si con este la fuente quedó desactivada."""
        with self._cerrojo:
            e = self._estado.setdefault(fuente, {"fallos": 0, "desactivada": False})
            e["fallos"] = int(e.get("fallos", 0)) + 1
            e["ultimo"] = motivo[:300]
            ahora_desactivada = e["fallos"] >= self._umbral and not e.get("desactivada")
            if ahora_desactivada:
                e["desactivada"], e["motivo"] = True, f"{e['fallos']} fallos seguidos de estructura: {motivo[:200]}"
            self._guardar()
            return ahora_desactivada

    def reactivar(self, fuente: str) -> None:
        with self._cerrojo:
            self._estado[fuente] = {"fallos": 0, "desactivada": False}
            self._guardar()

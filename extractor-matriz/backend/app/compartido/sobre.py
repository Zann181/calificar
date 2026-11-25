"""Sobre de réplica (ADR 0009, sección 6.1): la unidad que viaja del equipo local a la nube.

Sin infraestructura: lo usan los adaptadores de cada contexto (que lo arman y lo aplican) y la aplicación de
Sincronización (que solo lo compara y lo mueve).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

ESQUEMA = 1  # versión del formato del sobre; la nube rechaza (426) uno mayor que el suyo

# Orden en que se aplican los sobres nuevos o cambiados (cada tipo solo apunta a los anteriores).
# Los eliminados se aplican antes y en el orden inverso.
ORDEN_DE_TIPOS = ("proyecto", "libro", "articulo", "documento", "fila", "extraccion", "base")


def json_canonico(datos: Any) -> str:
    """JSON de claves ordenadas y sin espacios: mismo contenido, mismos bytes, en cualquier motor."""
    return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def hash_de(datos: Any) -> str:
    return "sha256:" + hashlib.sha256(json_canonico(datos).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Sobre:
    tipo: str
    id: str
    proyecto_id: str
    datos: dict[str, Any] | None  # None: el agregado se eliminó (eliminado=True)
    eliminado: bool = False
    # Claves de los archivos del almacén que el agregado necesita (se publican antes que el sobre).
    archivos: tuple[str, ...] = ()

    @property
    def hash(self) -> str:
        return "" if self.eliminado else hash_de(self.datos)

    def a_json(self) -> dict[str, Any]:
        return {"esquema": ESQUEMA, "tipo": self.tipo, "id": self.id, "proyecto_id": self.proyecto_id,
                "hash": self.hash, "eliminado": self.eliminado, "datos": self.datos,
                "archivos": list(self.archivos)}

    @staticmethod
    def desde_json(d: dict[str, Any]) -> Sobre:
        return Sobre(tipo=d["tipo"], id=d["id"], proyecto_id=d["proyecto_id"], datos=d.get("datos"),
                     eliminado=bool(d.get("eliminado")), archivos=tuple(d.get("archivos") or ()))

    def tamano(self) -> int:
        return len(json_canonico(self.a_json()).encode("utf-8"))


def clave_de(tipo: str, id_: str) -> str:
    return f"{tipo}/{id_}"

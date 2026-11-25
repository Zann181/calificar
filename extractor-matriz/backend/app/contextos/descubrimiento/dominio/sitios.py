"""Sitios con credenciales: la lista abierta de lugares a los que solo se entra con la cuenta de la persona.

La Biblioteca UNAL es el primero. Agregar otro es agregar una entrada a `recursos/sitios_con_credenciales.json`
(y, si hace falta, un adaptador de búsqueda); nada de este módulo menciona a la UNAL.

Regla firme (ADR 0011): **las credenciales las escribe siempre la persona**. Aquí solo se describe el sitio y sus
límites; no hay dónde guardar usuario ni contraseña.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.compartido.dominio import ErrorDeDominio

METODOS_DE_ACCESO = ("google_institucional", "usuario_y_clave")


class EstadoDeSesion(StrEnum):
    NO_CONECTADA = "NO_CONECTADA"
    VIGENTE = "VIGENTE"
    VENCIDA = "VENCIDA"


@dataclass(frozen=True)
class LimiteDeUso:
    """Presupuesto propio, siempre por debajo del que publica el sitio (se anota cuál es en `notas`)."""

    bytes_por_ventana: int
    ventana_s: int
    pausa_min_s: float
    concurrencia: int = 1

    def __post_init__(self) -> None:
        if self.bytes_por_ventana < 1 or self.ventana_s < 1 or self.pausa_min_s < 0 or self.concurrencia < 1:
            raise ErrorDeDominio("Límite de uso inválido")


@dataclass(frozen=True)
class SitioConCredenciales:
    id: str
    nombre: str
    hosts: tuple[str, ...]  # sufijos de servidor que cuentan como este sitio: «unalproxy.elogim.com»
    portal_url: str
    acceso: tuple[str, ...]
    limite: LimiteDeUso
    bases: tuple[str, ...] = ()
    notas: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.hosts:
            raise ErrorDeDominio("Un sitio necesita id y al menos un servidor")
        malos = [m for m in self.acceso if m not in METODOS_DE_ACCESO]
        if malos:
            raise ErrorDeDominio(f"Método de acceso desconocido en «{self.id}»: {', '.join(malos)}")

    def es_de_este_sitio(self, host: str) -> bool:
        h = host.lower().rstrip(".")
        return any(h == s or h.endswith("." + s) for s in self.hosts)

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> SitioConCredenciales:
        lim = d["limite"]
        return cls(id=str(d["id"]), nombre=str(d["nombre"]), hosts=tuple(str(h).lower() for h in d["hosts"]),
                   portal_url=str(d.get("portal_url", "")), acceso=tuple(str(a) for a in d.get("acceso", [])),
                   limite=LimiteDeUso(bytes_por_ventana=int(lim["bytes_por_ventana"]), ventana_s=int(lim["ventana_s"]),
                                      pausa_min_s=float(lim["pausa_min_s"]), concurrencia=int(lim.get("concurrencia", 1))),
                   bases=tuple(str(b) for b in d.get("bases", [])), notas=str(d.get("notas", "")))

    def a_dict(self) -> dict[str, Any]:
        return {"id": self.id, "nombre": self.nombre, "hosts": list(self.hosts), "portal_url": self.portal_url,
                "acceso": list(self.acceso), "bases": list(self.bases), "notas": self.notas,
                "limite": {"bytes_por_ventana": self.limite.bytes_por_ventana, "ventana_s": self.limite.ventana_s,
                           "pausa_min_s": self.limite.pausa_min_s, "concurrencia": self.limite.concurrencia}}

"""Lector de `robots.txt` (RFC 9309): lo que un sitio nos permite leer.

El módulo `urllib.robotparser` de Python no entiende los comodines `*` y `$` en las rutas (p. ej. `Disallow: /buscar/*`
de Dialnet), así que se hace aquí lo mínimo: grupos por agente, `Allow`/`Disallow`, comodines y «gana la regla más larga».

Se usa solo para las fuentes que se leen como página o servicio sin API documentada (nivel 3 del plan). Si un sitio nos lo
prohíbe, **no se lee**: no se busca otra forma de entrar.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

AGENTE = "extractormatriz"


def _patron(regla: str) -> re.Pattern[str]:
    cuerpo = re.escape(unquote(regla)).replace(r"\*", ".*")
    if cuerpo.endswith(r"\$"):
        cuerpo = cuerpo[: -2] + "$"
    return re.compile(cuerpo)


class ReglasDeRobots:
    def __init__(self, texto: str) -> None:
        grupos: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agentes: list[str] = []
        reglas: list[tuple[bool, str]] = []
        leyendo_agentes = False
        for crudo in texto.splitlines():
            linea = crudo.split("#", 1)[0].strip()
            if ":" not in linea:
                continue
            campo, _, valor = linea.partition(":")
            campo, valor = campo.strip().lower(), valor.strip()
            if campo == "user-agent":
                if not leyendo_agentes and (agentes or reglas):
                    grupos.append((agentes, reglas))
                    agentes, reglas = [], []
                agentes.append(valor.lower())
                leyendo_agentes = True
            elif campo in ("allow", "disallow"):
                leyendo_agentes = False
                if valor:  # «Disallow:» vacío no prohíbe nada
                    reglas.append((campo == "allow", valor))
        if agentes or reglas:
            grupos.append((agentes, reglas))
        propio = [r for ags, r in grupos if AGENTE in ags]
        general = [r for ags, r in grupos if "*" in ags]
        elegido = propio or general
        self._reglas = [(permite, _patron(ruta), len(ruta)) for grupo in elegido for permite, ruta in grupo]

    def permite(self, url: str) -> bool:
        partes = urlsplit(url)
        ruta = partes.path or "/"
        if partes.query:
            ruta += "?" + partes.query
        ruta = unquote(ruta)
        mejor: tuple[int, bool] | None = None
        for permite, patron, largo in self._reglas:
            if patron.match(ruta) and (mejor is None or largo > mejor[0] or (largo == mejor[0] and permite)):
                mejor = (largo, permite)
        return True if mejor is None else mejor[1]


PERMITE_TODO = ReglasDeRobots("")
PROHIBE_TODO = ReglasDeRobots("User-agent: *\nDisallow: /")

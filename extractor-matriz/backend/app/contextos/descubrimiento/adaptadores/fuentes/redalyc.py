"""Redalyc (revistas iberoamericanas de acceso abierto): el servicio JSON que usa su propio buscador.

**Es una vía no documentada**: Redalyc no publica una API de búsqueda (su OAI-PMH no es de búsqueda). Este adaptador lee el mismo
servicio `service/r2020/getArticles/…` que alimenta su página, con estas reglas de cortesía:

- se lee `robots.txt` y se respeta (`/service/` hoy está permitido; si cambia, no se lee);
- el ritmo es el del cliente cortés (una petición a la vez, pausa mínima);
- si la forma de la respuesta cambia, el adaptador lo dice (`ErrorDeEstructura`) y tras 3 fallos seguidos **se desactiva solo**
  hasta que la persona lo reactive; no devuelve basura en silencio.

La búsqueda de Redalyc no entiende paréntesis ni OR: se hacen unas pocas consultas `"a" AND "b"` con términos de los dos primeros
conceptos y cada resultado se vuelve a evaluar en local con la cadena.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from itertools import product
from typing import Any
from urllib.parse import quote

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.adaptadores.fuentes._comun import quitar_etiquetas
from app.contextos.descubrimiento.dominio.busqueda import ConsultaDeBusqueda, plano
from app.contextos.descubrimiento.dominio.candidato import Autor, RegistroBibliografico
from app.contextos.descubrimiento.dominio.errores import ErrorDeEstructura

BASE = "https://www.redalyc.org/service/r2020/getArticles/"
ARTICULO = "https://www.redalyc.org/articulo.oa?id="
PDF = "https://www.redalyc.org/journal/{revista}/{articulo}/{articulo}.pdf"
MAX_PARES = 8
POR_PAGINA = 25
IDIOMAS = {"español": "es", "inglés": "en", "portugués": "pt"}
_ESPANOL = re.compile(r"felicid|bienestar|eudaimon|desempe|rendimiento|productiv|trabajador|empleado|funcionari|laboral")


def _primero_en_espanol(terminos: tuple[str, ...]) -> list[str]:
    """Redalyc es sobre todo en español: sus términos van antes (y los de otros idiomas, después)."""
    return sorted((t.rstrip("*") for t in terminos), key=lambda t: 0 if _ESPANOL.search(plano(t)) else 1)


def consultas_de(consulta: ConsultaDeBusqueda) -> list[str]:
    conceptos = consulta.obligatorios[:2]
    if len(conceptos) < 2:
        return [f'"{t}"' for t in _primero_en_espanol(conceptos[0].terminos)[:MAX_PARES]]
    a, b = (_primero_en_espanol(c.terminos)[:4] for c in conceptos)
    return [f'"{x}" AND "{y}"' for x, y in product(a, b)][:MAX_PARES]


def _autores(r: dict[str, Any]) -> tuple[Autor, ...]:
    """`apellidoNombre` viene como « Erazo Muñoz, Pablo Andrés>>> Riaño Casallas, Martha Isabel>>>»."""
    partes = [p.strip() for p in str(r.get("apellidoNombre") or "").split(">>>") if p.strip()]
    autores = []
    for p in partes:
        apellido, _, nombre = p.partition(",")
        autores.append(Autor(nombre=f"{nombre.strip()} {apellido.strip()}".strip(), apellido=apellido.strip()))
    if not autores:  # sin ese campo: «Nombre Apellido, Nombre Apellido»
        autores = [Autor(nombre=n.strip(), apellido=n.strip().split()[-1]) for n in str(r.get("autores") or "").split(",")
                   if n.strip()]
    return tuple(autores)


def _resumen(r: dict[str, Any]) -> str:
    """`es: …>>>en: …`: se conserva el texto de todos los idiomas, sin las etiquetas «es:»/«en:»."""
    partes = [re.sub(r"^\s*[a-z]{2}\s*:\s*", "", p) for p in str(r.get("resumen") or "").split(">>>")]
    return quitar_etiquetas(" ".join(p for p in partes if p.strip()))


def _palabras(r: dict[str, Any]) -> tuple[str, ...]:
    vistas: list[str] = []
    for bloque in str(r.get("palabras") or "").split(">>>"):
        for k in bloque.replace(".", "").split(","):
            if k.strip() and k.strip() not in vistas:
                vistas.append(k.strip())
    return tuple(vistas)


class Redalyc:
    nombre = "redalyc"
    etiqueta = "Redalyc"
    sitio_id: str | None = None
    autodesactivable = True  # vía no documentada: si cambia de forma, se apaga sola

    def __init__(self, cliente: ClienteCortes) -> None:
        self._cliente = cliente

    def buscar(self, consulta: ConsultaDeBusqueda, limite: int, hoy: date) -> Iterator[RegistroBibliografico]:
        f = consulta.filtros
        locales = ConsultaDeBusqueda(conceptos=consulta.obligatorios[:2], filtros=f)
        consultas = consultas_de(consulta)
        por_consulta = max(10, limite // max(1, len(consultas)) + 10)
        vistos: set[str] = set()
        entregados = 0
        for q in consultas:
            pagina, leidos = 1, 0
            while leidos < por_consulta:
                url = f"{BASE}{quote(q, safe='')}/{pagina}/{POR_PAGINA}/1/default/"
                # Su servicio responde 406 si se pide solo «application/json» (contesta text/plain): se pide lo mismo que su página.
                datos = self._cliente.get_json(self.nombre, url, robots=True, accept="application/json, text/plain, */*")
                if not isinstance(datos, dict) or "resultados" not in datos or "totalResultados" not in datos:
                    raise ErrorDeEstructura(self.nombre, "la respuesta ya no trae «resultados» y «totalResultados»: el sitio cambió")
                resultados = datos["resultados"] or []
                for r in resultados:
                    leidos += 1
                    registro = self._registro(r, entregados + 1)
                    clave = str(r["cveArticulo"])
                    if clave in vistos or not f.desde <= (registro.anio or f.desde) <= f.hasta_efectivo(hoy):
                        continue
                    if not locales.coincide(f"{registro.titulo} {registro.resumen} {' '.join(registro.palabras_clave)}"):
                        continue
                    vistos.add(clave)
                    entregados += 1
                    yield registro
                    if entregados >= limite:
                        return
                if len(resultados) < POR_PAGINA:
                    break
                pagina += 1

    def _registro(self, r: dict[str, Any], posicion: int) -> RegistroBibliografico:
        if not isinstance(r, dict) or not r.get("titulo") or not r.get("cveArticulo"):
            raise ErrorDeEstructura(self.nombre, "un resultado ya no trae título ni clave de artículo: el sitio cambió")
        doi = str(r.get("doiTitulo") or "").strip() or None
        try:
            anio = int(str(r.get("anioArticulo") or "")[:4])
        except ValueError:
            anio = None
        pdf = PDF.format(revista=r.get("cveRevista"), articulo=r["cveArticulo"])  # todo Redalyc es de acceso abierto
        return RegistroBibliografico(
            fuente=self.nombre, id_externo=str(r["cveArticulo"]), posicion=posicion,
            titulo=quitar_etiquetas(str(r["titulo"])), doi=doi, autores=_autores(r), anio=anio,
            revista=str(r.get("nomRevista") or ""), resumen=_resumen(r), palabras_clave=_palabras(r),
            idioma=IDIOMAS.get(str(r.get("idiomaArticulo") or "").lower(), ""), tipo="article",
            url_oa=pdf, es_preprint=False, pdfs=(pdf,))

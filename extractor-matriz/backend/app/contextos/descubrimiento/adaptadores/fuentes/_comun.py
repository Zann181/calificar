"""Utilidades compartidas por los adaptadores de fuentes. Sin red y sin modelos: texto y diccionarios."""

from __future__ import annotations

import html
import re
from typing import Any

IDIOMA_ISO = {"eng": "en", "spa": "es", "por": "pt", "fre": "fr", "ger": "de", "ita": "it"}
IDIOMA_LARGO = {"en": "eng", "es": "spa", "pt": "por"}


_EN_LINEA = re.compile(r"</?(?:i|b|em|strong|sub|sup|u|span|italic|bold|jats:italic|jats:bold|jats:sub|jats:sup)(?=[\s/>])[^<>]*>", re.I)
_ETIQUETA = re.compile(r"</?[A-Za-z][^<>]*>")


def quitar_etiquetas(texto: str | None) -> str:
    """Resúmenes y títulos que llegan con HTML o JATS, a veces escapado (`&lt;i&gt;`): deja solo el texto.

    Primero se desescapa; las etiquetas «en línea» (cursiva, subíndice…) se quitan sin dejar espacio y las de bloque
    (`<p>`, `<h4>`, `<br>`) se vuelven un espacio. Solo se tocan etiquetas de verdad: un «p < .001 … p > .05» de
    estadística no se debe borrar.
    """
    if not texto:
        return ""
    sin = _ETIQUETA.sub(" ", _EN_LINEA.sub("", html.unescape(texto)))
    return re.sub(r"\s+", " ", sin).strip()


def apellido_de(nombre_completo: str) -> str:
    partes = nombre_completo.replace(",", " ").split()
    return partes[-1] if partes else ""


def entero_o_none(valor: Any) -> int | None:
    try:
        return int(str(valor)[:4])
    except (TypeError, ValueError):
        return None

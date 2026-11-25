"""Cómo se consigue el PDF de un candidato: solo copias abiertas y legales (ADR 0011).

Orden: la dirección de acceso abierto que ya trae la fuente → lo que Unpaywall conoce para ese DOI (solo si hay correo de
contacto configurado: Unpaywall lo exige). Si la dirección lleva a una página en lugar del PDF, se lee la etiqueta
`citation_pdf_url` que casi todas las revistas y repositorios ponen para los gestores bibliográficos (un solo salto).

No pasa por el proxy de la Biblioteca ni usa credenciales: eso es la Fase 5. Una descarga a la vez, con el ritmo del cliente.
"""

from __future__ import annotations

import logging
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes
from app.contextos.descubrimiento.dominio.candidato import normalizar_doi
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente

log = logging.getLogger("descubrimiento")
FUENTE = "descarga"
UNPAYWALL = "https://api.unpaywall.org/v2/"
MAX_URLS = 3


class ObtenerPdfAbierto:
    def __init__(self, cliente: ClienteCortes, *, contacto: str = "", max_bytes: int = 60_000_000) -> None:
        self._cliente, self._contacto, self._max_bytes = cliente, contacto.strip(), max_bytes

    def urls(self, doi: str | None, url_oa: str | None) -> list[str]:
        """Direcciones donde probar, de la más a la menos prometedora, sin repetir."""
        halladas: list[str] = [url_oa] if url_oa else []
        d = normalizar_doi(doi)
        if d and self._contacto:
            try:
                datos = self._cliente.get_json("unpaywall", UNPAYWALL + quote(d, safe="/"), {"email": self._contacto})
                lugares = [datos.get("best_oa_location") or {}, *(datos.get("oa_locations") or [])]
                halladas += [u for lugar in lugares for u in (lugar.get("url_for_pdf"), lugar.get("url")) if u]
            except ErrorDeFuente as e:  # Unpaywall caído o sin ese DOI: se sigue con lo que ya había
                log.error("Unpaywall: no se pudo consultar (%s)", e.causa)
        vistas: list[str] = []
        for u in halladas:
            if u not in vistas:
                vistas.append(u)
        return vistas[:MAX_URLS]

    def descargar(self, url: str) -> bytes:
        d = self._cliente.get_bytes(FUENTE, url, max_bytes=self._max_bytes)
        if d.datos.startswith(b"%PDF"):
            return d.datos
        if "html" in d.tipo:
            siguiente = self._pdf_de_la_pagina(d.datos, d.url_final)
            if siguiente and siguiente != url:
                d2 = self._cliente.get_bytes(FUENTE, siguiente, max_bytes=self._max_bytes)
                if d2.datos.startswith(b"%PDF"):
                    return d2.datos
        raise ErrorDeFuente(FUENTE, "la dirección no entrega un PDF (es una página web o pide iniciar sesión)")

    @staticmethod
    def _pdf_de_la_pagina(html: bytes, base: str) -> str | None:
        sopa = BeautifulSoup(html, "lxml")
        meta = sopa.find("meta", attrs={"name": "citation_pdf_url"})
        contenido = meta.get("content") if meta is not None else None
        return urljoin(base, str(contenido)) if contenido else None

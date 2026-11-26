"""Importar candidatos al flujo existente (plan «Buscar», Fase 3).

Importar = conseguir el PDF abierto de cada candidato y entregarlo a Biblioteca (`CargarPDF`): el artículo aparece en
«Nuevo» del panel de Artículos. **No convierte ni extrae nada** (la extracción cuesta ~2,6 USD y ~4 min por artículo y se
pide aparte) y **no escribe en la matriz**. Solo copias abiertas; una descarga a la vez; hasta 10 por pedido.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.compartido.dominio import ErrorDeDominio
from app.contextos.descubrimiento.dominio.candidato import Candidato, EstadoCandidato
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.contextos.descubrimiento.puertos import CargadorDeArticulos, ObtenerPdf, RepositorioDeCandidatos

log = logging.getLogger("descubrimiento")
MAX_POR_PEDIDO = 10
SIN_COPIA = ("No hay copia abierta: abra el artículo en su sitio (o por la Biblioteca) y suba el PDF a mano desde el "
             "panel de Artículos")


class EstadoImportacion(StrEnum):
    IMPORTADO = "IMPORTADO"
    YA_ESTABA = "YA_ESTABA"
    SIN_COPIA_ABIERTA = "SIN_COPIA_ABIERTA"
    RECHAZADO = "RECHAZADO"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ResultadoDeImportacion:
    candidato_id: uuid.UUID
    titulo: str
    estado: EstadoImportacion
    mensaje: str
    articulo_id: uuid.UUID | None = None


def nombre_de_archivo(c: Candidato) -> str:
    """`Perez_2023_happiness-and-job-performance.pdf`: legible y sin caracteres raros."""
    def limpio(t: str) -> str:
        sin = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
        return re.sub(r"[^A-Za-z0-9]+", "-", sin).strip("-")
    apellido = limpio(c.autores[0].apellido) if c.autores else "sin-autor"
    return f"{apellido or 'sin-autor'}_{c.anio or 's-f'}_{limpio(c.titulo)[:60] or 'sin-titulo'}.pdf"


class ImportarCandidatos:
    def __init__(self, candidatos: RepositorioDeCandidatos, obtener: ObtenerPdf, cargador: CargadorDeArticulos) -> None:
        self._candidatos, self._obtener, self._cargador = candidatos, obtener, cargador

    def ejecutar(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID]) -> list[ResultadoDeImportacion]:
        if not ids:
            raise ErrorDeDominio("No hay candidatos seleccionados")
        if len(set(ids)) > MAX_POR_PEDIDO:
            raise ErrorDeDominio(f"Se importan hasta {MAX_POR_PEDIDO} a la vez: una descarga por decisión, sin «bajar todo»")
        por_id = {c.id: c for c in self._candidatos.por_ids(proyecto_id, ids)}
        resultados: list[ResultadoDeImportacion] = []
        for cid in dict.fromkeys(ids):
            c = por_id.get(cid)
            resultados.append(self._uno(proyecto_id, cid, c) if c else ResultadoDeImportacion(
                cid, "", EstadoImportacion.ERROR, "No existe en este proyecto"))
        return resultados

    def _uno(self, proyecto_id: uuid.UUID, cid: uuid.UUID, c: Candidato) -> ResultadoDeImportacion:
        def r(estado: EstadoImportacion, mensaje: str, articulo: uuid.UUID | None = None) -> ResultadoDeImportacion:
            return ResultadoDeImportacion(cid, c.titulo, estado, mensaje, articulo)

        if c.estado == EstadoCandidato.IMPORTADO:
            return r(EstadoImportacion.YA_ESTABA, "Ya se había importado", c.articulo_id)
        if c.estado == EstadoCandidato.DESCARTADO:
            return r(EstadoImportacion.RECHAZADO, "Está descartado: reactívelo antes de importarlo")
        urls = self._obtener.urls(c.doi, c.url_pdf or c.url_oa)
        if not urls:
            return r(EstadoImportacion.SIN_COPIA_ABIERTA, SIN_COPIA)
        ultimo = "no se pudo descargar"
        datos: bytes | None = None
        for url in urls:
            try:
                datos = self._obtener.descargar(url)
                break
            except ErrorDeFuente as e:
                ultimo = e.causa
        if datos is None:
            log.error("Importar «%s»: no se pudo conseguir el PDF (%s)", c.titulo[:80], ultimo)
            return r(EstadoImportacion.ERROR, f"No se pudo descargar el PDF: {ultimo}")
        carga = self._cargador.cargar(proyecto_id, nombre_de_archivo(c), datos)
        if carga.error or carga.articulo_id is None:
            log.error("Importar «%s»: la Biblioteca rechazó el archivo (%s)", c.titulo[:80], carga.error)
            return r(EstadoImportacion.ERROR, carga.error or "La Biblioteca no aceptó el archivo")
        c.marcar_importado(carga.articulo_id)
        self._candidatos.guardar(c)
        if carga.duplicado:
            log.info("Importar «%s»: el PDF ya estaba en la biblioteca (%s)", c.titulo[:80], carga.duplicado_de)
            return r(EstadoImportacion.YA_ESTABA, f"El PDF ya estaba en la biblioteca ({carga.duplicado_de})",
                     carga.articulo_id)
        log.info("Importar «%s»: PDF cargado (%d KB); queda en «Nuevo»", c.titulo[:80], len(datos) // 1024)
        return r(EstadoImportacion.IMPORTADO, "PDF cargado: está en «Nuevo» en Artículos. No se extrajo nada.",
                 carga.articulo_id)

"""Etapa B: leer el texto completo de un PDF abierto y buscar en él los datos de la matriz (plan, 2.6).

Para cada candidato consigue el PDF (el ya importado a Biblioteca, o una copia abierta), extrae su texto, corre los mismos
detectores deterministas sobre métodos y resultados y guarda **solo los indicios con su página** (nunca el texto ni el
archivo). No importa el artículo, no extrae con el modelo, no escribe en la matriz. Hasta 10 por pedido.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.compartido.dominio import ErrorDeDominio, ahora
from app.contextos.descubrimiento.aplicacion.importar import MAX_POR_PEDIDO, SIN_COPIA
from app.contextos.descubrimiento.dominio.candidato import Candidato
from app.contextos.descubrimiento.dominio.completitud import AnalisisDeTexto
from app.contextos.descubrimiento.dominio.detectores import MotorDeDetectores
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.contextos.descubrimiento.puertos import (
    ExtraerTexto,
    ObtenerPdf,
    PdfsDeBiblioteca,
    RepositorioDeAnalisis,
    RepositorioDeCandidatos,
)

log = logging.getLogger("descubrimiento")


class EstadoAnalisis(StrEnum):
    ANALIZADO = "ANALIZADO"
    TEXTO_INSUFICIENTE = "TEXTO_INSUFICIENTE"
    SIN_COPIA_ABIERTA = "SIN_COPIA_ABIERTA"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ResultadoDeAnalisis:
    candidato_id: uuid.UUID
    titulo: str
    estado: EstadoAnalisis
    mensaje: str
    con_indicio: int = 0


class AnalizarTextoCompleto:
    def __init__(self, candidatos: RepositorioDeCandidatos, obtener: ObtenerPdf, pdfs: PdfsDeBiblioteca,
                 extraer: ExtraerTexto, analisis: RepositorioDeAnalisis, motor: MotorDeDetectores) -> None:
        self._candidatos, self._obtener, self._pdfs = candidatos, obtener, pdfs
        self._extraer, self._analisis, self._motor = extraer, analisis, motor

    def ejecutar(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID]) -> list[ResultadoDeAnalisis]:
        if not ids:
            raise ErrorDeDominio("No hay candidatos seleccionados")
        if len(set(ids)) > MAX_POR_PEDIDO:
            raise ErrorDeDominio(f"Se analizan hasta {MAX_POR_PEDIDO} a la vez: una descarga por decisión, sin «bajar todo»")
        por_id = {c.id: c for c in self._candidatos.por_ids(proyecto_id, ids)}
        return [self._uno(proyecto_id, por_id[i]) if i in por_id else
                ResultadoDeAnalisis(i, "", EstadoAnalisis.ERROR, "No existe en este proyecto")
                for i in dict.fromkeys(ids)]

    def _pdf(self, proyecto_id: uuid.UUID, c: Candidato) -> tuple[bytes, str] | str:
        """(bytes, de dónde salió) o un mensaje de por qué no se pudo."""
        if c.articulo_id is not None:
            datos = self._pdfs.leer(proyecto_id, c.articulo_id)
            if datos:
                return datos, "PDF ya importado a Artículos"
        urls = self._obtener.urls(c.doi, c.url_pdf or c.url_oa)
        if not urls:
            return SIN_COPIA
        ultimo = "no se pudo descargar"
        for url in urls:
            try:
                return self._obtener.descargar(url), "copia abierta"
            except ErrorDeFuente as e:
                ultimo = e.causa
        log.error("Analizar «%s»: no se pudo conseguir el PDF (%s)", c.titulo[:80], ultimo)
        return f"No se pudo descargar el PDF: {ultimo}"

    def _uno(self, proyecto_id: uuid.UUID, c: Candidato) -> ResultadoDeAnalisis:
        def r(estado: EstadoAnalisis, mensaje: str, n: int = 0) -> ResultadoDeAnalisis:
            return ResultadoDeAnalisis(c.id, c.titulo, estado, mensaje, n)

        obtenido = self._pdf(proyecto_id, c)
        if isinstance(obtenido, str):
            sin = obtenido == SIN_COPIA
            return r(EstadoAnalisis.SIN_COPIA_ABIERTA if sin else EstadoAnalisis.ERROR, obtenido)
        datos, origen = obtenido
        try:
            paginas = self._extraer.paginas(datos)
        except ErrorDeDominio as e:
            log.error("Analizar «%s»: el PDF no se pudo leer (%s)", c.titulo[:80], e)
            return r(EstadoAnalisis.ERROR, f"El PDF no se pudo leer: {e}")
        resultado = self._motor.analizar_texto(c, paginas)
        self._analisis.guardar(AnalisisDeTexto(
            candidato_id=c.id, celdas=resultado.celdas, intentadas=resultado.intentadas, paginas=resultado.paginas,
            caracteres=resultado.caracteres, suficiente=resultado.suficiente, origen=origen, analizado_en=ahora()))
        n = len(resultado.celdas)
        if not resultado.suficiente:
            log.error("Analizar «%s»: casi no hay texto en el PDF (%d caracteres): ¿está escaneado?", c.titulo[:80],
                      resultado.caracteres)
            return r(EstadoAnalisis.TEXTO_INSUFICIENTE,
                     f"El PDF ({origen}) casi no tiene texto (¿escaneado?): se guardó lo poco hallado, pero no se afirma "
                     "que algo falte", n)
        log.info("Analizar «%s»: %d páginas, indicio en %d de %d columnas", c.titulo[:80], resultado.paginas, n,
                 len(resultado.intentadas))
        return r(EstadoAnalisis.ANALIZADO, f"{resultado.paginas} páginas leídas ({origen}): indicio en {n} columnas", n)

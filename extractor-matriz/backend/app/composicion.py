"""Raíz de composición: arma casos de uso con sus adaptadores y conecta contextos por eventos.

Es el único módulo que conoce a todos los contextos. Los puentes entre contextos
(ConsultaDeColumnas, FuenteDeMatriz) llaman a casos de uso del otro contexto: ningún contexto
lee tablas ajenas.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.db import RegistroProyecto, crear_motor, fabrica_de_sesiones
from app.compartido.dominio import ErrorDeDominio
from app.compartido.outbox import Despachador
from app.config import Settings
from app.contextos.biblioteca.adaptadores.almacen import AlmacenEnDisco, AlmacenS3
from app.contextos.biblioteca.adaptadores.mineru import MineruHttp, _grilla
from app.contextos.biblioteca.adaptadores.repositorio_sql import UnidadDeTrabajoBibliotecaSql
from app.contextos.biblioteca.aplicacion.casos_de_uso import (
    AvanzarExtraccion,
    CargarPDF,
    CasosDeBiblioteca,
    ConsultasDeBiblioteca,
    ConvertirArticulo,
    ExcluirArticulo,
    ReactivarArticulo,
    ReintentarArticulo,
)
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.biblioteca.puertos import AlmacenDeArchivos, ConversorPDF
from app.contextos.exportacion.adaptadores.escritores import EscritorHeredadasOpenpyxl, ScriptEscritor
from app.contextos.exportacion.aplicacion.casos_de_uso import ExportarMatriz
from app.contextos.exportacion.puertos import FilaExportable, MatrizBase
from app.contextos.extraccion.adaptadores.claude_cli import ClaudeCli
from app.contextos.extraccion.adaptadores.pdf import LectorPyMuPdf
from app.contextos.extraccion.adaptadores.repositorio_sql import UnidadDeTrabajoExtraccionSql
from app.contextos.extraccion.adaptadores.validador import ScriptValidador
from app.contextos.extraccion.aplicacion.casos_de_uso import (
    CasosDeExtraccion,
    ConsultasDeExtraccion,
    ExtraerArticulo,
    ParametrosDelMotor,
)
from app.contextos.extraccion.aplicacion.ejecutor import (
    CONVIRTIENDO,
    ESPERANDO_MINERU,
    EjecutorDeExtracciones,
    PedidoDeExtraccion,
)
from app.contextos.extraccion.dominio.extraccion import Extraccion, Hallazgo
from app.contextos.extraccion.puertos import ArticuloParaExtraer, LibroVigente, ModeloDeLenguaje
from app.contextos.matriz.adaptadores.lector_excel import LectorExcel
from app.contextos.matriz.adaptadores.repositorio_sql import UnidadDeTrabajoMatrizSql
from app.contextos.matriz.aplicacion.casos_de_uso import (
    CasosDeMatriz,
    ConsultasDeMatriz,
    EscribirFilasDeExtraccion,
    EscribirFilasExtraidas,
    FilasDeExtraccion,
    ImportarMatriz,
    MarcarVersionDeFilas,
    RevisarCelda,
)
from app.contextos.normas.adaptadores.repositorio_sql import UnidadDeTrabajoNormasSql
from app.contextos.normas.aplicacion.casos_de_uso import CasosDeNormas, ConsultasDeNormas, PublicarLibro

log = logging.getLogger("composicion")


class ColumnasDesdeNormas:
    """Implementa matriz.puertos.ConsultaDeColumnas con el caso de uso de Normas."""

    def __init__(self, normas: ConsultasDeNormas) -> None:
        self._normas = normas

    def columnas(self, proyecto_id: uuid.UUID) -> list[Any]:
        return self._normas.columnas(proyecto_id)

    def version_activa_id(self, proyecto_id: uuid.UUID) -> uuid.UUID:
        return self._normas.libro_activo(proyecto_id).id


class FuenteDesdeContextos:
    """Implementa exportacion.puertos.FuenteDeMatriz con consultas de Matriz y Normas."""

    def __init__(self, matriz: ConsultasDeMatriz, normas: ConsultasDeNormas, almacen: AlmacenDeArchivos) -> None:
        self._matriz, self._normas, self._almacen = matriz, normas, almacen

    def columnas(self, proyecto_id: uuid.UUID) -> list[Any]:
        return self._normas.columnas(proyecto_id)

    def libro(self, proyecto_id: uuid.UUID) -> dict[str, Any]:
        return self._normas.libro_activo(proyecto_id).contenido

    def base(self, proyecto_id: uuid.UUID) -> MatrizBase:
        base = self._matriz.base(proyecto_id)
        if base is None:
            raise LookupError("Primero importe la matriz vigente: la exportación parte de ese Excel")
        return MatrizBase(datos=self._almacen.leer(base.clave_almacen), hoja=base.hoja)

    def filas(self, proyecto_id: uuid.UUID) -> list[FilaExportable]:
        return [
            FilaExportable(
                estudio=f.estudio, origen=f.origen.value, valores=f.valores(),
                notas_heredadas=f.trazabilidad.get("notas_heredadas", {}),
                fila_excel_origen=f.trazabilidad.get("fila_excel_origen"),
                salida=f.trazabilidad.get("salida"), auditoria=f.trazabilidad.get("auditoria", []),
            )
            for f in self._matriz.todas(proyecto_id)
        ]


class ArticulosDesdeBiblioteca:
    """Implementa extraccion.puertos.FuenteDeArticulos con los casos de uso de Biblioteca."""

    def __init__(self, biblioteca: CasosDeBiblioteca) -> None:
        self._b = biblioteca

    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> ArticuloParaExtraer:
        articulo = self._b.consultas.articulo(proyecto_id, articulo_id)
        documento = self._b.consultas.documento(proyecto_id, articulo_id).a_dict()
        for b in documento["bloques"]:
            if b.get("tabla") and not b["tabla"]["es_imagen"]:
                b["tabla"]["filas_grilla"] = [" ".join(f) for f in _grilla(b["tabla"]["html"])]
        return ArticuloParaExtraer(articulo_id=articulo.id, nombre_archivo=articulo.nombre_archivo,
                                   pdf=self._b.almacen.leer(articulo.clave_almacen), documento=documento)

    def iniciar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, *, confirmar_reextraccion: bool,
                motivo: str | None) -> None:
        self._b.extraccion.iniciar(proyecto_id, articulo_id, confirmar_reextraccion=confirmar_reextraccion,
                                   motivo=motivo)

    def pasar_a_auditoria(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> None:
        self._b.extraccion.auditar(proyecto_id, articulo_id)

    def fallar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, paso: str, mensaje: str) -> None:
        self._b.extraccion.fallar(proyecto_id, articulo_id, EstadoArticulo(paso), mensaje)


class NormasParaExtraccion:
    def __init__(self, normas: ConsultasDeNormas) -> None:
        self._normas = normas

    def libro_activo(self, proyecto_id: uuid.UUID) -> LibroVigente:
        v = self._normas.libro_activo(proyecto_id)
        return LibroVigente(id=v.id, contenido=v.contenido)


class NumeracionDesdeMatriz:
    def __init__(self, matriz: ConsultasDeMatriz) -> None:
        self._matriz = matriz

    def siguiente(self, proyecto_id: uuid.UUID) -> int:
        return self._matriz.siguiente_estudio(proyecto_id)


AUDITOR_EN_EXCEL = {"AUDITOR_EVIDENCIA": "Auditor de evidencia", "CODIFICADOR_CIEGO": "Codificador ciego",
                    "CONCILIADOR": "Conciliador"}


def hallazgo_para_excel(h: Hallazgo) -> dict[str, Any]:
    """Formato de la hoja Auditoria de escribir_matriz.py."""
    return {"estudio": h.estudio, "columna": h.columna, "auditor": AUDITOR_EN_EXCEL[h.auditor.value],
            "veredicto": h.veredicto.value.replace("_", " "), "hallazgo": h.detalle,
            "evidencia": h.evidencia_propuesta, "resolucion": h.resolucion,
            "estado": "Resuelto" if h.estado.value == "RESUELTO" else "Pendiente"}


def filas_de_extraccion(ext: Extraccion, umbral_acuerdo: float) -> FilasDeExtraccion:
    """Copia la salida con el ancla de cada evidencia, para que Matriz arme las celdas."""
    salida = copy.deepcopy(ext.salida)
    por_estudio = {int(f["fila"]["Estudio"]): f for f in salida}
    for a in ext.anclas:
        item = por_estudio.get(a.estudio) or {}
        evidencias = ((item.get("trazabilidad") or {}).get("evidencia") or {}).get(a.columna) or []
        if a.indice_evidencia < len(evidencias) and isinstance(evidencias[a.indice_evidencia], dict):
            evidencias[a.indice_evidencia]["ancla"] = a.a_dict()
    extra: dict[str, Any] = {"extraccion_id": str(ext.id), "acuerdo_campos_criticos": ext.acuerdo_campos_criticos,
                             "avisos_validador": ext.avisos_validador}
    acuerdo = ext.acuerdo_campos_criticos
    if acuerdo is not None and acuerdo < umbral_acuerdo:
        extra["aviso_acuerdo"] = (f"Acuerdo extractor-codificador ciego de {acuerdo:.2f} en campos críticos, "
                                  f"menor que {umbral_acuerdo:.2f}")
    return FilasDeExtraccion(articulo_id=ext.articulo_id, version_libro_id=ext.version_libro_id, salida=salida,
                             auditoria=[hallazgo_para_excel(h) for h in ext.hallazgos], trazabilidad_extra=extra)


@dataclass
class Contenedor:
    ajustes: Settings
    fabrica: Callable[[], Session]
    almacen: AlmacenDeArchivos
    biblioteca: CasosDeBiblioteca
    normas: CasosDeNormas
    matriz: CasosDeMatriz
    extraccion: CasosDeExtraccion
    exportar: ExportarMatriz
    despachador: Despachador
    # None si MinerU no responde; si responde, su /salud ({} para conversores sin servicio, como el de pruebas).
    ejecutor: EjecutorDeExtracciones
    mineru: Callable[[], dict[str, Any] | None]
    convertir_nuevos: Callable[[], int]


def construir(ajustes: Settings, *, fabrica: Callable[[], Session] | None = None,
              almacen: AlmacenDeArchivos | None = None, conversor: ConversorPDF | None = None,
              modelo: ModeloDeLenguaje | None = None) -> Contenedor:
    if fabrica is None:
        fabrica = fabrica_de_sesiones(crear_motor(ajustes.database_url))
    if almacen is None and ajustes.almacen_dir is not None:
        almacen = AlmacenEnDisco(ajustes.almacen_dir)
    if almacen is None:
        s3 = AlmacenS3(endpoint=ajustes.s3_endpoint, bucket=ajustes.s3_bucket, access_key=ajustes.s3_access_key,
                       secret_key=ajustes.s3_secret_key, endpoint_publico=ajustes.s3_endpoint_publico)
        s3.asegurar_bucket()
        almacen = s3
    if conversor is None:
        conversor = MineruHttp(ajustes.mineru_url, ajustes.mineru_tiempo_max)
    if modelo is None:
        modelo = ClaudeCli({"extractor": ajustes.modelo_extractor, "auditor": ajustes.modelo_auditor,
                            "ciego": ajustes.modelo_ciego, "conciliador": ajustes.modelo_conciliador},
                           ajustes.claude_cli)

    def udt_bib() -> UnidadDeTrabajoBibliotecaSql:
        return UnidadDeTrabajoBibliotecaSql(fabrica)

    def udt_nor() -> UnidadDeTrabajoNormasSql:
        return UnidadDeTrabajoNormasSql(fabrica)

    def udt_mat() -> UnidadDeTrabajoMatrizSql:
        return UnidadDeTrabajoMatrizSql(fabrica)

    def udt_ext() -> UnidadDeTrabajoExtraccionSql:
        return UnidadDeTrabajoExtraccionSql(fabrica)

    biblioteca = CasosDeBiblioteca(
        cargar=CargarPDF(udt_bib, almacen), convertir=ConvertirArticulo(udt_bib, almacen, conversor),
        excluir=ExcluirArticulo(udt_bib), reactivar=ReactivarArticulo(udt_bib),
        reintentar=ReintentarArticulo(udt_bib), consultas=ConsultasDeBiblioteca(udt_bib), almacen=almacen,
        extraccion=AvanzarExtraccion(udt_bib),
    )
    consultas_normas = ConsultasDeNormas(udt_nor)
    normas = CasosDeNormas(publicar=PublicarLibro(udt_nor), consultas=consultas_normas)
    consultas_matriz = ConsultasDeMatriz(udt_mat)
    columnas_de_normas = ColumnasDesdeNormas(consultas_normas)
    matriz = CasosDeMatriz(
        importar=ImportarMatriz(udt_mat, columnas_de_normas, LectorExcel(), almacen),
        consultas=consultas_matriz, marcar_version=MarcarVersionDeFilas(udt_mat),
        escribir_extraidas=EscribirFilasExtraidas(udt_mat), revisar=RevisarCelda(udt_mat, columnas_de_normas),
        escribir_extraccion=EscribirFilasDeExtraccion(udt_mat, columnas_de_normas),
    )
    extraccion = CasosDeExtraccion(
        extraer=ExtraerArticulo(
            udt_ext, ArticulosDesdeBiblioteca(biblioteca), NormasParaExtraccion(consultas_normas),
            NumeracionDesdeMatriz(consultas_matriz), modelo,
            ScriptValidador(ajustes.recursos_dir / "validar_extraccion.py", pdftotext=ajustes.pdftotext), LectorPyMuPdf(),
            ParametrosDelMotor(max_iteraciones_validador=ajustes.max_iteraciones_validador,
                               umbral_similitud=ajustes.umbral_similitud,
                               concurrencia=ajustes.concurrencia_extraccion)),
        consultas=ConsultasDeExtraccion(udt_ext),
    )
    exportar = ExportarMatriz(
        FuenteDesdeContextos(consultas_matriz, consultas_normas, almacen), EscritorHeredadasOpenpyxl(),
        ScriptEscritor(ajustes.recursos_dir / "escribir_matriz.py"), almacen,
    )

    despachador = Despachador(fabrica)

    def preparar_extraccion(pedido: PedidoDeExtraccion, informar: Callable[[str], None]) -> None:
        """«Extraer» sobre un PDF sin convertir lo convierte primero con MinerU; si MinerU está apagado, espera."""
        limite = time.monotonic() + ajustes.espera_conversion_max
        reintentada = False  # un PDF que falló al convertirse se reintenta una vez; si vuelve a fallar, se informa
        while True:
            with candado_conversion:
                articulo = biblioteca.consultas.articulo(pedido.proyecto_id, pedido.articulo_id)
                estado = articulo.estado
                if (estado == EstadoArticulo.ERROR and not reintentada and articulo.error is not None
                        and articulo.error.paso == EstadoArticulo.CONVIRTIENDO):
                    biblioteca.reintentar.ejecutar(pedido.proyecto_id, pedido.articulo_id)
                    reintentada, estado = True, EstadoArticulo.NUEVO
                if estado == EstadoArticulo.NUEVO and mineru() is not None:
                    informar(CONVIRTIENDO)
                    estado = biblioteca.convertir.ejecutar(pedido.proyecto_id, pedido.articulo_id)
            if estado == EstadoArticulo.ERROR:
                articulo = biblioteca.consultas.articulo(pedido.proyecto_id, pedido.articulo_id)
                if articulo.error is not None and articulo.error.paso == EstadoArticulo.CONVIRTIENDO:
                    raise ErrorDeDominio(f"«{pedido.nombre}»: la conversión falló; no se puede extraer (ver el registro)")
                return  # el error fue al extraer: ExtraerArticulo retoma la extracción desde ese paso
            if estado not in (EstadoArticulo.NUEVO, EstadoArticulo.CONVIRTIENDO):
                return
            if time.monotonic() > limite:
                raise ErrorDeDominio(f"«{pedido.nombre}»: no se convirtió a tiempo (¿MinerU apagado?)")
            informar(ESPERANDO_MINERU if estado == EstadoArticulo.NUEVO else CONVIRTIENDO)
            time.sleep(3)

    ejecutor = EjecutorDeExtracciones(extraccion.extraer, ajustes.extracciones_en_paralelo, preparar_extraccion)

    def mineru() -> dict[str, Any] | None:
        salud = getattr(conversor, "salud", None)
        if salud is None:
            return {}
        try:
            return dict(salud())
        except Exception:
            return None

    candado_conversion = threading.Lock()  # una conversión a la vez, venga del barrido o de un pedido de extraer

    def convertir_nuevos() -> int:
        """Convierte los artículos que siguen en Nuevo, si MinerU responde. Devuelve cuántos intentó."""
        with fabrica() as s:
            proyectos = [p.id for p in s.scalars(select(RegistroProyecto)).all()]
        pendientes = [(pid, a) for pid in proyectos
                      for a in biblioteca.consultas.listar(pid, EstadoArticulo.NUEVO).articulos]
        if not pendientes or mineru() is None:
            return 0
        hechos = 0
        for pid, a in pendientes:
            with candado_conversion:
                if biblioteca.consultas.articulo(pid, a.id).estado == EstadoArticulo.NUEVO:  # otro pudo ganarle
                    biblioteca.convertir.ejecutar(pid, a.id)
                    hechos += 1
        return hechos

    def al_cargar_articulo(datos: dict[str, Any]) -> None:
        # F1: la conversión corre en el despachador. En F3 la toma Orquestación (Trabajo + Dramatiq).
        pid, aid = uuid.UUID(datos["proyecto_id"]), uuid.UUID(datos["articulo_id"])
        if not ajustes.convertir_al_cargar:
            log.info("Artículo %s: cargado; queda en Nuevo hasta que se pulse su estado para convertir y extraer",
                     str(aid)[:8])
            return
        if biblioteca.consultas.articulo(pid, aid).estado == EstadoArticulo.NUEVO:
            if mineru() is None:
                log.warning("Artículo %s: MinerU no responde en %s; queda en Nuevo y se convertirá solo cuando "
                            "MinerU responda", str(aid)[:8], ajustes.mineru_url)
                return
            log.info("Artículo %s: el despachador inicia su conversión", str(aid)[:8])
            estado = biblioteca.convertir.ejecutar(pid, aid)
            log.info("Artículo %s convertido: %s", aid, estado)

    def al_publicar_libro(datos: dict[str, Any]) -> None:
        matriz.marcar_version.ejecutar(uuid.UUID(datos["proyecto_id"]), uuid.UUID(datos["version_libro_id"]))

    def al_completar_extraccion(datos: dict[str, Any]) -> None:
        # Sección 8.3, paso 9: Matriz escribe las filas y el artículo queda POR_REVISAR.
        pid, aid = uuid.UUID(datos["proyecto_id"]), uuid.UUID(datos["articulo_id"])
        ext = extraccion.consultas.obtener(pid, uuid.UUID(datos["extraccion_id"]))
        filas = matriz.escribir_extraccion.ejecutar(pid, filas_de_extraccion(ext, ajustes.umbral_acuerdo))
        biblioteca.extraccion.completar(pid, aid)
        log.info("Extracción %s: %d filas escritas", ext.id, len(filas))

    despachador.suscribir("ArticuloCargado", al_cargar_articulo)
    despachador.suscribir("LibroPublicado", al_publicar_libro)
    despachador.suscribir("ExtraccionCompletada", al_completar_extraccion)

    return Contenedor(ajustes=ajustes, fabrica=fabrica, almacen=almacen, biblioteca=biblioteca, normas=normas,
                      matriz=matriz, extraccion=extraccion, exportar=exportar,
                      despachador=despachador, ejecutor=ejecutor, mineru=mineru,
                      convertir_nuevos=convertir_nuevos)

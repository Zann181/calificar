"""Casos de uso de Biblioteca: CargarPDF, ConvertirArticulo, ExcluirArticulo, ReactivarArticulo."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.compartido.dominio import ErrorDeDominio
from app.contextos.biblioteca.dominio.articulo import Articulo, EstadoArticulo
from app.contextos.biblioteca.dominio.documento import DocumentoEstructurado
from app.contextos.biblioteca.puertos import (
    AlmacenDeArchivos,
    ConversorPDF,
    HuellaDuplicada,
    UnidadDeTrabajoBiblioteca,
)

FabricaUdT = Callable[[], UnidadDeTrabajoBiblioteca]


def huella(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


@dataclass(frozen=True)
class ResultadoCarga:
    nombre_archivo: str
    articulo_id: uuid.UUID | None
    duplicado: bool
    duplicado_de: str | None = None
    error: str | None = None


log = logging.getLogger("biblioteca")


class CargarPDF:
    def __init__(self, udt: FabricaUdT, almacen: AlmacenDeArchivos) -> None:
        self._udt, self._almacen = udt, almacen

    def ejecutar(self, proyecto_id: uuid.UUID, nombre_archivo: str, datos: bytes) -> ResultadoCarga:
        if not datos.startswith(b"%PDF"):
            log.warning("%s: rechazado, no es un PDF", nombre_archivo)
            return ResultadoCarga(nombre_archivo, None, False, error="El archivo no es un PDF")
        sha = huella(datos)
        with self._udt() as u:
            existente = u.articulos.por_huella(proyecto_id, sha)
            if existente is not None:
                log.warning("%s: duplicado de «%s» (misma huella SHA-256), no se carga", nombre_archivo,
                            existente.nombre_archivo)
                return ResultadoCarga(nombre_archivo, existente.id, True, duplicado_de=existente.nombre_archivo)
            clave = f"pdf/{proyecto_id}/{sha}.pdf"
            self._almacen.guardar(clave, datos, "application/pdf")
            articulo = Articulo.cargar(proyecto_id=proyecto_id, nombre_archivo=nombre_archivo,
                                       huella_sha256=sha, clave_almacen=clave)
            try:
                u.articulos.agregar(articulo)
                u.confirmar()
            except HuellaDuplicada:
                u.revertir()
                return ResultadoCarga(nombre_archivo, None, True)
        log.info("%s: cargado (%d KB, huella %s…). Estado: Nuevo; se convierte y extrae al pulsar «Nuevo»", nombre_archivo,
                 len(datos) // 1024, sha[:10])
        return ResultadoCarga(nombre_archivo, articulo.id, False)


class ConvertirArticulo:
    """NUEVO → CONVIRTIENDO → LISTO, o ERROR con el paso y el mensaje."""

    def __init__(self, udt: FabricaUdT, almacen: AlmacenDeArchivos, conversor: ConversorPDF) -> None:
        self._udt, self._almacen, self._conversor = udt, almacen, conversor

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> EstadoArticulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            if articulo.estado != EstadoArticulo.CONVIRTIENDO:
                articulo.iniciar_conversion()
            u.confirmar()
        log.info("%s: convirtiendo con MinerU (en CPU toma entre 11 y 21 s por página)", articulo.nombre_archivo)
        inicio = time.perf_counter()
        try:
            pdf = self._almacen.leer(articulo.clave_almacen)
            conversion = self._conversor.convertir(pdf, articulo.nombre_archivo)
            self._almacen.guardar(f"crudo/{articulo_id}.zip", conversion.crudo, "application/zip")
        except Exception as e:
            with self._udt() as u:
                articulo = u.articulos.obtener(proyecto_id, articulo_id)
                articulo.fallar(EstadoArticulo.CONVIRTIENDO, f"{type(e).__name__}: {e}")
                u.confirmar()
            log.error("%s: la conversión falló. %s: %s", articulo.nombre_archivo, type(e).__name__, e)
            return EstadoArticulo.ERROR
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            documento_id = u.documentos.guardar(proyecto_id, articulo_id, conversion.documento)
            articulo.completar_conversion(documento_estructurado_id=documento_id,
                                          paginas=len(conversion.documento.paginas))
            u.confirmar()
        log.info("%s: convertido en %.0f s · %d páginas · %d bloques. Estado: %s", articulo.nombre_archivo,
                 time.perf_counter() - inicio, len(conversion.documento.paginas), len(conversion.documento.bloques),
                 articulo.estado.value)
        return articulo.estado


class ExcluirArticulo:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, motivo: str) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            articulo.excluir(motivo)
            u.confirmar()
        return articulo


class ReactivarArticulo:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            articulo.reactivar()
            u.confirmar()
        return articulo


class ReintentarArticulo:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            articulo.reintentar()
            u.confirmar()
        return articulo


class AvanzarExtraccion:
    """Estados del artículo durante una extracción (sección 5.1):
    EN_COLA → EXTRAYENDO → AUDITANDO → POR_REVISAR, o ERROR con el paso que falló.

    Cada método es idempotente respecto del estado de destino: un reintento desde ERROR deja el artículo
    en el paso que falló y la extracción sigue desde ahí.
    """

    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def iniciar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, *, confirmar_reextraccion: bool = False,
                motivo: str | None = None) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            if articulo.estado not in (EstadoArticulo.EN_COLA, EstadoArticulo.EXTRAYENDO, EstadoArticulo.AUDITANDO):
                articulo.encolar(confirmar_reextraccion=confirmar_reextraccion, motivo=motivo)
            if articulo.estado == EstadoArticulo.EN_COLA:
                articulo.transicionar(EstadoArticulo.EXTRAYENDO)
            u.articulos.agregar(articulo)
            u.confirmar()
        return articulo

    def _pasar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, desde: EstadoArticulo,
               hacia: EstadoArticulo) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            if articulo.estado == desde:
                articulo.transicionar(hacia)
            elif articulo.estado != hacia:
                raise ErrorDeDominio(f"El artículo está en {articulo.estado}, no en {desde}")
            u.articulos.agregar(articulo)
            u.confirmar()
        return articulo

    def auditar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        return self._pasar(proyecto_id, articulo_id, EstadoArticulo.EXTRAYENDO, EstadoArticulo.AUDITANDO)

    def completar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        return self._pasar(proyecto_id, articulo_id, EstadoArticulo.AUDITANDO, EstadoArticulo.POR_REVISAR)

    def fallar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, paso: EstadoArticulo, mensaje: str) -> Articulo:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            articulo.fallar(paso, mensaje)
            u.articulos.agregar(articulo)
            u.confirmar()
        return articulo


@dataclass(frozen=True)
class Listado:
    articulos: list[Articulo]
    contadores: dict[str, int]


class ConsultasDeBiblioteca:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def listar(self, proyecto_id: uuid.UUID, estado: EstadoArticulo | None = None) -> Listado:
        with self._udt() as u:
            return Listado(u.articulos.listar(proyecto_id, estado), u.articulos.contar_por_estado(proyecto_id))

    def articulo(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        with self._udt() as u:
            return u.articulos.obtener(proyecto_id, articulo_id)

    def documento(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> DocumentoEstructurado:
        with self._udt() as u:
            articulo = u.articulos.obtener(proyecto_id, articulo_id)
            if articulo.documento_estructurado_id is None:
                raise ErrorDeDominio("El artículo aún no tiene documento estructurado")
            return u.documentos.obtener(proyecto_id, articulo.documento_estructurado_id)


@dataclass
class CasosDeBiblioteca:
    """Lo que la API de Biblioteca necesita; lo arma app.composicion."""

    cargar: CargarPDF
    convertir: ConvertirArticulo
    excluir: ExcluirArticulo
    reactivar: ReactivarArticulo
    reintentar: ReintentarArticulo
    consultas: ConsultasDeBiblioteca
    almacen: AlmacenDeArchivos
    extraccion: AvanzarExtraccion

"""Agregado Articulo y su máquina de estados (sección 5.1 de la especificación)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.compartido.dominio import Entidad, ErrorDeDominio, ahora
from app.contextos.biblioteca.eventos import (
    ArticuloCargado,
    ArticuloConvertido,
    ArticuloExcluido,
    ConversionFallida,
    EstadoDeArticuloCambiado,
)


class EstadoArticulo(StrEnum):
    HEREDADO = "HEREDADO"
    NUEVO = "NUEVO"
    CONVIRTIENDO = "CONVIRTIENDO"
    LISTO = "LISTO"
    EN_COLA = "EN_COLA"
    EXTRAYENDO = "EXTRAYENDO"
    AUDITANDO = "AUDITANDO"
    POR_REVISAR = "POR_REVISAR"
    APROBADO = "APROBADO"
    ERROR = "ERROR"
    EXCLUIDO = "EXCLUIDO"


E = EstadoArticulo

# Transiciones permitidas, y ninguna otra. ERROR y EXCLUIDO se tratan aparte (ver abajo).
TRANSICIONES: dict[EstadoArticulo, frozenset[EstadoArticulo]] = {
    E.NUEVO: frozenset({E.CONVIRTIENDO}),
    E.CONVIRTIENDO: frozenset({E.LISTO}),
    E.LISTO: frozenset({E.EN_COLA}),
    E.EN_COLA: frozenset({E.EXTRAYENDO, E.LISTO, E.HEREDADO}),
    E.EXTRAYENDO: frozenset({E.AUDITANDO}),
    E.AUDITANDO: frozenset({E.POR_REVISAR}),
    E.POR_REVISAR: frozenset({E.APROBADO, E.EN_COLA}),
    E.APROBADO: frozenset({E.EN_COLA}),
    E.HEREDADO: frozenset({E.EN_COLA}),
    E.ERROR: frozenset(),
    E.EXCLUIDO: frozenset({E.NUEVO, E.HEREDADO}),
}
EXCLUIBLES = frozenset({E.NUEVO, E.LISTO, E.HEREDADO, E.ERROR})
EXTRAIBLES = frozenset({E.LISTO, E.HEREDADO, E.ERROR, E.POR_REVISAR})


class TransicionInvalida(ErrorDeDominio):
    def __init__(self, desde: EstadoArticulo, hacia: EstadoArticulo) -> None:
        super().__init__(f"Transición inválida: {desde} → {hacia}")
        self.desde, self.hacia = desde, hacia


@dataclass(frozen=True)
class DetalleError:
    paso: EstadoArticulo
    mensaje: str
    fecha: datetime


@dataclass(kw_only=True, eq=False)
class Articulo(Entidad):
    nombre_archivo: str
    huella_sha256: str
    clave_almacen: str
    estado: EstadoArticulo = E.NUEVO
    paginas: int | None = None
    documento_estructurado_id: uuid.UUID | None = None
    error: DetalleError | None = None
    excluido_motivo: str | None = None
    # Estado desde el que se entró a EN_COLA o EXCLUIDO; decide a dónde vuelve al cancelar o reactivar.
    estado_anterior: EstadoArticulo | None = None

    @classmethod
    def cargar(cls, *, proyecto_id: uuid.UUID, nombre_archivo: str, huella_sha256: str,
               clave_almacen: str) -> Articulo:
        if len(huella_sha256) != 64:
            raise ErrorDeDominio("La huella debe ser SHA-256 en hexadecimal")
        a = cls(proyecto_id=proyecto_id, nombre_archivo=nombre_archivo, huella_sha256=huella_sha256,
                clave_almacen=clave_almacen)
        a.registrar(ArticuloCargado(proyecto_id=proyecto_id, articulo_id=a.id,
                                    nombre_archivo=nombre_archivo, huella_sha256=huella_sha256))
        return a

    # --- núcleo de la máquina de estados ---
    def _pasar(self, nuevo: EstadoArticulo) -> None:
        anterior = self.estado
        self.estado = nuevo
        self.registrar(EstadoDeArticuloCambiado(proyecto_id=self.proyecto_id, articulo_id=self.id,
                                                anterior=anterior.value, nuevo=nuevo.value))

    def transicionar(self, nuevo: EstadoArticulo) -> None:
        if nuevo == E.ERROR:
            raise ErrorDeDominio("Para pasar a ERROR use fallar(paso, mensaje)")
        if nuevo == E.EXCLUIDO:
            raise ErrorDeDominio("Para excluir use excluir(motivo)")
        if nuevo not in TRANSICIONES[self.estado]:
            raise TransicionInvalida(self.estado, nuevo)
        if nuevo == E.EN_COLA:
            self.estado_anterior = self.estado
        self._pasar(nuevo)

    # --- conversión ---
    def iniciar_conversion(self) -> None:
        self.transicionar(E.CONVIRTIENDO)

    def completar_conversion(self, *, documento_estructurado_id: uuid.UUID, paginas: int) -> None:
        if paginas < 1:
            raise ErrorDeDominio("Un documento convertido tiene al menos una página")
        self.transicionar(E.LISTO)
        self.documento_estructurado_id = documento_estructurado_id
        self.paginas = paginas
        self.error = None
        self.registrar(ArticuloConvertido(proyecto_id=self.proyecto_id, articulo_id=self.id,
                                          documento_estructurado_id=documento_estructurado_id, paginas=paginas))

    # --- error y reintento ---
    def fallar(self, paso: EstadoArticulo, mensaje: str) -> None:
        if self.estado == E.EXCLUIDO:
            raise TransicionInvalida(self.estado, E.ERROR)
        self.error = DetalleError(paso=paso, mensaje=mensaje[:2000], fecha=ahora())
        self._pasar(E.ERROR)
        if paso == E.CONVIRTIENDO:
            self.registrar(ConversionFallida(proyecto_id=self.proyecto_id, articulo_id=self.id, mensaje=mensaje[:500]))

    def reintentar(self) -> None:
        if self.estado != E.ERROR or self.error is None:
            raise TransicionInvalida(self.estado, self.error.paso if self.error else E.NUEVO)
        self._pasar(self.error.paso)

    # --- cola de extracción ---
    def encolar(self, *, confirmar_reextraccion: bool = False, motivo: str | None = None) -> None:
        if self.estado not in EXTRAIBLES and self.estado != E.APROBADO:
            raise TransicionInvalida(self.estado, E.EN_COLA)
        if self.documento_estructurado_id is None:
            raise ErrorDeDominio("El artículo no tiene documento estructurado: conviértalo antes de extraer")
        if self.estado in (E.POR_REVISAR, E.APROBADO) and not confirmar_reextraccion:
            raise ErrorDeDominio("Reextraer exige confirmación")
        if self.estado == E.APROBADO and not (motivo and motivo.strip()):
            raise ErrorDeDominio("Reextraer un artículo aprobado exige motivo")
        if self.estado == E.ERROR:
            # ERROR → estado del paso que falló: la extracción se retoma desde ese paso.
            if self.error is None or self.error.paso not in (E.EN_COLA, E.EXTRAYENDO, E.AUDITANDO):
                raise ErrorDeDominio("El error no ocurrió al extraer: use reintentar()")
            self.reintentar()
            return
        self.transicionar(E.EN_COLA)

    def cancelar(self) -> None:
        if self.estado != E.EN_COLA:
            raise TransicionInvalida(self.estado, E.LISTO)
        self.transicionar(E.HEREDADO if self.estado_anterior == E.HEREDADO else E.LISTO)

    # --- exclusión ---
    def excluir(self, motivo: str) -> None:
        if not motivo or not motivo.strip():
            raise ErrorDeDominio("Excluir exige motivo")
        if self.estado not in EXCLUIBLES:
            raise TransicionInvalida(self.estado, E.EXCLUIDO)
        self.estado_anterior = self.estado
        self.excluido_motivo = motivo.strip()
        self._pasar(E.EXCLUIDO)
        self.registrar(ArticuloExcluido(proyecto_id=self.proyecto_id, articulo_id=self.id, motivo=self.excluido_motivo))

    def reactivar(self) -> None:
        if self.estado != E.EXCLUIDO:
            raise TransicionInvalida(self.estado, E.NUEVO)
        destino = E.HEREDADO if self.estado_anterior == E.HEREDADO else E.NUEVO
        self.excluido_motivo = None
        self.transicionar(destino)

"""Lógica pura de la sincronización: qué falta en la nube y cómo agruparlo (ADR 0009, secciones 6.1 y 6.2)."""

from __future__ import annotations

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from app.compartido.sobre import ORDEN_DE_TIPOS, Sobre, clave_de

LOTE_MAXIMO_BYTES = 1_000_000


class ErrorDeSincronizacion(Exception):
    """Falla al hablar con la nube. `reintentable` es True si conviene volver a intentar sola (red, nube dormida)."""

    def __init__(self, mensaje: str, *, codigo: int | None = None, reintentable: bool = False) -> None:
        super().__init__(mensaje)
        self.codigo, self.reintentable = codigo, reintentable


class ConflictoDeInstalacion(Exception):
    """Otro equipo ya sincroniza esta nube (HTTP 409). «Reenviar todo» toma el control."""


@dataclass(frozen=True)
class Opciones:
    """Qué se sube (sección 7, punto 2). Todo activado por defecto."""

    pdf: bool = True
    documento: bool = True
    matriz: bool = True
    historial: bool = True
    extraccion: bool = True
    crudo: bool = True
    excel: bool = True

    def a_dict(self) -> dict[str, bool]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @staticmethod
    def desde_dict(d: dict[str, Any] | None) -> Opciones:
        base = Opciones()
        return replace(base, **{k: bool(v) for k, v in (d or {}).items() if k in base.__dataclass_fields__})

    def tipos(self) -> set[str]:
        """Tipos de sobre que se replican con estas opciones."""
        activos = {"proyecto", "libro", "articulo"}
        if self.documento:
            activos.add("documento")
        if self.matriz:
            activos |= {"fila", "base"}
        if self.extraccion:
            activos.add("extraccion")
        return activos

    def permite_archivo(self, clave: str) -> bool:
        raiz = clave.split("/", 1)[0]
        return {"pdf": self.pdf, "crudo": self.crudo, "matrices": self.excel}.get(raiz, True)


@dataclass(frozen=True)
class Manifiesto:
    revision: int
    items: dict[str, str]  # «tipo/id» → hash del sobre
    archivos: dict[str, str]  # clave del almacén → SHA-256


@dataclass
class Plan:
    archivos: list[str] = field(default_factory=list)  # claves por subir
    eliminar: list[Sobre] = field(default_factory=list)
    subir: list[Sobre] = field(default_factory=list)

    @property
    def pendientes(self) -> int:
        return len(self.archivos) + len(self.eliminar) + len(self.subir)

    @property
    def vacio(self) -> bool:
        return self.pendientes == 0


def filtrar(sobres: Iterable[Sobre], opciones: Opciones) -> list[Sobre]:
    """Aplica «qué se sube»: quita los tipos apagados, los archivos apagados y, sin historial, el de cada celda."""
    tipos = opciones.tipos()
    salida: list[Sobre] = []
    for s in sobres:
        if s.tipo not in tipos:
            continue
        datos = s.datos
        if s.tipo == "fila" and not opciones.historial and datos is not None:
            datos = {**datos, "celdas": [{**c, "historial": []} for c in datos["celdas"]]}
        archivos = tuple(a for a in s.archivos if opciones.permite_archivo(a))
        salida.append(replace(s, datos=datos, archivos=archivos))
    salida.sort(key=lambda s: (ORDEN_DE_TIPOS.index(s.tipo) if s.tipo in ORDEN_DE_TIPOS else len(ORDEN_DE_TIPOS), s.id))
    return salida


def calcular_plan(local: list[Sobre], archivos_locales: dict[str, str], nube: Manifiesto, opciones: Opciones,
                  proyecto_id: str) -> Plan:
    """Compara lo local con el manifiesto de la nube. No usa ninguna tabla de «lo enviado»: la nube es la referencia."""
    plan = Plan()
    tipos = opciones.tipos()
    vistos: set[str] = set()
    for s in local:
        k = clave_de(s.tipo, s.id)
        vistos.add(k)
        if nube.items.get(k) != s.hash:
            plan.subir.append(s)
    # Lo que la nube tiene y el equipo ya no: se elimina (solo de los tipos que se replican).
    orden = {t: i for i, t in enumerate(ORDEN_DE_TIPOS)}
    for k in nube.items:
        tipo, _, id_ = k.partition("/")
        if tipo in tipos and k not in vistos:
            plan.eliminar.append(Sobre(tipo, id_, proyecto_id, None, eliminado=True))
    plan.eliminar.sort(key=lambda s: -orden.get(s.tipo, 0))
    # Archivos que los sobres por subir necesitan y la nube no tiene (o tiene distintos).
    necesarios: list[str] = []
    for s in plan.subir:
        for a in s.archivos:
            if a in archivos_locales and nube.archivos.get(a) != archivos_locales[a] and a not in necesarios:
                necesarios.append(a)
    # También los archivos de sobres iguales cuyo archivo falte en la nube (nube restaurada a medias).
    for s in local:
        for a in s.archivos:
            if a in archivos_locales and nube.archivos.get(a) != archivos_locales[a] and a not in necesarios:
                necesarios.append(a)
    plan.archivos = necesarios
    return plan


def en_lotes(sobres: list[Sobre], maximo: int = LOTE_MAXIMO_BYTES) -> list[list[Sobre]]:
    """Agrupa sobres consecutivos en lotes de hasta `maximo` bytes (uno más grande viaja solo)."""
    lotes: list[list[Sobre]] = []
    actual: list[Sobre] = []
    peso = 0
    for s in sobres:
        t = s.tamano()
        if actual and peso + t > maximo:
            lotes.append(actual)
            actual, peso = [], 0
        actual.append(s)
        peso += t
    if actual:
        lotes.append(actual)
    return lotes


def tipo_de_contenido(clave: str) -> str:
    return {".pdf": "application/pdf", ".zip": "application/zip",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}.get(
        posixpath.splitext(clave)[1].lower(), "application/octet-stream")

"""Agregado FilaDeEfecto y entidad Celda (sección 5.4 de la especificación).

Invariantes (cubiertas por tests/unitarias/test_matriz.py):
1. No se aprueba una celda NO_VERIFICABLE ni POR_CONFIRMAR sin motivo. Por la regla central
   ("un dato sin ubicación comprobable no entra como verificado") lo mismo vale para SIN_EVIDENCIA.
2. Corregir exige motivo y deja el valor anterior en el historial.
3. Una fila pasa a aprobada solo si todas sus celdas numéricas están APROBADA o CORREGIDA.
4. Estudio único por proyecto: restricción única en la base de datos y reserva atómica.
5. El valor de una columna con valores_permitidos pertenece a esa lista.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.compartido.columnas import CODIGOS_FALTANTE, DefinicionDeColumna
from app.compartido.dominio import Entidad, ErrorDeDominio, ahora
from app.contextos.matriz.eventos import (
    CeldaAprobada,
    CeldaCorregida,
    CeldaRechazada,
    FilaAprobada,
    FilaEscrita,
)

Json = Any
_OTRO = re.compile(r"^Otro: \S.*$")


class Origen(StrEnum):
    HEREDADA = "HEREDADA"
    EXTRAIDA = "EXTRAIDA"


class TipoValor(StrEnum):
    LITERAL = "LITERAL"
    CODIFICADO = "CODIFICADO"
    INFERIDO = "INFERIDO"
    FALTANTE = "FALTANTE"


class EstadoRevision(StrEnum):
    SIN_EVIDENCIA = "SIN_EVIDENCIA"
    PENDIENTE = "PENDIENTE"
    POR_CONFIRMAR = "POR_CONFIRMAR"
    NO_VERIFICABLE = "NO_VERIFICABLE"
    APROBADA = "APROBADA"
    CORREGIDA = "CORREGIDA"
    RECHAZADA = "RECHAZADA"


EXIGEN_MOTIVO_AL_APROBAR = frozenset(
    {EstadoRevision.NO_VERIFICABLE, EstadoRevision.POR_CONFIRMAR, EstadoRevision.SIN_EVIDENCIA}
)
REVISADAS = frozenset({EstadoRevision.APROBADA, EstadoRevision.CORREGIDA})

# Niveles de ancla de la sección 8.4, del más alto al más bajo. La celda toma el más bajo.
NIVELES_ANCLA = ("VERIFICADA", "VERIFICADA_CON_CORRECCION", "POR_CONFIRMAR", "NO_VERIFICABLE")
ESTADO_POR_NIVEL = {
    "VERIFICADA": EstadoRevision.PENDIENTE,
    "VERIFICADA_CON_CORRECCION": EstadoRevision.PENDIENTE,
    "POR_CONFIRMAR": EstadoRevision.POR_CONFIRMAR,
    "NO_VERIFICABLE": EstadoRevision.NO_VERIFICABLE,
}


def valor_permitido(definicion: DefinicionDeColumna, valor: Json) -> bool:
    """Invariante 5. null siempre se admite aquí; la obligatoriedad la controla el validador."""
    if valor is None or not definicion.valores_permitidos:
        return True
    if not isinstance(valor, str):
        return False
    permitidos = set(definicion.valores_permitidos)
    admite_otro = any(p.startswith("Otro:") for p in permitidos)
    partes = valor.split("; ") if definicion.tipo_de_dato == "categoría múltiple" else [valor]
    return all(p in permitidos or (admite_otro and _OTRO.match(p) is not None) for p in partes)


@dataclass(frozen=True)
class Evidencia:
    pagina_pdf: int
    ubicacion: str
    cita_textual: str
    leido_de_figura: bool = False
    fila_tabla: str | None = None
    columna_tabla: str | None = None
    bloque_id: str | None = None
    ancla: dict[str, Any] | None = None  # copia del Ancla de Extracción (nivel, rect, rango, similitud)


@dataclass(frozen=True)
class Inferencia:
    regla: str
    razonamiento: str
    premisas: tuple[str, ...] = ()


@dataclass(frozen=True)
class CambioDeCelda:
    autor: str
    fecha: datetime
    accion: str
    valor_anterior: Json
    valor_nuevo: Json
    motivo: str | None


@dataclass(kw_only=True)
class Celda:
    clave: str
    valor: Json = None
    estado_dato: str | None = None
    tipo_valor: TipoValor | None = None  # None: fila heredada, el tipo no se conoce
    evidencias: list[Evidencia] = field(default_factory=list)
    inferencia: Inferencia | None = None
    estado_revision: EstadoRevision = EstadoRevision.SIN_EVIDENCIA
    historial: list[CambioDeCelda] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.estado_dato is not None and self.estado_dato not in CODIGOS_FALTANTE:
            raise ErrorDeDominio(f"estado_dato inválido en '{self.clave}': {self.estado_dato}")

    @property
    def nivel_ancla(self) -> str | None:
        """El nivel más bajo entre las anclas de sus evidencias (sección 8.4); None si no hay anclas."""
        niveles = [e.ancla["nivel"] for e in self.evidencias if e.ancla and e.ancla.get("nivel") in NIVELES_ANCLA]
        return max(niveles, key=NIVELES_ANCLA.index) if niveles else None

    @classmethod
    def extraida(cls, *, clave: str, valor: Json, estado_dato: str | None, tipo_valor: TipoValor,
                 evidencias: list[Evidencia], inferencia: Inferencia | None = None) -> Celda:
        """Celda escrita por la extracción: su estado de revisión inicial sale del ancla más baja."""
        celda = cls(clave=clave, valor=valor, estado_dato=estado_dato, tipo_valor=tipo_valor,
                    evidencias=list(evidencias), inferencia=inferencia)
        nivel = celda.nivel_ancla
        celda.estado_revision = ESTADO_POR_NIVEL[nivel] if nivel else EstadoRevision.PENDIENTE
        return celda

    def _anotar(self, autor: str, accion: str, anterior: Json, nuevo: Json, motivo: str | None) -> None:
        if not autor:
            raise ErrorDeDominio("Toda acción de revisión exige autor")
        self.historial.append(CambioDeCelda(autor=autor, fecha=ahora(), accion=accion,
                                            valor_anterior=anterior, valor_nuevo=nuevo, motivo=motivo))

    def aprobar(self, *, autor: str, motivo: str | None = None) -> None:
        motivo = (motivo or "").strip() or None
        if self.estado_revision in EXIGEN_MOTIVO_AL_APROBAR and motivo is None:
            raise ErrorDeDominio(f"Aprobar una celda {self.estado_revision} exige motivo")
        self._anotar(autor, "APROBAR", self.valor, self.valor, motivo)
        self.estado_revision = EstadoRevision.APROBADA

    def corregir(self, *, autor: str, valor: Json, motivo: str, definicion: DefinicionDeColumna,
                 estado_dato: str | None = None) -> None:
        motivo = (motivo or "").strip()
        if not motivo:
            raise ErrorDeDominio("Corregir exige motivo")
        if not valor_permitido(definicion, valor):
            raise ErrorDeDominio(f"'{valor}' no está entre los valores permitidos de '{self.clave}'")
        if estado_dato is not None and estado_dato not in CODIGOS_FALTANTE:
            raise ErrorDeDominio(f"estado_dato inválido: {estado_dato}")
        self._anotar(autor, "CORREGIR", self.valor, valor, motivo)
        self.valor = valor
        self.estado_dato = estado_dato if valor is None else None
        self.estado_revision = EstadoRevision.CORREGIDA

    def rechazar(self, *, autor: str, motivo: str) -> None:
        motivo = (motivo or "").strip()
        if not motivo:
            raise ErrorDeDominio("Rechazar exige motivo")
        self._anotar(autor, "RECHAZAR", self.valor, self.valor, motivo)
        self.estado_revision = EstadoRevision.RECHAZADA


@dataclass(kw_only=True, eq=False)
class FilaDeEfecto(Entidad):
    estudio: int
    documento: int
    origen: Origen
    version_libro_id: uuid.UUID | None
    articulo_id: uuid.UUID | None = None
    version_desactualizada: bool = False
    aprobada: bool = False
    celdas: dict[str, Celda] = field(default_factory=dict)
    trazabilidad: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.estudio < 1 or self.documento < 1:
            raise ErrorDeDominio("Estudio y Documento son enteros positivos")

    @classmethod
    def importar_heredada(cls, *, proyecto_id: uuid.UUID, estudio: int, documento: int,
                          valores: dict[str, Json], version_libro_id: uuid.UUID | None,
                          notas_heredadas: dict[str, dict[str, str | None]] | None = None,
                          fila_excel: int | None = None) -> FilaDeEfecto:
        """Fila de la matriz vigente. Los valores se guardan tal cual (sin depurar vocabulario):
        la importación y la exportación deben coincidir celda por celda."""
        celdas = {
            clave: Celda(clave=clave, valor=valor,
                         tipo_valor=TipoValor.FALTANTE if valor is None else None,
                         estado_revision=EstadoRevision.SIN_EVIDENCIA)
            for clave, valor in valores.items()
        }
        trazabilidad: dict[str, Any] = {"notas_heredadas": notas_heredadas or {}}
        if fila_excel is not None:
            trazabilidad["fila_excel_origen"] = fila_excel
        fila = cls(proyecto_id=proyecto_id, estudio=estudio, documento=documento, origen=Origen.HEREDADA,
                   version_libro_id=version_libro_id, celdas=celdas, trazabilidad=trazabilidad)
        fila.registrar(FilaEscrita(proyecto_id=proyecto_id, fila_id=fila.id, estudio=estudio,
                                   origen=Origen.HEREDADA.value))
        return fila

    @classmethod
    def extraida(cls, *, proyecto_id: uuid.UUID, estudio: int, documento: int, articulo_id: uuid.UUID,
                 version_libro_id: uuid.UUID, celdas: dict[str, Celda],
                 trazabilidad: dict[str, Any]) -> FilaDeEfecto:
        """Fila escrita por una extracción (sección 8.3, paso 9): queda pendiente de revisión."""
        fila = cls(proyecto_id=proyecto_id, estudio=estudio, documento=documento, origen=Origen.EXTRAIDA,
                   version_libro_id=version_libro_id, articulo_id=articulo_id, celdas=dict(celdas),
                   trazabilidad=dict(trazabilidad))
        fila.registrar(FilaEscrita(proyecto_id=proyecto_id, fila_id=fila.id, estudio=estudio,
                                   origen=Origen.EXTRAIDA.value))
        return fila

    def celda(self, clave: str) -> Celda:
        try:
            return self.celdas[clave]
        except KeyError as e:
            raise ErrorDeDominio(f"La fila {self.estudio} no tiene la columna '{clave}'") from e

    # --- revisión ---
    def aprobar_celda(self, clave: str, *, autor: str, motivo: str | None = None) -> None:
        self.celda(clave).aprobar(autor=autor, motivo=motivo)
        self.registrar(CeldaAprobada(proyecto_id=self.proyecto_id, fila_id=self.id, estudio=self.estudio,
                                     clave=clave, autor=autor))

    def corregir_celda(self, clave: str, *, autor: str, valor: Json, motivo: str,
                       definicion: DefinicionDeColumna, estado_dato: str | None = None) -> None:
        if definicion.clave != clave:
            raise ErrorDeDominio("La definición no corresponde a la columna")
        self.celda(clave).corregir(autor=autor, valor=valor, motivo=motivo, definicion=definicion,
                                   estado_dato=estado_dato)
        self.aprobada = False
        self.registrar(CeldaCorregida(proyecto_id=self.proyecto_id, fila_id=self.id, estudio=self.estudio,
                                      clave=clave, autor=autor, motivo=motivo))

    def rechazar_celda(self, clave: str, *, autor: str, motivo: str) -> None:
        self.celda(clave).rechazar(autor=autor, motivo=motivo)
        self.aprobada = False
        self.registrar(CeldaRechazada(proyecto_id=self.proyecto_id, fila_id=self.id, estudio=self.estudio,
                                      clave=clave, autor=autor, motivo=motivo))

    def aprobar(self, *, autor: str, columnas: list[DefinicionDeColumna]) -> None:
        pendientes = [c.clave for c in columnas
                      if c.es_numerica and self.celda(c.clave).estado_revision not in REVISADAS]
        if pendientes:
            raise ErrorDeDominio("No se puede aprobar la fila: celdas numéricas sin revisar: " + ", ".join(pendientes))
        self.aprobada = True
        self.registrar(FilaAprobada(proyecto_id=self.proyecto_id, fila_id=self.id, estudio=self.estudio, autor=autor))

    # --- normas ---
    def marcar_version(self, version_libro_id: uuid.UUID) -> None:
        """Al publicarse un libro, las filas extraídas con otra versión quedan desactualizadas."""
        if self.origen == Origen.EXTRAIDA and self.version_libro_id != version_libro_id:
            self.version_desactualizada = True

    def valores(self) -> dict[str, Json]:
        return {clave: c.valor for clave, c in self.celdas.items()}

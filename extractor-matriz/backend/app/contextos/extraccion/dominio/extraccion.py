"""Agregado Extraccion (sección 5.3): un intento de extracción sobre un artículo.

Estados, en el orden del caso de uso ExtraerArticulo (sección 8.3):

    EXTRAYENDO → VALIDANDO → ANCLANDO → AUDITANDO → CONCILIANDO → COMPLETADA
    VALIDANDO → EXTRAYENDO           (otra iteración con los errores del validador)
    cualquiera salvo COMPLETADA → FALLIDA

Si el conciliador cambia un valor, la salida nueva se vuelve a validar sin salir de CONCILIANDO
(aplicar_conciliacion): con errores, se conserva la salida anterior y los cambios quedan pendientes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.compartido.dominio import Entidad, ErrorDeDominio, ahora
from app.contextos.extraccion.dominio.anclaje import Ancla, NivelAncla
from app.contextos.extraccion.eventos import CitaNoVerificable, ExtraccionCompletada, ExtraccionFallida


class EstadoExtraccion(StrEnum):
    EXTRAYENDO = "EXTRAYENDO"
    VALIDANDO = "VALIDANDO"
    ANCLANDO = "ANCLANDO"
    AUDITANDO = "AUDITANDO"
    CONCILIANDO = "CONCILIANDO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"


X = EstadoExtraccion
TRANSICIONES: dict[EstadoExtraccion, frozenset[EstadoExtraccion]] = {
    X.EXTRAYENDO: frozenset({X.VALIDANDO}),
    X.VALIDANDO: frozenset({X.EXTRAYENDO, X.ANCLANDO}),
    X.ANCLANDO: frozenset({X.AUDITANDO}),
    X.AUDITANDO: frozenset({X.CONCILIANDO}),
    X.CONCILIANDO: frozenset({X.COMPLETADA}),
    X.COMPLETADA: frozenset(),
    X.FALLIDA: frozenset(),
}


class Auditor(StrEnum):
    AUDITOR_EVIDENCIA = "AUDITOR_EVIDENCIA"
    CODIFICADOR_CIEGO = "CODIFICADOR_CIEGO"
    CONCILIADOR = "CONCILIADOR"


class Veredicto(StrEnum):
    CONFIRMADO = "CONFIRMADO"
    REFUTADO = "REFUTADO"
    NO_VERIFICABLE = "NO_VERIFICABLE"


class EstadoHallazgo(StrEnum):
    PENDIENTE = "PENDIENTE"
    RESUELTO = "RESUELTO"


def veredicto_de(texto: Any) -> Veredicto:
    """Lee el veredicto que escribe el modelo ("REFUTADO", "NO VERIFICABLE", "Refutado: ...")."""
    t = str(texto or "").strip().upper().replace(" ", "_")
    for v in (Veredicto.REFUTADO, Veredicto.NO_VERIFICABLE, Veredicto.CONFIRMADO):
        if t.startswith(v.value):
            return v
    return Veredicto.NO_VERIFICABLE


@dataclass(frozen=True)
class Hallazgo:
    estudio: int | None
    columna: str
    auditor: Auditor
    veredicto: Veredicto
    detalle: str
    evidencia_propuesta: Any = None
    resolucion: str | None = None
    estado: EstadoHallazgo = EstadoHallazgo.PENDIENTE

    def resolver(self, resolucion: str) -> Hallazgo:
        return Hallazgo(self.estudio, self.columna, self.auditor, self.veredicto, self.detalle,
                        self.evidencia_propuesta, resolucion, EstadoHallazgo.RESUELTO)

    def a_dict(self) -> dict[str, Any]:
        return {"estudio": self.estudio, "columna": self.columna, "auditor": self.auditor.value,
                "veredicto": self.veredicto.value, "detalle": self.detalle,
                "evidencia_propuesta": self.evidencia_propuesta, "resolucion": self.resolucion,
                "estado": self.estado.value}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> Hallazgo:
        return cls(estudio=d.get("estudio"), columna=d["columna"], auditor=Auditor(d["auditor"]),
                   veredicto=Veredicto(d["veredicto"]), detalle=d.get("detalle", ""),
                   evidencia_propuesta=d.get("evidencia_propuesta"), resolucion=d.get("resolucion"),
                   estado=EstadoHallazgo(d.get("estado", "PENDIENTE")))


@dataclass(kw_only=True, eq=False)
class Extraccion(Entidad):
    articulo_id: uuid.UUID
    version_libro_id: uuid.UUID
    estado: EstadoExtraccion = X.EXTRAYENDO
    estudios_reservados: list[int] = field(default_factory=list)
    salida: list[dict[str, Any]] = field(default_factory=list)
    codificacion_ciega: list[dict[str, Any]] = field(default_factory=list)
    anclas: list[Ancla] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    acuerdo_campos_criticos: float | None = None
    iteraciones_validador: int = 0
    errores_validador: list[str] = field(default_factory=list)
    avisos_validador: list[str] = field(default_factory=list)
    uso_tokens: dict[str, Any] = field(default_factory=dict)
    paso_fallido: str | None = None
    error: str | None = None
    iniciada_en: datetime = field(default_factory=ahora)
    terminada_en: datetime | None = None

    @classmethod
    def iniciar(cls, *, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, version_libro_id: uuid.UUID,
                estudios_reservados: list[int]) -> Extraccion:
        if not estudios_reservados or any(e < 1 for e in estudios_reservados):
            raise ErrorDeDominio("Una extracción empieza con al menos un número de Estudio reservado")
        return cls(proyecto_id=proyecto_id, articulo_id=articulo_id, version_libro_id=version_libro_id,
                   estudios_reservados=list(estudios_reservados))

    @property
    def terminada(self) -> bool:
        return self.estado in (X.COMPLETADA, X.FALLIDA)

    def pasar(self, nuevo: EstadoExtraccion) -> None:
        if nuevo in (X.FALLIDA, X.COMPLETADA):
            raise ErrorDeDominio("Para terminar use fallar() o completar()")
        if nuevo not in TRANSICIONES[self.estado]:
            raise ErrorDeDominio(f"Transición inválida de la extracción: {self.estado} → {nuevo}")
        self.estado = nuevo
        self.actualizado_en = ahora()

    def registrar_salida(self, salida: list[dict[str, Any]]) -> None:
        if self.estado != X.EXTRAYENDO:
            raise ErrorDeDominio(f"No se registra una salida en el estado {self.estado}")
        self.salida = salida
        self.pasar(X.VALIDANDO)

    def registrar_validacion(self, errores: list[str], avisos: list[str]) -> None:
        if self.estado != X.VALIDANDO:
            raise ErrorDeDominio("La validación se registra en el estado VALIDANDO")
        self.iteraciones_validador += 1
        self.errores_validador, self.avisos_validador = list(errores), list(avisos)

    def registrar_anclas(self, anclas: list[Ancla]) -> None:
        if self.estado != X.ANCLANDO:
            raise ErrorDeDominio("Las anclas se registran en el estado ANCLANDO")
        if self.errores_validador:
            raise ErrorDeDominio("No se ancla una salida con errores del validador")
        self.anclas = list(anclas)

    def registrar_hallazgos(self, ciega: list[dict[str, Any]], hallazgos: list[Hallazgo]) -> None:
        if self.estado != X.AUDITANDO:
            raise ErrorDeDominio("Los hallazgos de auditoría se registran en el estado AUDITANDO")
        self.codificacion_ciega = list(ciega)
        self.hallazgos = list(hallazgos)

    def aplicar_conciliacion(self, *, salida: list[dict[str, Any]], anclas: list[Ancla], hallazgos: list[Hallazgo],
                             errores: list[str], avisos: list[str]) -> bool:
        """Salida corregida por el conciliador, ya validada. Con errores no se aplica. Devuelve si se aplicó."""
        if self.estado != X.CONCILIANDO:
            raise ErrorDeDominio("La conciliación se aplica en el estado CONCILIANDO")
        self.iteraciones_validador += 1
        if errores:
            return False
        self.salida, self.anclas, self.hallazgos = list(salida), list(anclas), list(hallazgos)
        self.avisos_validador = list(avisos)
        return True

    def registrar_conciliacion(self, hallazgos: list[Hallazgo]) -> None:
        if self.estado != X.CONCILIANDO:
            raise ErrorDeDominio("La conciliación se registra en el estado CONCILIANDO")
        self.hallazgos = list(hallazgos)

    def registrar_uso(self, rol: str, uso: dict[str, Any]) -> None:
        r = self.uso_tokens.setdefault(rol, {"llamadas": 0, "entrada": 0, "cache_escritura": 0,
                                             "cache_lectura": 0, "salida": 0, "costo_usd": 0.0, "segundos": 0.0})
        r["llamadas"] += 1
        for k in ("entrada", "cache_escritura", "cache_lectura", "salida"):
            r[k] += int(uso.get(k) or 0)
        r["costo_usd"] = round(r["costo_usd"] + float(uso.get("costo_usd") or 0), 4)
        r["segundos"] = round(r["segundos"] + float(uso.get("segundos") or 0), 1)

    def completar(self, *, acuerdo: float | None) -> None:
        if self.estado != X.CONCILIANDO:
            raise TransicionDeExtraccionInvalida(self.estado, X.COMPLETADA)
        if not self.salida or self.errores_validador:
            raise ErrorDeDominio("Solo se completa una salida sin errores del validador")
        estudios = [int(f["fila"]["Estudio"]) for f in self.salida]
        self.acuerdo_campos_criticos = acuerdo
        self.estado = X.COMPLETADA
        self.terminada_en = ahora()
        for a in self.anclas:
            if a.nivel == NivelAncla.NO_VERIFICABLE:
                self.registrar(CitaNoVerificable(proyecto_id=self.proyecto_id, extraccion_id=self.id,
                                                 articulo_id=self.articulo_id, estudio=a.estudio,
                                                 columna=a.columna, indice_evidencia=a.indice_evidencia))
        self.registrar(ExtraccionCompletada(proyecto_id=self.proyecto_id, extraccion_id=self.id,
                                            articulo_id=self.articulo_id, estudios=estudios,
                                            acuerdo_campos_criticos=acuerdo))

    def fallar(self, mensaje: str) -> None:
        if self.terminada:
            raise TransicionDeExtraccionInvalida(self.estado, X.FALLIDA)
        self.paso_fallido = self.estado.value
        self.error = mensaje[:4000]
        self.estado = X.FALLIDA
        self.terminada_en = ahora()
        self.registrar(ExtraccionFallida(proyecto_id=self.proyecto_id, extraccion_id=self.id,
                                         articulo_id=self.articulo_id, paso=self.paso_fallido,
                                         mensaje=mensaje[:500]))


class TransicionDeExtraccionInvalida(ErrorDeDominio):
    def __init__(self, desde: EstadoExtraccion, hacia: EstadoExtraccion) -> None:
        super().__init__(f"Transición inválida de la extracción: {desde} → {hacia}")

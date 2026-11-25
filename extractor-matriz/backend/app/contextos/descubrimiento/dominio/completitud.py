"""Perfil de columnas, cobertura y puntaje de un candidato (plan «Buscar», sección 5).

La persona elige qué columnas de la matriz le importan y con qué prioridad. Para cada candidato se evalúa, columna por
columna, si los metadatos o el resumen sugieren que trae ese dato. El puntaje solo **ordena y filtra**; no escribe nada en
la matriz. Una columna que solo el PDF puede juzgar queda «pendiente» y **no** cuenta como ausente.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.compartido.dominio import Entidad, ErrorDeDominio
from app.contextos.descubrimiento.dominio.busqueda import plano
from app.contextos.descubrimiento.dominio.candidato import Candidato
from app.contextos.descubrimiento.dominio.detectores import CeldaPrevia, EstadoCelda, MotorDeDetectores, Nivel


class Prioridad(StrEnum):
    IMPRESCINDIBLE = "IMPRESCINDIBLE"
    IMPORTANTE = "IMPORTANTE"
    DESEABLE = "DESEABLE"


PESOS: dict[Prioridad, int] = {Prioridad.IMPRESCINDIBLE: 5, Prioridad.IMPORTANTE: 3, Prioridad.DESEABLE: 1}


class Etiqueta(StrEnum):
    PROBABLE = "PROBABLE"
    DUDOSO = "DUDOSO"
    SIN_DATOS = "SIN_DATOS"
    INCOMPLETO = "INCOMPLETO"
    NO_APLICA = "NO_APLICA"


class Exigir(StrEnum):
    NADA = "nada"
    SIN_AUSENTES = "sin_ausentes"  # oculta los que ya no pueden cumplir las imprescindibles
    CONFIRMADAS = "confirmadas"  # solo los que ya muestran indicio de todas las imprescindibles


@dataclass(frozen=True)
class ColumnaDelLibro:
    """Lo que la pestaña necesita saber de una columna del libro (lo aporta `app/composicion.py` desde Normas)."""

    clave: str
    encabezado: str
    valores_permitidos: tuple[str, ...] = ()
    derivada: bool = False


@dataclass(frozen=True)
class ColumnaElegida:
    clave: str
    prioridad: Prioridad

    def a_dict(self) -> dict[str, str]:
        return {"clave": self.clave, "prioridad": self.prioridad.value}


@dataclass(kw_only=True, eq=False)
class PerfilDeColumnas(Entidad):
    nombre: str
    columnas: tuple[ColumnaElegida, ...]
    predeterminado: bool = False

    def __post_init__(self) -> None:
        self.nombre = self.nombre.strip()[:100]
        if not self.nombre:
            raise ErrorDeDominio("El perfil necesita un nombre")
        if not self.columnas:
            raise ErrorDeDominio("Elija al menos una columna")
        claves = [c.clave for c in self.columnas]
        if len(claves) != len(set(claves)):
            raise ErrorDeDominio("Una columna no puede estar dos veces en el perfil")

    @property
    def imprescindibles(self) -> tuple[ColumnaElegida, ...]:
        return tuple(c for c in self.columnas if c.prioridad == Prioridad.IMPRESCINDIBLE)


# Propuesta inicial (plan, 5.1). Si alguna columna no existe en el libro vigente, simplemente se omite.
PERFIL_INICIAL: tuple[ColumnaElegida, ...] = (
    ColumnaElegida("Muestra", Prioridad.IMPRESCINDIBLE),
    ColumnaElegida("Correlacion o Beta felicidad 1 - JP", Prioridad.IMPRESCINDIBLE),
    ColumnaElegida("Instrumento felicidad", Prioridad.IMPRESCINDIBLE),
    ColumnaElegida("Escala de medición: Performance", Prioridad.IMPRESCINDIBLE),
    ColumnaElegida("Fiabilidad Alfa - Omega (felicidad)", Prioridad.IMPORTANTE),
    ColumnaElegida("Fiabilidad Alfa - Omega (desempeño)", Prioridad.IMPORTANTE),
    ColumnaElegida("Pais", Prioridad.IMPORTANTE),
    ColumnaElegida("Sector", Prioridad.DESEABLE),
    ColumnaElegida("Study design", Prioridad.DESEABLE),
    ColumnaElegida("Software", Prioridad.DESEABLE),
    ColumnaElegida("Start date", Prioridad.DESEABLE),
)


def perfil_inicial(proyecto_id: uuid.UUID, existentes: set[str]) -> PerfilDeColumnas:
    cols = tuple(c for c in PERFIL_INICIAL if c.clave in existentes) or PERFIL_INICIAL[:1]
    return PerfilDeColumnas(proyecto_id=proyecto_id, nombre="Esencial para metaanálisis", columnas=cols,
                            predeterminado=True)


_TITULO_SECUNDARIO = re.compile(
    r"systematic review|meta-?analy|scoping review|literature review|review of|bibliometric|a review\b|"
    r"revision sistematica|revision de la literatura|metaanalisis|state of the art")
_RESUMEN_SECUNDARIO = re.compile(
    r"this (?:systematic |scoping |literature |integrative )?review|this meta-?analy|we conducted a (?:systematic|meta)|"
    r"this bibliometric|esta revision|este metaanalisis")
_CUALITATIVO = re.compile(r"this qualitative|semi-structured interviews|thematic analysis|grounded theory|case study")


def no_aplica(c: Candidato) -> str | None:
    """Motivo por el que un candidato no aporta una correlación primaria (revisión, metaanálisis, cualitativo)."""
    if c.tipo == "review":
        return "revisión: no aporta una correlación primaria"
    titulo, resumen = plano(c.titulo), plano(c.resumen)
    if _TITULO_SECUNDARIO.search(titulo) or _RESUMEN_SECUNDARIO.search(resumen):
        return "revisión o metaanálisis: no aporta una correlación primaria"
    if _CUALITATIVO.search(resumen) and not re.search(r"correlat|regression|\br\s*=", resumen):
        return "estudio cualitativo: sin correlación primaria"
    return None


@dataclass(frozen=True)
class AnalisisDeTexto:
    """Lo que dio leer el texto completo de un PDF abierto (etapa B). No guarda el texto, solo indicios cortos con su
    página: son lo único que se conserva del documento."""

    candidato_id: uuid.UUID
    celdas: dict[str, CeldaPrevia]  # solo lo hallado
    intentadas: tuple[str, ...]  # columnas que los detectores sí buscaron
    paginas: int
    caracteres: int
    suficiente: bool  # False: casi no había texto (¿PDF escaneado?): no se puede afirmar que algo falte
    origen: str
    analizado_en: datetime


def celda_final(motor: MotorDeDetectores, clave: str, c: Candidato, analisis: AnalisisDeTexto | None) -> CeldaPrevia:
    """Combina la etapa A (metadatos y resumen) con la B (texto completo, si se leyó).

    Si el resumen ya daba un indicio, se conserva (medido: el cuerpo del texto cita otros estudios y empeora la precisión). Si no, vale el del texto completo, que trae la página. Solo si el
    texto era suficiente y el detector sí buscó esa columna, la ausencia de indicio es «ausente»; si no, «pendiente».
    """
    a = motor.evaluar(clave, c)
    if analisis is None or motor.nivel(clave) in (Nivel.M, Nivel.X):
        return a
    if a.estado == EstadoCelda.INDICIO:
        return a  # lo que dice el resumen es lo más fiable: el cuerpo del texto cita a otros estudios y sus ejemplos
    b = analisis.celdas.get(clave)
    if b is not None:
        return b
    if analisis.suficiente and clave in analisis.intentadas:
        return CeldaPrevia(clave, EstadoCelda.AUSENTE, origen="sin indicio en el texto completo")
    return a


@dataclass(frozen=True)
class Evaluacion:
    celdas: tuple[CeldaPrevia, ...]  # en el orden del perfil
    prioridades: tuple[Prioridad, ...]
    peso_total: int
    peso_cubierto: int
    peso_pendiente: int
    etiqueta: Etiqueta
    razon: str | None = None
    etapa: str = "A"  # A: metadatos y resumen · B: además, el texto completo

    @property
    def puntaje(self) -> float:
        return self.peso_cubierto / self.peso_total if self.peso_total else 0.0

    @property
    def maximo(self) -> float:
        """Lo más que podría llegar a ser si todo lo pendiente apareciera en el PDF."""
        return (self.peso_cubierto + self.peso_pendiente) / self.peso_total if self.peso_total else 0.0

    def imprescindibles_confirmadas(self) -> bool:
        return all(c.cubierta for c, p in zip(self.celdas, self.prioridades, strict=True)
                   if p == Prioridad.IMPRESCINDIBLE)

    def hay_imprescindible_perdida(self) -> bool:
        return any(c.estado == EstadoCelda.AUSENTE for c, p in zip(self.celdas, self.prioridades, strict=True)
                   if p == Prioridad.IMPRESCINDIBLE)

    def a_dict(self) -> dict[str, Any]:
        return {"puntaje": round(self.puntaje, 4), "maximo": round(self.maximo, 4), "etiqueta": self.etiqueta.value,
                "razon": self.razon, "etapa": self.etapa, "peso_total": self.peso_total,
                "celdas": [{**c.a_dict(), "prioridad": p.value} for c, p in zip(self.celdas, self.prioridades, strict=True)]}


def evaluar(motor: MotorDeDetectores, c: Candidato, perfil: PerfilDeColumnas,
            analisis: AnalisisDeTexto | None = None) -> Evaluacion:
    ev = _evaluar(motor, c, perfil, analisis)
    return replace(ev, etapa="B") if analisis is not None else ev


def _evaluar(motor: MotorDeDetectores, c: Candidato, perfil: PerfilDeColumnas,
             analisis: AnalisisDeTexto | None) -> Evaluacion:
    celdas = tuple(celda_final(motor, col.clave, c, analisis) for col in perfil.columnas)
    prioridades = tuple(col.prioridad for col in perfil.columnas)
    contables = [(cel, p) for cel, p in zip(celdas, prioridades, strict=True) if cel.estado != EstadoCelda.NO_APLICA]
    total = sum(PESOS[p] for _c, p in contables)
    cubierto = sum(PESOS[p] for cel, p in contables if cel.cubierta)
    pendiente = sum(PESOS[p] for cel, p in contables if cel.estado == EstadoCelda.PENDIENTE)
    base = Evaluacion(celdas, prioridades, total, cubierto, pendiente, Etiqueta.SIN_DATOS)
    motivo = no_aplica(c)
    if motivo:
        return Evaluacion(celdas, prioridades, total, cubierto, pendiente, Etiqueta.NO_APLICA, motivo)
    if base.hay_imprescindible_perdida():
        return Evaluacion(celdas, prioridades, total, cubierto, pendiente, Etiqueta.INCOMPLETO,
                          "la fuente no trae una columna imprescindible")
    imprescindibles = perfil.imprescindibles
    probable = base.imprescindibles_confirmadas() if imprescindibles else base.puntaje >= 0.5
    if probable:
        etiqueta = Etiqueta.PROBABLE
    elif base.maximo >= 0.5:
        etiqueta = Etiqueta.DUDOSO
    else:
        etiqueta = Etiqueta.SIN_DATOS
    return Evaluacion(celdas, prioridades, total, cubierto, pendiente, etiqueta)


def pasa_exigencia(ev: Evaluacion, exigir: Exigir) -> bool:
    if exigir == Exigir.NADA:
        return True
    if exigir == Exigir.SIN_AUSENTES:
        return ev.etiqueta not in (Etiqueta.NO_APLICA, Etiqueta.INCOMPLETO)
    return ev.etiqueta != Etiqueta.NO_APLICA and ev.imprescindibles_confirmadas()


def ordenar_por_puntaje(pares: list[tuple[Candidato, Evaluacion]]) -> list[tuple[Candidato, Evaluacion]]:
    """Mejor puntaje primero; luego el máximo posible; luego el año más reciente. «No aplica» al final."""
    def clave(par: tuple[Candidato, Evaluacion]) -> tuple[int, float, float, int]:
        c, ev = par
        return (1 if ev.etiqueta == Etiqueta.NO_APLICA else 0, -ev.puntaje, -ev.maximo, -(c.anio or 0))
    return sorted(pares, key=clave)


@dataclass(frozen=True)
class DetalleDeColumna:
    """Una columna tal como se ofrece en el selector."""

    clave: str
    encabezado: str
    grupo: str
    nivel: Nivel
    vocabulario: int = 0
    derivada: bool = False
    elegible: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return {"clave": self.clave, "encabezado": self.encabezado, "grupo": self.grupo, "nivel": self.nivel.value,
                "vocabulario": self.vocabulario, "derivada": self.derivada, "elegible": self.elegible}

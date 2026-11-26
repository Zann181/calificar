"""Búsqueda: la cadena por conceptos, sus filtros y el registro de cómo salió (plan «Buscar», secciones 4.1 y 11).

Una búsqueda es reproducible: guarda la cadena, los filtros, las fuentes y, por fuente, cuántos resultados y cuántos
errores hubo (insumo del diagrama de flujo de la revisión). Una vez ejecutada no se modifica.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from functools import lru_cache
from typing import Any

from app.compartido.dominio import Entidad, ErrorDeDominio

IDIOMAS_POR_DEFECTO = ("en", "es", "pt")
ANIO_DESDE_POR_DEFECTO = 2020


@lru_cache(maxsize=50_000)
def plano(texto: str) -> str:
    """Minúsculas y sin tildes: «Bienestar psicológico» → «bienestar psicologico». Para comparar, nunca para mostrar."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_marcas.replace("’", "'").replace("–", "-").replace("—", "-")).strip().lower()


@dataclass(frozen=True)
class Concepto:
    """Un concepto de la cadena: sus términos se unen con OR; los conceptos obligatorios, con AND."""

    nombre: str
    terminos: tuple[str, ...]
    obligatorio: bool = True

    def __post_init__(self) -> None:
        limpios = tuple(t.strip() for t in self.terminos if t.strip())
        if not limpios:
            raise ErrorDeDominio(f"El concepto «{self.nombre}» necesita al menos un término")
        object.__setattr__(self, "terminos", limpios)

    def a_dict(self) -> dict[str, Any]:
        return {"nombre": self.nombre, "terminos": list(self.terminos), "obligatorio": self.obligatorio}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> Concepto:
        return cls(nombre=str(d["nombre"]), terminos=tuple(str(t) for t in d["terminos"]),
                   obligatorio=bool(d.get("obligatorio", True)))


@dataclass(frozen=True)
class Filtros:
    desde: int = ANIO_DESDE_POR_DEFECTO
    hasta: int | None = None  # None: hasta la fecha de la búsqueda
    idiomas: tuple[str, ...] = IDIOMAS_POR_DEFECTO
    incluir_preprints: bool = True

    def hasta_efectivo(self, hoy: date) -> int:
        return self.hasta if self.hasta is not None else hoy.year

    def a_dict(self) -> dict[str, Any]:
        return {"desde": self.desde, "hasta": self.hasta, "idiomas": list(self.idiomas),
                "incluir_preprints": self.incluir_preprints}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> Filtros:
        return cls(desde=int(d.get("desde", ANIO_DESDE_POR_DEFECTO)),
                   hasta=None if d.get("hasta") is None else int(d["hasta"]),
                   idiomas=tuple(str(i) for i in d.get("idiomas", IDIOMAS_POR_DEFECTO)),
                   incluir_preprints=bool(d.get("incluir_preprints", True)))


def _termino_a_regex(termino: str) -> re.Pattern[str]:
    t = plano(termino)
    prefijo = t.endswith("*")
    t = re.escape(t.rstrip("*").strip())
    return re.compile(r"(?<!\w)" + t + (r"\w*" if prefijo else r"(?!\w)"))


@dataclass(frozen=True)
class ConsultaDeBusqueda:
    conceptos: tuple[Concepto, ...]
    filtros: Filtros = field(default_factory=Filtros)

    def __post_init__(self) -> None:
        if not any(c.obligatorio for c in self.conceptos):
            raise ErrorDeDominio("La búsqueda necesita al menos un concepto obligatorio")
        if self.filtros.hasta is not None and self.filtros.hasta < self.filtros.desde:
            raise ErrorDeDominio("El año final no puede ser anterior al inicial")

    @property
    def obligatorios(self) -> tuple[Concepto, ...]:
        return tuple(c for c in self.conceptos if c.obligatorio)

    def booleana(self, *, comodines: bool = True) -> str:
        """`("a" OR "b") AND ("c")`: la sintaxis que entienden OpenAlex y Europe PMC (sin campos).

        `comodines=False` quita el `*` final (OpenAlex lo rechaza en su búsqueda con raíces: «employee*» → «employee»,
        y sus raíces ya cubren «employees»). Las comas se cambian por espacios: separan filtros en OpenAlex.
        """
        def termino(t: str) -> str:
            t = t.replace(",", " ").strip()
            estrella = t.endswith("*")
            if estrella and not comodines:
                t, estrella = t.rstrip("*").strip(), False
            return f'"{t}"' if re.search(r"[\s\-]", t) and not estrella else t
        return " AND ".join("(" + " OR ".join(termino(t) for t in c.terminos) + ")" for c in self.obligatorios)

    def coincide(self, texto: str) -> bool:
        """Evalúa la cadena en local, para las fuentes que no saben de lógica booleana (Crossref)."""
        base = plano(texto)
        return all(any(_termino_a_regex(t).search(base) for t in c.terminos) for c in self.obligatorios)

    def a_dict(self) -> dict[str, Any]:
        return {"conceptos": [c.a_dict() for c in self.conceptos], "filtros": self.filtros.a_dict()}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> ConsultaDeBusqueda:
        return cls(conceptos=tuple(Concepto.desde_dict(c) for c in d["conceptos"]),
                   filtros=Filtros.desde_dict(d.get("filtros", {})))


def consulta_inicial() -> ConsultaDeBusqueda:
    """La cadena que fijó el responsable el 2026-11-25 (plan, sección 11). «job satisfaction» y «work engagement» van
    apagados: ensanchan mucho y meten ruido."""
    return ConsultaDeBusqueda(conceptos=(
        Concepto("Felicidad", (
            "happiness", "subjective well-being", "psychological well-being", "hedonic", "eudaimonic",
            "happy-productive", "felicidad", "bienestar subjetivo", "bienestar psicológico", "eudaimonía",
            "felicidade")),
        Concepto("Desempeño", (
            "job performance", "work performance", "task performance", "employee performance",
            "desempeño laboral", "rendimiento laboral", "desempenho no trabalho", "productivity")),
        Concepto("Contexto laboral", (
            "employee*", "worker*", "workplace", "empleado*", "trabajador*", "funcionario*")),
        Concepto("Satisfacción y compromiso (opcional)", ("job satisfaction", "work engagement"), obligatorio=False),
    ))


class EstadoBusqueda(StrEnum):
    EN_CURSO = "EN_CURSO"
    TERMINADA = "TERMINADA"
    TERMINADA_CON_ERRORES = "TERMINADA_CON_ERRORES"
    CANCELADA = "CANCELADA"


class Origen(StrEnum):
    """Dónde manda cada búsqueda (ADR 0012). `NUBE`: se lanzó en la web y el equipo todavía no la ha recogido."""

    EQUIPO = "equipo"
    NUBE = "nube"


class EstadoDeFuente(StrEnum):
    PENDIENTE = "PENDIENTE"
    BUSCANDO = "BUSCANDO"
    LISTA = "LISTA"
    ERROR = "ERROR"
    OMITIDA = "OMITIDA"


@dataclass
class ProgresoDeFuente:
    estado: EstadoDeFuente = EstadoDeFuente.PENDIENTE
    encontrados: int = 0
    nuevos: int = 0
    sin_pdf: int = 0  # descartados porque no entregan un PDF gratuito (ADR 0013)
    errores: int = 0
    ultimo_error: str | None = None

    def a_dict(self) -> dict[str, Any]:
        return {"estado": self.estado.value, "encontrados": self.encontrados, "nuevos": self.nuevos, "sin_pdf": self.sin_pdf,
                "errores": self.errores, "ultimo_error": self.ultimo_error}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> ProgresoDeFuente:
        return cls(estado=EstadoDeFuente(d.get("estado", "PENDIENTE")), encontrados=int(d.get("encontrados", 0)),
                   nuevos=int(d.get("nuevos", 0)), sin_pdf=int(d.get("sin_pdf", 0)), errores=int(d.get("errores", 0)), ultimo_error=d.get("ultimo_error"))


@dataclass(kw_only=True, eq=False)
class Busqueda(Entidad):
    nombre: str
    consulta: ConsultaDeBusqueda
    fuentes: tuple[str, ...]
    limite_por_fuente: int = 200
    estado: EstadoBusqueda = EstadoBusqueda.EN_CURSO
    progreso: dict[str, ProgresoDeFuente] = field(default_factory=dict)
    total_unicos: int = 0
    terminada_en: datetime | None = None
    origen: Origen = Origen.EQUIPO

    @classmethod
    def crear(cls, *, proyecto_id: uuid.UUID, nombre: str, consulta: ConsultaDeBusqueda, fuentes: tuple[str, ...],
              limite_por_fuente: int = 200, origen: Origen = Origen.EQUIPO) -> Busqueda:
        if not fuentes:
            raise ErrorDeDominio("Elija al menos una fuente")
        if not 1 <= limite_por_fuente <= 2000:
            raise ErrorDeDominio("El límite por fuente va de 1 a 2000")
        nombre = nombre.strip() or "Búsqueda sin nombre"
        return cls(proyecto_id=proyecto_id, nombre=nombre[:200], consulta=consulta, fuentes=fuentes,
                   limite_por_fuente=limite_por_fuente, origen=origen,
                   progreso={f: ProgresoDeFuente() for f in fuentes})

    @property
    def errores(self) -> int:
        return sum(p.errores for p in self.progreso.values())

    def terminar(self, *, cancelada: bool = False, cuando: datetime) -> None:
        self.terminada_en = cuando
        if cancelada:
            self.estado = EstadoBusqueda.CANCELADA
        elif self.errores:
            self.estado = EstadoBusqueda.TERMINADA_CON_ERRORES
        else:
            self.estado = EstadoBusqueda.TERMINADA

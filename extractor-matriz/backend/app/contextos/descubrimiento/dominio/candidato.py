"""Candidato: un trabajo encontrado por una o varias fuentes, y las reglas para reconocer que es el mismo trabajo.

Todo lo que trae un candidato es un **indicio** (regla de ubicación comprobable): nada de aquí entra a la matriz.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rapidfuzz import fuzz

from app.compartido.dominio import Entidad, ErrorDeDominio, ahora
from app.contextos.descubrimiento.dominio.busqueda import plano

UMBRAL_TITULO_PARECIDO = 93
MAX_RESUMEN = 20_000


class EstadoCandidato(StrEnum):
    NUEVO = "NUEVO"
    PRIORIZADO = "PRIORIZADO"
    DESCARTADO = "DESCARTADO"
    IMPORTADO = "IMPORTADO"


_PERMITIDAS: dict[EstadoCandidato, frozenset[EstadoCandidato]] = {
    EstadoCandidato.NUEVO: frozenset({EstadoCandidato.PRIORIZADO, EstadoCandidato.DESCARTADO}),
    EstadoCandidato.PRIORIZADO: frozenset({EstadoCandidato.NUEVO, EstadoCandidato.DESCARTADO}),
    EstadoCandidato.DESCARTADO: frozenset({EstadoCandidato.NUEVO}),
    EstadoCandidato.IMPORTADO: frozenset(),
}


@dataclass(frozen=True)
class Autor:
    nombre: str
    apellido: str = ""
    paises: tuple[str, ...] = ()

    def a_dict(self) -> dict[str, Any]:
        return {"nombre": self.nombre, "apellido": self.apellido, "paises": list(self.paises)}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> Autor:
        return cls(nombre=str(d.get("nombre", "")), apellido=str(d.get("apellido", "")),
                   paises=tuple(str(p) for p in d.get("paises", [])))


@dataclass(frozen=True)
class RegistroBibliografico:
    """Lo que una fuente dice de un trabajo, ya en nuestro vocabulario. Es lo único que cruza el puerto."""

    fuente: str
    id_externo: str
    posicion: int
    titulo: str
    doi: str | None = None
    autores: tuple[Autor, ...] = ()
    anio: int | None = None
    revista: str = ""
    resumen: str = ""
    palabras_clave: tuple[str, ...] = ()
    idioma: str = ""
    tipo: str = "article"
    url_oa: str | None = None
    es_preprint: bool = False
    pdfs: tuple[str, ...] = ()  # enlaces que la fuente declara como PDF gratuito y legal, del mejor al peor
    url_pdf: str | None = None  # el que ya se comprobó que entrega el PDF (ADR 0013)


def normalizar_doi(doi: str | None) -> str | None:
    """`https://doi.org/10.1000/ABC` → `10.1000/abc`. None si no parece un DOI."""
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d).strip().rstrip(".,;")
    return d if re.fullmatch(r"10\.\d{4,9}/\S+", d) else None


def titulo_plano(titulo: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", plano(titulo)).strip()


def clave_de(doi: str | None, titulo: str, anio: int | None, primer_apellido: str) -> str:
    """Identidad estable de un trabajo: su DOI; sin DOI, título + año + primer apellido."""
    d = normalizar_doi(doi)
    if d:
        return f"doi:{d}"
    return f"tit:{titulo_plano(titulo)[:160]}|{anio or ''}|{plano(primer_apellido)}"


def clave_del_registro(r: RegistroBibliografico) -> str:
    return clave_de(r.doi, r.titulo, r.anio, r.autores[0].apellido if r.autores else "")


def mismo_trabajo(titulo_a: str, anio_a: int | None, titulo_b: str, anio_b: int | None) -> bool:
    """Sin DOI en común: títulos casi iguales y años a ≤ 1 de distancia (un preprint sale antes que el artículo)."""
    a, b = titulo_plano(titulo_a), titulo_plano(titulo_b)
    if not a or not b:
        return False
    if anio_a is not None and anio_b is not None and abs(anio_a - anio_b) > 1:
        return False
    return bool(fuzz.ratio(a, b) >= UMBRAL_TITULO_PARECIDO)


@dataclass(kw_only=True, eq=False)
class Candidato(Entidad):
    clave: str
    titulo: str
    doi: str | None = None
    anio: int | None = None
    autores: list[Autor] = field(default_factory=list)
    revista: str = ""
    resumen: str = ""
    palabras_clave: list[str] = field(default_factory=list)
    idioma: str = ""
    tipo: str = "article"
    url_oa: str | None = None
    es_preprint: bool = False
    url_pdf: str | None = None  # PDF gratuito comprobado (ADR 0013)
    fuentes: list[str] = field(default_factory=list)
    estado: EstadoCandidato = EstadoCandidato.NUEVO
    motivo: str | None = None
    en_matriz: bool = False
    articulo_id: uuid.UUID | None = None

    @classmethod
    def desde(cls, proyecto_id: uuid.UUID, r: RegistroBibliografico) -> Candidato:
        if not r.titulo.strip():
            raise ErrorDeDominio("Un candidato necesita título")
        c = cls(proyecto_id=proyecto_id, clave=clave_del_registro(r), titulo=r.titulo.strip(),
                doi=normalizar_doi(r.doi), anio=r.anio, autores=list(r.autores), revista=r.revista,
                resumen=r.resumen[:MAX_RESUMEN], palabras_clave=list(r.palabras_clave), idioma=r.idioma, tipo=r.tipo,
                url_oa=r.url_oa, es_preprint=r.es_preprint, url_pdf=r.url_pdf, fuentes=[r.fuente])
        return c

    @property
    def paises(self) -> list[str]:
        vistos: list[str] = []
        for a in self.autores:
            for p in a.paises:
                if p not in vistos:
                    vistos.append(p)
        return vistos

    def como_registro(self, fuente: str) -> RegistroBibliografico:
        """Lo que este candidato sabe, en forma de registro: para unirlo con otro que sea el mismo trabajo."""
        return RegistroBibliografico(
            fuente=fuente, id_externo=self.clave, posicion=0, titulo=self.titulo, doi=self.doi,
            autores=tuple(self.autores), anio=self.anio, revista=self.revista, resumen=self.resumen,
            palabras_clave=tuple(self.palabras_clave), idioma=self.idioma, tipo=self.tipo, url_oa=self.url_oa,
            es_preprint=self.es_preprint, url_pdf=self.url_pdf)

    def absorber(self, r: RegistroBibliografico) -> bool:
        """Suma lo que otra fuente sabe del mismo trabajo, sin pisar lo que ya había. True si cambió algo."""
        antes = (self.doi, self.resumen, self.url_oa, self.url_pdf, len(self.autores), self.anio, self.revista,
                 tuple(self.fuentes), tuple(self.palabras_clave), self.idioma)
        if r.fuente not in self.fuentes:
            self.fuentes.append(r.fuente)
        doi = normalizar_doi(r.doi)
        if doi and not self.doi:
            self.doi = doi
            self.clave = f"doi:{doi}"
        if len(r.resumen) > len(self.resumen):
            self.resumen = r.resumen[:MAX_RESUMEN]
        if r.url_oa and not self.url_oa:
            self.url_oa = r.url_oa
        if r.url_pdf and not self.url_pdf:
            self.url_pdf = r.url_pdf
        if len(r.autores) > len(self.autores) or (
                r.autores and sum(len(a.paises) for a in r.autores) > sum(len(a.paises) for a in self.autores)):
            self.autores = list(r.autores)
        if self.anio is None and r.anio is not None:
            self.anio = r.anio
        if not self.revista and r.revista:
            self.revista = r.revista
        for p in r.palabras_clave:
            if p not in self.palabras_clave:
                self.palabras_clave.append(p)
        if not self.idioma and r.idioma:
            self.idioma = r.idioma
        if self.es_preprint and not r.es_preprint:
            self.es_preprint = False  # si alguna fuente lo conoce ya publicado, deja de ser solo preprint
        despues = (self.doi, self.resumen, self.url_oa, self.url_pdf, len(self.autores), self.anio, self.revista,
                   tuple(self.fuentes), tuple(self.palabras_clave), self.idioma)
        cambio = antes != despues
        if cambio:
            self.actualizado_en = ahora()
        return cambio

    # --- decisiones de la persona ---
    def _pasar(self, nuevo: EstadoCandidato) -> None:
        if nuevo == self.estado:
            return
        if nuevo not in _PERMITIDAS[self.estado]:
            raise ErrorDeDominio(f"Un candidato {self.estado.value.lower()} no puede pasar a {nuevo.value.lower()}")
        self.estado = nuevo
        self.actualizado_en = ahora()

    def priorizar(self) -> None:
        self._pasar(EstadoCandidato.PRIORIZADO)
        self.motivo = None

    def descartar(self, motivo: str) -> None:
        if not motivo or not motivo.strip():
            raise ErrorDeDominio("Descartar exige motivo")
        self._pasar(EstadoCandidato.DESCARTADO)
        self.motivo = motivo.strip()[:500]

    def reactivar(self) -> None:
        self._pasar(EstadoCandidato.NUEVO)
        self.motivo = None

    def marcar_importado(self, articulo_id: uuid.UUID) -> None:
        if self.estado == EstadoCandidato.DESCARTADO:
            raise ErrorDeDominio("Reactive el candidato antes de importarlo")
        self.estado = EstadoCandidato.IMPORTADO
        self.articulo_id = articulo_id
        self.actualizado_en = ahora()

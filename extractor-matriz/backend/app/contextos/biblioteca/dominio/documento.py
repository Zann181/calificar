"""Objeto de valor DocumentoEstructurado: salida normalizada de MinerU (páginas, bloques, tablas).

Coordenadas: puntos PDF con origen arriba a la izquierda (ADR 0001).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.compartido.dominio import ErrorDeDominio
from app.compartido.normalizacion import norm

TIPOS_DE_BLOQUE = ("titulo", "parrafo", "tabla", "figura", "ecuacion", "leyenda", "nota", "otro")
_PATRON_ID = re.compile(r"^p(\d{2,})-b(\d{2,})$")


def id_de_bloque(pagina: int, orden: int) -> str:
    return f"p{pagina:02d}-b{orden:02d}"


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ErrorDeDominio(f"Rectángulo inválido: {self}")

    def a_lista(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(frozen=True)
class Pagina:
    numero: int  # base 1
    ancho_pt: float
    alto_pt: float


@dataclass(frozen=True)
class CeldaTabla:
    fila: int
    columna: int
    texto: str
    etiqueta_fila: str
    etiqueta_columna: str


@dataclass(frozen=True)
class Tabla:
    html: str
    celdas: tuple[CeldaTabla, ...]
    es_imagen: bool


@dataclass(frozen=True)
class Bloque:
    id: str
    pagina: int
    tipo: str
    rect: Rect
    texto: str
    texto_norm: str = ""
    tabla: Tabla | None = None
    imagen: str | None = None  # ruta de la imagen dentro de la salida cruda

    def __post_init__(self) -> None:
        m = _PATRON_ID.match(self.id)
        if not m or int(m.group(1)) != self.pagina:
            raise ErrorDeDominio(f"Id de bloque inválido: {self.id} (página {self.pagina})")
        if self.tipo not in TIPOS_DE_BLOQUE:
            raise ErrorDeDominio(f"Tipo de bloque desconocido: {self.tipo}")
        if not self.texto_norm and self.texto:
            object.__setattr__(self, "texto_norm", norm(self.texto))


@dataclass(frozen=True)
class DocumentoEstructurado:
    paginas: tuple[Pagina, ...]
    bloques: tuple[Bloque, ...]
    metadatos: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [b.id for b in self.bloques]
        if len(ids) != len(set(ids)):
            raise ErrorDeDominio("Hay ids de bloque repetidos")
        numeros = {p.numero for p in self.paginas}
        fuera = [b.id for b in self.bloques if b.pagina not in numeros]
        if fuera:
            raise ErrorDeDominio(f"Bloques en páginas inexistentes: {fuera[:5]}")

    def bloque(self, id_bloque: str) -> Bloque | None:
        return next((b for b in self.bloques if b.id == id_bloque), None)

    def bloques_de_pagina(self, numero: int) -> list[Bloque]:
        return [b for b in self.bloques if b.pagina == numero]

    def pagina(self, numero: int) -> Pagina | None:
        return next((p for p in self.paginas if p.numero == numero), None)

    # Serialización para JSONB. Vive aquí para que el formato persistido sea parte del modelo.
    def a_dict(self) -> dict[str, Any]:
        return {
            "paginas": [{"numero": p.numero, "ancho_pt": p.ancho_pt, "alto_pt": p.alto_pt} for p in self.paginas],
            "bloques": [
                {
                    "id": b.id, "pagina": b.pagina, "tipo": b.tipo, "rect": b.rect.a_lista(),
                    "texto": b.texto, "texto_norm": b.texto_norm, "imagen": b.imagen,
                    "tabla": None if b.tabla is None else {
                        "html": b.tabla.html, "es_imagen": b.tabla.es_imagen,
                        "celdas": [
                            {"fila": c.fila, "columna": c.columna, "texto": c.texto,
                             "etiqueta_fila": c.etiqueta_fila, "etiqueta_columna": c.etiqueta_columna}
                            for c in b.tabla.celdas
                        ],
                    },
                }
                for b in self.bloques
            ],
            "metadatos": self.metadatos,
        }

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> DocumentoEstructurado:
        bloques = []
        for b in d["bloques"]:
            t = b.get("tabla")
            tabla = None if t is None else Tabla(
                html=t["html"], es_imagen=t["es_imagen"],
                celdas=tuple(CeldaTabla(**c) for c in t["celdas"]),
            )
            bloques.append(Bloque(id=b["id"], pagina=b["pagina"], tipo=b["tipo"], rect=Rect(*b["rect"]),
                                  texto=b["texto"], texto_norm=b["texto_norm"], tabla=tabla,
                                  imagen=b.get("imagen")))
        return cls(paginas=tuple(Pagina(**p) for p in d["paginas"]), bloques=tuple(bloques),
                   metadatos=d.get("metadatos", {}))

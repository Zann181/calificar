"""Agregado VersionDelLibro."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.compartido.dominio import Entidad, ahora
from app.contextos.normas.dominio.catalogo import CatalogoDeColumnas, validar_estructura
from app.contextos.normas.eventos import LibroPublicado


def huella_del_contenido(contenido: dict[str, Any]) -> str:
    canonico = json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass(kw_only=True, eq=False)
class VersionDelLibro(Entidad):
    version: str
    contenido: dict[str, Any]
    hash: str = ""
    activa: bool = False
    publicada_en: datetime | None = None
    _catalogo: CatalogoDeColumnas | None = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def publicar(cls, *, proyecto_id: Any, contenido: dict[str, Any]) -> VersionDelLibro:
        validar_estructura(contenido)
        version = str(contenido.get("metadatos", {}).get("version") or "sin versión")
        libro = cls(proyecto_id=proyecto_id, version=version, contenido=contenido,
                    hash=huella_del_contenido(contenido), activa=True, publicada_en=ahora())
        libro.catalogo()  # falla ahora si las columnas no se pueden derivar
        libro.registrar(LibroPublicado(proyecto_id=proyecto_id, version_libro_id=libro.id,
                                       version=version, hash=libro.hash))
        return libro

    def desactivar(self) -> None:
        self.activa = False

    def catalogo(self) -> CatalogoDeColumnas:
        if self._catalogo is None:
            self._catalogo = CatalogoDeColumnas(self.contenido)
        return self._catalogo

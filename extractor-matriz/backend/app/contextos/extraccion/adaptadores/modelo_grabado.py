"""Adaptadores de prueba del puerto ModeloDeLenguaje.

ModeloGrabado responde desde grabaciones (sección 6). Busca primero por la huella de la llamada
(rol, sistema y mensaje); si no la encuentra, usa la respuesta por rol, para que las pruebas doradas no
dependan del texto exacto de las instrucciones. Una respuesta por rol puede ser una lista: se entrega
en orden y la última se repite.

Grabadora envuelve un modelo real y guarda cada respuesta con su huella, para crear grabaciones.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from app.contextos.extraccion.puertos import ModeloDeLenguaje, RespuestaModelo


class SinGrabacion(LookupError):
    pass


def huella(rol: str, sistema: str, mensaje: str) -> str:
    return hashlib.sha256(json.dumps([rol, sistema, mensaje], ensure_ascii=False).encode("utf-8")).hexdigest()


class ModeloGrabado:
    def __init__(self, por_huella: dict[str, str] | None = None,
                 por_rol: dict[str, str | list[str]] | None = None) -> None:
        self._por_huella = dict(por_huella or {})
        self._por_rol = {rol: list(v) if isinstance(v, list) else [v] for rol, v in (por_rol or {}).items()}
        self._cerrojo = threading.Lock()
        self.llamadas: list[tuple[str, str]] = []  # (rol, mensaje), para las pruebas

    @classmethod
    def desde_carpeta(cls, carpeta: Path) -> ModeloGrabado:
        """Lee <huella>.txt (grabaciones de Grabadora) y <rol>.txt o <rol>.json (respuesta por rol)."""
        por_huella: dict[str, str] = {}
        por_rol: dict[str, str | list[str]] = {}
        for ruta in carpeta.iterdir():
            if not ruta.is_file():
                continue
            texto = ruta.read_text(encoding="utf-8")
            if len(ruta.stem) == 64:
                por_huella[ruta.stem] = texto
            else:
                por_rol[ruta.stem] = texto
        return cls(por_huella, por_rol)

    def completar(self, *, rol: str, sistema: str, mensaje: str,
                  imagenes: dict[str, bytes] | None = None) -> RespuestaModelo:
        with self._cerrojo:
            self.llamadas.append((rol, mensaje))
            h = huella(rol, sistema, mensaje)
            if h in self._por_huella:
                return RespuestaModelo(texto=self._por_huella[h], uso={"modelo": "grabado"})
            respuestas = self._por_rol.get(rol)
            if not respuestas:
                raise SinGrabacion(f"No hay grabación para el rol '{rol}' (huella {h[:12]})")
            texto = respuestas.pop(0) if len(respuestas) > 1 else respuestas[0]
            return RespuestaModelo(texto=texto, uso={"modelo": "grabado"})


class Grabadora:
    def __init__(self, modelo: ModeloDeLenguaje, carpeta: Path) -> None:
        self._modelo, self._carpeta = modelo, carpeta
        carpeta.mkdir(parents=True, exist_ok=True)

    def completar(self, *, rol: str, sistema: str, mensaje: str,
                  imagenes: dict[str, bytes] | None = None) -> RespuestaModelo:
        r = self._modelo.completar(rol=rol, sistema=sistema, mensaje=mensaje, imagenes=imagenes)
        (self._carpeta / f"{huella(rol, sistema, mensaje)}.txt").write_text(r.texto, encoding="utf-8")
        return r

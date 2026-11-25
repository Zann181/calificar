"""Lado de la nube (solo MODO=nube): manifiesto, archivos y lotes de sobres (ADR 0009, sección 6.3)."""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable
from typing import Any

from app.compartido.sobre import ESQUEMA, ORDEN_DE_TIPOS, Sobre, clave_de
from app.contextos.sincronizacion.dominio.plan import Manifiesto, tipo_de_contenido
from app.contextos.sincronizacion.puertos import (
    AlmacenDeArchivos,
    EstadoDeNube,
    FuenteDeReplica,
    ResultadoLote,
)


class EsquemaDesconocido(Exception):
    """El equipo local es más nuevo que la nube: hay que desplegar la nube primero (HTTP 426)."""


class LoteInvalido(Exception):
    """Sobre de un tipo que la nube no conoce, o archivo cuyo hash no coincide (HTTP 422)."""


class Ingesta:
    def __init__(self, fuentes: list[FuenteDeReplica], estado: EstadoDeNube, almacen: AlmacenDeArchivos,
                 archivos_guardados: Callable[[], dict[str, str]],
                 listar_proyectos: Callable[[], list[dict[str, str]]] = lambda: [],
                 al_cambiar: Callable[[int], None] = lambda _revision: None) -> None:
        self._por_tipo = {t: f for f in fuentes for t in f.tipos}
        self._fuentes, self._estado, self._almacen = fuentes, estado, almacen
        self._archivos_guardados = archivos_guardados
        self._listar_proyectos = listar_proyectos
        self._al_cambiar = al_cambiar  # aviso en memoria a las conexiones abiertas del visor (SSE)
        self._vistos: OrderedDict[str, ResultadoLote] = OrderedDict()  # Idempotency-Key de los últimos lotes
        self._cerrojo = threading.Lock()

    def revision(self) -> int:
        return self._estado.revision()

    def manifiesto(self, proyecto_id: uuid.UUID) -> Manifiesto:
        items: dict[str, str] = {}
        for f in self._fuentes:
            for s in f.sobres(proyecto_id):
                items[clave_de(s.tipo, s.id)] = s.hash
        return Manifiesto(revision=self._estado.revision(), items=items, archivos=self._archivos_guardados())

    # -- Restauración: el equipo local baja lo que la nube guarda -------------------------------------------------
    def proyectos(self) -> list[dict[str, str]]:
        return self._listar_proyectos()

    def sobres_de(self, proyecto_id: uuid.UUID, tipo: str) -> Iterable[Sobre]:
        if tipo not in self._por_tipo:
            raise LoteInvalido(f"Tipo de sobre desconocido: {tipo}")
        return (s for s in self._por_tipo[tipo].sobres(proyecto_id) if s.tipo == tipo)

    def leer_archivo(self, clave: str) -> tuple[bytes, str]:
        if ".." in clave.split("/") or clave.startswith("/"):
            raise LoteInvalido(f"Clave de archivo no válida: {clave}")
        datos = self._almacen.leer(clave)
        return datos, hashlib.sha256(datos).hexdigest()

    def recibir_archivo(self, clave: str, sha256: str, datos: bytes) -> None:
        if hashlib.sha256(datos).hexdigest() != sha256:
            raise LoteInvalido(f"El archivo {clave} llegó alterado: su SHA-256 no coincide")
        if ".." in clave.split("/") or clave.startswith("/"):
            raise LoteInvalido(f"Clave de archivo no válida: {clave}")
        self._almacen.guardar(clave, datos, tipo_de_contenido(clave))

    def aplicar_lote(self, sobres: list[Sobre], *, esquema: int, instalacion: str | None, tomar_control: bool,
                     clave_idempotencia: str | None = None) -> ResultadoLote:
        if esquema > ESQUEMA:
            raise EsquemaDesconocido(f"El lote usa el esquema {esquema} y esta nube solo entiende hasta el {ESQUEMA}: "
                                     "actualice la nube")
        with self._cerrojo:
            if clave_idempotencia and clave_idempotencia in self._vistos:
                return self._vistos[clave_idempotencia]
        for s in sobres:
            if s.tipo not in self._por_tipo:
                raise LoteInvalido(f"Tipo de sobre desconocido: {s.tipo}")
        orden = {t: i for i, t in enumerate(ORDEN_DE_TIPOS)}
        # Primero lo eliminado (en orden inverso) y luego lo nuevo (en orden de dependencias).
        ordenados = sorted(sobres, key=lambda s: (0, -orden[s.tipo]) if s.eliminado else (1, orden[s.tipo]))
        contadores = {"aplicados": 0, "iguales": 0}

        def trabajo(sesion: Any) -> bool:
            for s in ordenados:
                if self._por_tipo[s.tipo].aplicar(sesion, s):
                    contadores["aplicados"] += 1
                else:
                    contadores["iguales"] += 1
            return contadores["aplicados"] > 0

        revision = self._estado.transaccion(trabajo, instalacion=instalacion, tomar_control=tomar_control)
        resultado = ResultadoLote(revision=revision, **contadores)
        if contadores["aplicados"]:
            self._al_cambiar(revision)
        if clave_idempotencia:
            with self._cerrojo:
                self._vistos[clave_idempotencia] = resultado
                while len(self._vistos) > 200:
                    self._vistos.popitem(last=False)
        return resultado

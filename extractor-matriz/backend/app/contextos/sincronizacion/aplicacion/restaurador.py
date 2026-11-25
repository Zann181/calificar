"""«Descargar proyecto desde la nube» (ADR 0009, Fase 2): restaura el equipo local desde la réplica.

La nube es la referencia y el equipo el destino. Por defecto solo se bajan los agregados y archivos que faltan; si
hay diferencias el plan las informa y no se toca nada hasta que se pida `reemplazar`. Nunca se borra lo local.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.compartido.sobre import ORDEN_DE_TIPOS, Sobre, clave_de
from app.contextos.sincronizacion.dominio.plan import (
    ErrorDeSincronizacion,
    PlanDeRestauracion,
    calcular_restauracion,
    tipo_de_contenido,
)
from app.contextos.sincronizacion.puertos import (
    AlmacenDeArchivos,
    DestinoRemoto,
    FuenteDeReplica,
    TransaccionLocal,
)

Progreso = Callable[[str, int, int], None]


class RestauracionRechazada(Exception):
    """Hay diferencias entre el equipo y la nube y no se pidió reemplazar."""


@dataclass
class ResultadoDeRestauracion:
    agregados: int = 0
    archivos: int = 0
    bytes_bajados: int = 0
    solo_locales: list[str] = field(default_factory=list)  # se dejaron como estaban
    reemplazados: int = 0


class Restaurador:
    def __init__(self, fuentes: list[FuenteDeReplica], almacen: AlmacenDeArchivos, transaccion: TransaccionLocal) -> None:
        self._fuentes, self._almacen, self._tx = fuentes, almacen, transaccion

    def _locales(self, proyecto_id: uuid.UUID, claves_nube: list[str]) -> tuple[dict[str, str], dict[str, str]]:
        items = {clave_de(s.tipo, s.id): s.hash for f in self._fuentes for s in f.sobres(proyecto_id)}
        archivos: dict[str, str] = {}
        for clave in claves_nube:
            if self._almacen.existe(clave):
                archivos[clave] = hashlib.sha256(self._almacen.leer(clave)).hexdigest()
        return items, archivos

    def planear(self, nube: DestinoRemoto, proyecto_id: uuid.UUID, manifiesto: Any) -> PlanDeRestauracion:
        items, archivos = self._locales(proyecto_id, list(manifiesto.archivos))
        return calcular_restauracion(items, archivos, manifiesto)

    def ejecutar(self, nube: DestinoRemoto, proyecto_id: uuid.UUID, manifiesto: Any, *, reemplazar: bool,
                 progreso: Progreso | None = None) -> ResultadoDeRestauracion:
        avisar = progreso or (lambda *_: None)
        plan = self.planear(nube, proyecto_id, manifiesto)
        if plan.hay_conflictos and not reemplazar:
            raise RestauracionRechazada(
                f"El equipo y la nube difieren en {len(plan.distintos)} agregados y {len(plan.archivos_distintos)} "
                "archivos. Revise el plan; para quedarse con la versión de la nube, use «reemplazar»")
        resultado = ResultadoDeRestauracion(solo_locales=plan.solo_locales)
        por_bajar_items = set(plan.faltan) | (set(plan.distintos) if reemplazar else set())
        por_bajar_archivos = plan.archivos_faltan + (plan.archivos_distintos if reemplazar else [])
        total = len(por_bajar_items) + len(por_bajar_archivos)
        hechos = 0
        for clave in por_bajar_archivos:  # los archivos primero: ningún artículo queda sin su PDF
            datos, sha = nube.bajar_archivo(clave)
            if hashlib.sha256(datos).hexdigest() != sha:
                raise ErrorDeSincronizacion(f"El archivo {clave} llegó alterado: su SHA-256 no coincide")
            self._almacen.guardar(clave, datos, tipo_de_contenido(clave))
            resultado.archivos += 1
            resultado.bytes_bajados += len(datos)
            hechos += 1
            avisar("archivos", hechos, total)
        sobres: list[Sobre] = []
        for tipo in ORDEN_DE_TIPOS:
            if not any(k.startswith(tipo + "/") for k in por_bajar_items):
                continue
            sobres.extend(s for s in nube.sobres(proyecto_id, tipo) if clave_de(s.tipo, s.id) in por_bajar_items)
        porque = {clave_de(s.tipo, s.id) for s in sobres}
        if porque != por_bajar_items:
            raise ErrorDeSincronizacion("La nube cambió durante la descarga; vuelva a intentarlo")
        por_tipo = {t: f for f in self._fuentes for t in f.tipos}

        def trabajo(sesion: Any) -> None:
            nonlocal hechos
            for s in sobres:  # en orden de dependencias: ya vienen por tipo
                por_tipo[s.tipo].aplicar(sesion, s)
                hechos += 1
                avisar("sobres", hechos, total)

        try:
            self._tx.ejecutar(trabajo)
        except Exception as e:
            if "UNIQUE" in str(e).upper() or "unique" in str(e):
                raise ErrorDeSincronizacion(
                    "Ya hay un proyecto con ese nombre y otro identificador en este equipo (¿corrió «semilla»?). "
                    "Restaure sobre una base vacía o sobre el mismo proyecto") from e
            raise
        resultado.agregados = len(sobres)
        resultado.reemplazados = len(set(plan.distintos) & por_bajar_items)
        # Verificación: lo restaurado quedó idéntico a la nube.
        despues, _ = self._locales(proyecto_id, [])
        malos = [k for k in por_bajar_items if despues.get(k) != manifiesto.items[k]]
        if malos:
            raise ErrorDeSincronizacion(f"La verificación posterior encontró {len(malos)} agregados distintos a los de la nube")
        return resultado

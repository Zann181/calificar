"""Una pasada de sincronización del equipo local hacia la nube (ADR 0009, sección 6.2).

    1. local  = hashes de todos los agregados replicables
    2. nube   = manifiesto
    3. plan   = lo que falta, lo que sobra
    4. archivos, luego eliminaciones y luego sobres nuevos en lotes (≤ 1 MB)
    5. verificar: el manifiesto de la nube iguala al local

Sin tabla local de «lo enviado»: la nube es la referencia, así una nube vacía o a medias se completa sola.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable

from app.compartido.dominio import ahora
from app.compartido.sobre import Sobre
from app.contextos.sincronizacion.dominio.plan import (
    ErrorDeSincronizacion,
    Manifiesto,
    Plan,
    calcular_plan,
    en_lotes,
    filtrar,
)
from app.contextos.sincronizacion.puertos import (
    AlmacenDeArchivos,
    Corrida,
    Credenciales,
    Destino,
    DestinoRemoto,
    FabricaDeDestino,
    FuenteDeReplica,
    RepositorioDeDestinos,
)

log = logging.getLogger("sincronizacion")
Progreso = Callable[[str, int, int], None]  # (fase, hechos, total)


class SinConfigurar(Exception):
    """Falta la URL de la nube o su token."""


class Sincronizador:
    def __init__(self, fuentes: list[FuenteDeReplica], almacen: AlmacenDeArchivos, destinos: RepositorioDeDestinos,
                 credenciales: Credenciales, fabrica_de_destino: FabricaDeDestino) -> None:
        self._fuentes, self._almacen, self._destinos = fuentes, almacen, destinos
        self._credenciales, self._fabrica = credenciales, fabrica_de_destino

    # -- piezas ------------------------------------------------------------------------------------------------
    def conectar(self, proyecto_id: uuid.UUID) -> tuple[Destino, DestinoRemoto]:
        destino = self._destinos.obtener(proyecto_id)
        token = self._credenciales.token(proyecto_id)
        if destino is None or not destino.url or not token:
            raise SinConfigurar("Falta la URL de la nube o el token de sincronización")
        return destino, self._fabrica(destino, token)

    def _locales(self, destino: Destino) -> tuple[list[Sobre], dict[str, str]]:
        sobres = filtrar((s for f in self._fuentes for s in f.sobres(destino.proyecto_id)), destino.opciones)
        archivos: dict[str, str] = {}
        for s in sobres:
            for clave in s.archivos:
                if clave in archivos:
                    continue
                try:
                    archivos[clave] = hashlib.sha256(self._almacen.leer(clave)).hexdigest()
                except FileNotFoundError:
                    log.warning("El archivo %s no está en el almacén local: no se sincroniza", clave)
        return sobres, archivos

    def plan(self, destino: Destino, nube: DestinoRemoto, *, todo: bool = False
             ) -> tuple[Plan, Manifiesto, list[Sobre], dict[str, str]]:
        """`todo`: «Reenviar todo». Se ignora lo que la nube dice tener, salvo para saber qué sobra."""
        sobres, archivos = self._locales(destino)
        manifiesto = nube.manifiesto(destino.proyecto_id)
        pid = str(destino.proyecto_id)
        plan = calcular_plan(sobres, archivos, manifiesto, destino.opciones, pid)
        if todo:
            completo = calcular_plan(sobres, archivos, Manifiesto(manifiesto.revision, {}, {}), destino.opciones, pid)
            completo.eliminar = plan.eliminar
            plan = completo
        return plan, manifiesto, sobres, archivos

    def pendientes(self, proyecto_id: uuid.UUID) -> Plan:
        """Qué falta enviar, sin enviar nada («Verificar integridad»)."""
        destino, nube = self.conectar(proyecto_id)
        return self.plan(destino, nube)[0]

    # -- pasada ------------------------------------------------------------------------------------------------
    def pasada(self, proyecto_id: uuid.UUID, *, motivo: str = "", tomar_control: bool = False, todo: bool = False,
               progreso: Progreso | None = None) -> Corrida:
        corrida = Corrida(id=uuid.uuid4(), proyecto_id=proyecto_id, iniciada_en=ahora(), motivo=motivo)
        try:
            destino, nube = self.conectar(proyecto_id)
            self._ejecutar(corrida, destino, nube, tomar_control, todo, progreso or (lambda *_: None))
            corrida.estado = "ok"
        except SinConfigurar as e:
            corrida.estado, corrida.detalle = "error", str(e)
        except ErrorDeSincronizacion as e:
            corrida.estado = "sin_conexion" if e.reintentable else "error"
            corrida.detalle = str(e)
        except Exception as e:  # una corrida que falla nunca tumba la aplicación local
            log.exception("La sincronización falló")
            corrida.estado, corrida.detalle = "error", f"{type(e).__name__}: {e}"
        corrida.terminada_en = ahora()
        self._destinos.registrar(corrida)
        return corrida

    def _ejecutar(self, corrida: Corrida, destino: Destino, nube: DestinoRemoto, tomar_control: bool, todo: bool,
                  progreso: Progreso) -> None:
        plan, inicial, _, archivos = self.plan(destino, nube, todo=todo)
        total = plan.pendientes
        hechos = 0
        for clave in plan.archivos:
            datos = self._almacen.leer(clave)
            nube.subir_archivo(clave, archivos[clave], datos)
            corrida.archivos += 1
            corrida.bytes_enviados += len(datos)
            hechos += 1
            progreso("archivos", hechos, total)
        revision: int | None = inicial.revision
        for lote in en_lotes(plan.eliminar) + en_lotes(plan.subir):
            clave = hashlib.sha256("".join(f"{s.tipo}/{s.id}:{s.hash}" for s in lote).encode()).hexdigest()
            r = nube.enviar_lote(lote, clave, tomar_control=tomar_control)
            revision = r.revision
            corrida.eliminados += sum(1 for s in lote if s.eliminado)
            corrida.sobres += sum(1 for s in lote if not s.eliminado)
            hechos += len(lote)
            progreso("sobres", hechos, total)
        if total:  # la verificación solo hace falta si se envió algo
            despues, manifiesto, _, _ = self.plan(destino, nube)
            if not despues.vacio:
                raise ErrorDeSincronizacion(
                    f"La verificación posterior encontró {despues.pendientes} diferencias entre el equipo y la nube "
                    f"({_resumen(despues)}). La siguiente pasada lo reintenta; si persiste, use «Reenviar todo»")
            revision = manifiesto.revision
        corrida.revision = revision


def _resumen(plan: Plan) -> str:
    partes = []
    if plan.archivos:
        partes.append(f"{len(plan.archivos)} archivos")
    if plan.eliminar:
        partes.append(f"{len(plan.eliminar)} por eliminar")
    if plan.subir:
        partes.append("por subir: " + ", ".join(sorted({f'{s.tipo}' for s in plan.subir})))
    return "; ".join(partes)

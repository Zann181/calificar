"""El equipo recoge las búsquedas lanzadas desde la web (ADR 0012).

Se desduplica contra lo que el equipo ya tiene, con las mismas reglas de una búsqueda propia. Es repetible: si el envío
posterior a la nube falla, la siguiente pasada vuelve a recibir lo mismo sin duplicar nada. Las decisiones de la persona
(priorizar, descartar, importar) no se tocan.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.contextos.descubrimiento.aplicacion.casos_de_uso import esta_en_matriz
from app.contextos.descubrimiento.dominio.busqueda import Busqueda, EstadoBusqueda, Origen
from app.contextos.descubrimiento.dominio.candidato import Candidato, mismo_trabajo, titulo_plano
from app.contextos.descubrimiento.puertos import (
    RepositorioDeBusquedas,
    RepositorioDeCandidatos,
    TitulosEnMatriz,
)

log = logging.getLogger("descubrimiento")


@dataclass(frozen=True)
class HallazgoRecibido:
    candidato: Candidato
    fuente: str
    posicion: int
    visto_en: datetime


@dataclass(frozen=True)
class BusquedaRecibida:
    busqueda: Busqueda
    hallazgos: Sequence[HallazgoRecibido]


class RecibirBusquedas:
    def __init__(self, busquedas: RepositorioDeBusquedas, candidatos: RepositorioDeCandidatos,
                 titulos: TitulosEnMatriz) -> None:
        self._busquedas, self._candidatos, self._titulos = busquedas, candidatos, titulos

    def ejecutar(self, proyecto_id: uuid.UUID, recibidas: Sequence[BusquedaRecibida]) -> int:
        terminadas = [r for r in recibidas
                      if r.busqueda.proyecto_id == proyecto_id and r.busqueda.estado != EstadoBusqueda.EN_CURSO]
        for r in terminadas:
            self._recibir(proyecto_id, r)
        return len(terminadas)

    def _recibir(self, proyecto_id: uuid.UUID, recibida: BusquedaRecibida) -> None:
        b = recibida.busqueda
        b.origen = Origen.EQUIPO  # desde ahora es del equipo, y el próximo envío se lo confirma a la nube
        self._busquedas.guardar(b)
        titulos_matriz = self._titulos.titulos(proyecto_id)
        planos = {titulo_plano(t) for t in titulos_matriz}
        indice = self._candidatos.indice(proyecto_id)
        ids = {cid for cid, _k, _t, _a in indice}
        por_clave = {clave: cid for cid, clave, _t, _a in indice}
        for h in recibida.hallazgos:
            nuevo = h.candidato
            existente = nuevo.id if nuevo.id in ids else por_clave.get(nuevo.clave)
            if existente is None:
                existente = next((cid for cid, _k, t, a in indice if mismo_trabajo(nuevo.titulo, nuevo.anio, t, a)), None)
            if existente is None:
                nuevo.proyecto_id = proyecto_id
                nuevo.en_matriz = esta_en_matriz(nuevo.titulo, planos, titulos_matriz)
                self._candidatos.guardar(nuevo)
                ids.add(nuevo.id)
                por_clave[nuevo.clave] = nuevo.id
                indice.append((nuevo.id, nuevo.clave, nuevo.titulo, nuevo.anio))
                existente = nuevo.id
            else:
                actual = self._candidatos.obtener(proyecto_id, existente)
                if actual.absorber(nuevo.como_registro(h.fuente)):
                    self._candidatos.guardar(actual)
                por_clave.setdefault(actual.clave, actual.id)
            self._busquedas.registrar_hallazgo(b.id, existente, h.fuente, h.posicion, h.visto_en)
        b.total_unicos = len(self._busquedas.candidatos_de(b.id))
        self._busquedas.guardar(b)
        log.info("Búsqueda «%s» hecha en la web: recibida en el equipo (%d candidatos)", b.nombre, b.total_unicos)

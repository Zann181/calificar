"""Réplica de Descubrimiento (ADR 0009 y 0012): las búsquedas, los candidatos y los perfiles viajan a la nube.

Tres agregados:
- **búsqueda** (solo las terminadas: una en curso cambia a cada rato y se envía al acabar);
- **candidato** (cuando alguna búsqueda terminada lo trajo), con sus hallazgos y, si se leyó su texto, el análisis
  (etapa B);
- **perfil** de columnas.

La nube también busca (ADR 0012). Lo buscado allí queda marcado `origen = nube`: **no** entra en el manifiesto, así que el
equipo no lo toma por «algo que ya no tengo» y no lo borra. El equipo lo recoge por el buzón (`BuzonDeDescubrimiento`) y,
al enviarlo de vuelta, la búsqueda pasa a ser del equipo.

No viajan: la caché HTTP, el estado de las fuentes, ni sesiones o credenciales (no existen en estas tablas). El análisis
guarda frases cortas con su página, nunca el texto ni el PDF.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.compartido.replica_sql import a_datos, aplicar_registro, registro_de
from app.compartido.sobre import Sobre, hash_de
from app.contextos.descubrimiento.adaptadores.tablas import (
    RegistroAnalisis,
    RegistroBusqueda,
    RegistroCandidato,
    RegistroHallazgo,
    RegistroPerfil,
    a_busqueda,
    a_candidato,
)
from app.contextos.descubrimiento.aplicacion.recibir import (
    BusquedaRecibida,
    HallazgoRecibido,
    RecibirBusquedas,
)
from app.contextos.descubrimiento.dominio.busqueda import EstadoBusqueda, Origen

_EN_CURSO = EstadoBusqueda.EN_CURSO.value
_NUBE = Origen.NUBE.value


def _hallazgo(h: RegistroHallazgo) -> dict[str, Any]:
    # El id del hallazgo es un contador de cada base: no viaja. Su identidad es (búsqueda, candidato, fuente).
    return a_datos(h, excluir=("id", "candidato_id"))


def _datos_de_candidato(c: RegistroCandidato, hallazgos: list[RegistroHallazgo],
                        analisis: RegistroAnalisis | None) -> dict[str, Any]:
    datos = a_datos(c)
    datos["hallazgos"] = sorted((_hallazgo(h) for h in hallazgos), key=lambda h: (h["busqueda_id"], h["fuente"]))
    datos["analisis"] = None if analisis is None else a_datos(analisis)
    return datos


def _sin_recoger() -> Select[Any]:
    """Las búsquedas de la web que el equipo todavía no ha recibido (en el equipo nunca queda ninguna)."""
    return select(RegistroBusqueda.id).where(RegistroBusqueda.origen == _NUBE)


class ReplicaDeDescubrimiento:
    tipos = ("busqueda", "candidato", "perfil")

    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]:
        pid = str(proyecto_id)
        replicables = (RegistroBusqueda.proyecto_id == proyecto_id, RegistroBusqueda.estado != _EN_CURSO,
                       RegistroBusqueda.origen != _NUBE)
        with self._fabrica() as s:
            for b in s.scalars(select(RegistroBusqueda).where(*replicables).order_by(RegistroBusqueda.id)):
                yield Sobre("busqueda", str(b.id), pid, a_datos(b))
            hallazgos: dict[uuid.UUID, list[RegistroHallazgo]] = {}
            q = (select(RegistroHallazgo).join(RegistroBusqueda, RegistroBusqueda.id == RegistroHallazgo.busqueda_id)
                 .where(*replicables))
            for h in s.scalars(q):
                hallazgos.setdefault(h.candidato_id, []).append(h)
            analisis = {a.candidato_id: a for a in s.scalars(
                select(RegistroAnalisis).join(RegistroCandidato, RegistroCandidato.id == RegistroAnalisis.candidato_id)
                .where(RegistroCandidato.proyecto_id == proyecto_id))}
            for c in s.scalars(select(RegistroCandidato).where(RegistroCandidato.proyecto_id == proyecto_id)
                               .order_by(RegistroCandidato.id)):
                if c.id in hallazgos:  # lo que solo trajo una búsqueda sin terminar (o sin recoger) espera
                    yield Sobre("candidato", str(c.id), pid, _datos_de_candidato(c, hallazgos[c.id], analisis.get(c.id)))
            for p in s.scalars(select(RegistroPerfil).where(RegistroPerfil.proyecto_id == proyecto_id)
                               .order_by(RegistroPerfil.id)):
                yield Sobre("perfil", str(p.id), pid, a_datos(p))

    # -- en el destino ----------------------------------------------------------------------------------------------
    def aplicar(self, sesion: Session, sobre: Sobre) -> bool:
        identificador = uuid.UUID(sobre.id)
        if sobre.tipo == "busqueda":
            return self._aplicar_busqueda(sesion, sobre, identificador)
        if sobre.tipo == "perfil":
            return self._aplicar_perfil(sesion, sobre, identificador)
        return self._aplicar_candidato(sesion, sobre, identificador)

    def _aplicar_busqueda(self, sesion: Session, sobre: Sobre, identificador: uuid.UUID) -> bool:
        actual = sesion.get(RegistroBusqueda, identificador)
        if sobre.eliminado:
            if actual is None:
                return False
            sesion.execute(delete(RegistroHallazgo).where(RegistroHallazgo.busqueda_id == identificador))
            sesion.execute(delete(RegistroBusqueda).where(RegistroBusqueda.id == identificador))
            sesion.flush()
            return True
        assert sobre.datos is not None
        if actual is not None and actual.origen == _NUBE and sobre.datos.get("origen") != _NUBE:
            self._soltar_hallazgos(sesion, identificador)
        return aplicar_registro(sesion, RegistroBusqueda, sobre.datos)

    def _soltar_hallazgos(self, sesion: Session, busqueda_id: uuid.UUID) -> None:
        """El equipo ya recogió esta búsqueda de la web: mandan sus candidatos (llegan enseguida). Lo que solo existía
        por ella se quita, para que no quede repetido lo que el equipo unió con otro candidato que ya tenía."""
        suyos = set(sesion.scalars(select(RegistroHallazgo.candidato_id)
                                   .where(RegistroHallazgo.busqueda_id == busqueda_id)))
        sesion.execute(delete(RegistroHallazgo).where(RegistroHallazgo.busqueda_id == busqueda_id))
        con_otros = set(sesion.scalars(select(RegistroHallazgo.candidato_id)
                                       .where(RegistroHallazgo.candidato_id.in_(suyos))))
        huerfanos = list(suyos - con_otros)
        if huerfanos:
            self._quitar_candidatos(sesion, huerfanos)
        sesion.flush()

    @staticmethod
    def _aplicar_perfil(sesion: Session, sobre: Sobre, identificador: uuid.UUID) -> bool:
        if sobre.eliminado:
            perfil = sesion.get(RegistroPerfil, identificador)
            if perfil is None:
                return False
            sesion.delete(perfil)
            sesion.flush()
            return True
        assert sobre.datos is not None
        # Un perfil rehecho conserva el nombre con otro id: el viejo sale antes (índice único).
        sesion.execute(delete(RegistroPerfil).where(
            RegistroPerfil.proyecto_id == uuid.UUID(sobre.datos["proyecto_id"]),
            RegistroPerfil.nombre == sobre.datos["nombre"], RegistroPerfil.id != identificador))
        sesion.flush()
        return aplicar_registro(sesion, RegistroPerfil, sobre.datos)

    @staticmethod
    def _quitar_candidatos(sesion: Session, ids: list[uuid.UUID]) -> None:
        sesion.execute(delete(RegistroHallazgo).where(RegistroHallazgo.candidato_id.in_(ids)))
        sesion.execute(delete(RegistroAnalisis).where(RegistroAnalisis.candidato_id.in_(ids)))
        sesion.execute(delete(RegistroCandidato).where(RegistroCandidato.id.in_(ids)))
        sesion.flush()

    def _aplicar_candidato(self, sesion: Session, sobre: Sobre, identificador: uuid.UUID) -> bool:
        actual = sesion.get(RegistroCandidato, identificador)
        if sobre.eliminado:
            if actual is None:
                return False
            self._quitar_candidatos(sesion, [identificador])
            return True
        assert sobre.datos is not None
        datos = dict(sobre.datos)
        hallazgos: list[dict[str, Any]] = datos.pop("hallazgos")
        analisis: dict[str, Any] | None = datos.pop("analisis")
        # Los del equipo: lo que la web encontró y aún no se recogió no cuenta para comparar ni se borra.
        del_equipo = select(RegistroHallazgo).where(RegistroHallazgo.candidato_id == identificador,
                                                    RegistroHallazgo.busqueda_id.not_in(_sin_recoger()))
        if actual is not None:
            suyos = list(sesion.scalars(del_equipo))
            if hash_de(_datos_de_candidato(actual, suyos, sesion.get(RegistroAnalisis, identificador))) == sobre.hash:
                return False
        # Otro id con la misma clave (la web encontró lo mismo): sale, pero conserva lo que falta por recoger.
        otros = list(sesion.scalars(select(RegistroCandidato.id).where(
            RegistroCandidato.proyecto_id == uuid.UUID(datos["proyecto_id"]), RegistroCandidato.clave == datos["clave"],
            RegistroCandidato.id != identificador)))
        por_recoger: list[dict[str, Any]] = []
        if otros:
            por_recoger = [_hallazgo(h) for h in sesion.scalars(select(RegistroHallazgo).where(
                RegistroHallazgo.candidato_id.in_(otros), RegistroHallazgo.busqueda_id.in_(_sin_recoger())))]
            self._quitar_candidatos(sesion, otros)
        aplicar_registro(sesion, RegistroCandidato, datos)
        for viejo in sesion.scalars(del_equipo):
            sesion.delete(viejo)
        sesion.flush()
        presentes = {(h.busqueda_id, h.fuente) for h in sesion.scalars(
            select(RegistroHallazgo).where(RegistroHallazgo.candidato_id == identificador))}
        for d in [*hallazgos, *por_recoger]:
            llave = (uuid.UUID(d["busqueda_id"]), d["fuente"])
            if llave not in presentes:
                presentes.add(llave)
                sesion.add(RegistroHallazgo(busqueda_id=llave[0], candidato_id=identificador, fuente=d["fuente"],
                                            posicion=d["posicion"], visto_en=datetime.fromisoformat(d["visto_en"])))
        if analisis is None:
            sesion.execute(delete(RegistroAnalisis).where(RegistroAnalisis.candidato_id == identificador))
        else:
            aplicar_registro(sesion, RegistroAnalisis, analisis)
        sesion.flush()
        return True


class BuzonDeDescubrimiento:
    """Lo buscado en la web que el equipo debe recoger: la nube lo empaqueta y el equipo lo recibe (ADR 0012)."""

    tipo = "busqueda"  # se recoge si «qué se sube» incluye las búsquedas

    def __init__(self, fabrica: Callable[[], Session], recibir: RecibirBusquedas) -> None:
        self._fabrica, self._recibir = fabrica, recibir

    def pendientes(self, proyecto_id: uuid.UUID) -> list[dict[str, Any]]:
        with self._fabrica() as s:
            q = select(RegistroBusqueda).where(RegistroBusqueda.proyecto_id == proyecto_id,
                                               RegistroBusqueda.origen == _NUBE, RegistroBusqueda.estado != _EN_CURSO)
            paquetes = []
            for b in s.scalars(q.order_by(RegistroBusqueda.creado_en)):
                filas = s.execute(
                    select(RegistroCandidato, RegistroHallazgo)
                    .join(RegistroHallazgo, RegistroHallazgo.candidato_id == RegistroCandidato.id)
                    .where(RegistroHallazgo.busqueda_id == b.id).order_by(RegistroHallazgo.id))
                paquetes.append({"busqueda": a_datos(b),
                                 "hallazgos": [{**_hallazgo(h), "candidato": a_datos(c)} for c, h in filas]})
            return paquetes

    def recibir(self, proyecto_id: uuid.UUID, paquetes: list[dict[str, Any]]) -> int:
        recibidas = []
        for p in paquetes:
            hallazgos = [HallazgoRecibido(
                candidato=a_candidato(registro_de(RegistroCandidato, h["candidato"])), fuente=h["fuente"],
                posicion=h["posicion"], visto_en=datetime.fromisoformat(h["visto_en"])) for h in p["hallazgos"]]
            recibidas.append(BusquedaRecibida(a_busqueda(registro_de(RegistroBusqueda, p["busqueda"])), hallazgos))
        return self._recibir.ejecutar(proyecto_id, recibidas)

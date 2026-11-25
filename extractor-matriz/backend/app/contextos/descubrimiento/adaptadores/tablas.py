"""Tablas de Descubrimiento y sus repositorios SQL. Sin cookies, contraseñas ni claves: solo lo encontrado."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.compartido.dominio import NoEncontrado, ahora
from app.contextos.descubrimiento.dominio.busqueda import (
    Busqueda,
    ConsultaDeBusqueda,
    EstadoBusqueda,
    ProgresoDeFuente,
)
from app.contextos.descubrimiento.dominio.candidato import Autor, Candidato, EstadoCandidato
from app.contextos.descubrimiento.dominio.completitud import (
    AnalisisDeTexto,
    ColumnaElegida,
    PerfilDeColumnas,
    Prioridad,
)
from app.contextos.descubrimiento.dominio.detectores import CeldaPrevia, EstadoCelda


class RegistroBusqueda(Base):
    __tablename__ = "descubrimiento_busquedas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    consulta: Mapped[dict[str, Any]]
    fuentes: Mapped[list[Any]]
    limite_por_fuente: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(30), index=True)
    progreso: Mapped[dict[str, Any]]
    total_unicos: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistroCandidato(Base):
    __tablename__ = "descubrimiento_candidatos"
    __table_args__ = (UniqueConstraint("proyecto_id", "clave", name="uq_candidato_clave"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    clave: Mapped[str] = mapped_column(String(400))
    doi: Mapped[str | None] = mapped_column(String(300), index=True)
    titulo: Mapped[str] = mapped_column(Text)
    anio: Mapped[int | None] = mapped_column(Integer, index=True)
    autores: Mapped[list[Any]]
    revista: Mapped[str] = mapped_column(String(300), server_default="")
    resumen: Mapped[str] = mapped_column(Text, server_default="")
    palabras_clave: Mapped[list[Any]]
    idioma: Mapped[str] = mapped_column(String(10), server_default="")
    tipo: Mapped[str] = mapped_column(String(30), server_default="article")
    url_oa: Mapped[str | None] = mapped_column(String(1000))
    es_preprint: Mapped[bool] = mapped_column(Boolean, default=False)
    fuentes: Mapped[list[Any]]
    estado: Mapped[str] = mapped_column(String(20), index=True)
    motivo: Mapped[str | None] = mapped_column(String(500))
    en_matriz: Mapped[bool] = mapped_column(Boolean, default=False)
    articulo_id: Mapped[uuid.UUID | None]
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistroHallazgo(Base):
    """Qué fuente devolvió qué candidato, en qué búsqueda y en qué posición (trazabilidad del flujo PRISMA)."""

    __tablename__ = "descubrimiento_hallazgos"
    __table_args__ = (UniqueConstraint("busqueda_id", "candidato_id", "fuente", name="uq_hallazgo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    busqueda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("descubrimiento_busquedas.id"), index=True)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("descubrimiento_candidatos.id"), index=True)
    fuente: Mapped[str] = mapped_column(String(40))
    posicion: Mapped[int] = mapped_column(Integer)
    visto_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistroPerfil(Base):
    """Columnas que la persona eligió para evaluar candidatos, con su prioridad y su orden (plan, sección 5.1)."""

    __tablename__ = "descubrimiento_perfiles"
    __table_args__ = (UniqueConstraint("proyecto_id", "nombre", name="uq_perfil_nombre"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    columnas: Mapped[list[Any]]
    predeterminado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistroAnalisis(Base):
    """Etapa B: indicios hallados en el texto completo de un PDF abierto. No guarda el texto ni el archivo."""

    __tablename__ = "descubrimiento_analisis"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("descubrimiento_candidatos.id"), primary_key=True)
    celdas: Mapped[dict[str, Any]]
    intentadas: Mapped[list[Any]]
    paginas: Mapped[int] = mapped_column(Integer)
    caracteres: Mapped[int] = mapped_column(Integer)
    suficiente: Mapped[bool] = mapped_column(Boolean)
    origen: Mapped[str] = mapped_column(String(100))
    analizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _a_analisis(r: RegistroAnalisis) -> AnalisisDeTexto:
    celdas = {k: CeldaPrevia(columna=k, estado=EstadoCelda(v["estado"]), valor=v.get("valor"),
                             origen=v.get("origen", ""), frase=v.get("frase")) for k, v in r.celdas.items()}
    return AnalisisDeTexto(candidato_id=r.candidato_id, celdas=celdas, intentadas=tuple(str(c) for c in r.intentadas),
                           paginas=r.paginas, caracteres=r.caracteres, suficiente=r.suficiente, origen=r.origen,
                           analizado_en=r.analizado_en)


class RepositorioDeAnalisisSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def guardar(self, a: AnalisisDeTexto) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroAnalisis, a.candidato_id) or RegistroAnalisis(candidato_id=a.candidato_id)
            r.celdas = {k: c.a_dict() for k, c in a.celdas.items()}
            r.intentadas, r.paginas, r.caracteres = list(a.intentadas), a.paginas, a.caracteres
            r.suficiente, r.origen, r.analizado_en = a.suficiente, a.origen[:100], a.analizado_en
            s.add(r)
            s.commit()

    def por_candidatos(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, AnalisisDeTexto]:
        if not ids:
            return {}
        with self._fabrica() as s:
            q = select(RegistroAnalisis).where(RegistroAnalisis.candidato_id.in_(ids))
            return {r.candidato_id: _a_analisis(r) for r in s.scalars(q)}


def _a_perfil(r: RegistroPerfil) -> PerfilDeColumnas:
    p = PerfilDeColumnas(proyecto_id=r.proyecto_id, id=r.id, nombre=r.nombre, predeterminado=r.predeterminado,
                         columnas=tuple(ColumnaElegida(str(c["clave"]), Prioridad(c["prioridad"])) for c in r.columnas))
    p.creado_en, p.actualizado_en = r.creado_en, r.actualizado_en
    return p


class RepositorioDePerfilesSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def guardar(self, p: PerfilDeColumnas) -> PerfilDeColumnas:
        """Upsert por nombre. Si queda como predeterminado, los demás dejan de serlo."""
        with self._fabrica() as s:
            r = s.scalar(select(RegistroPerfil).where(RegistroPerfil.proyecto_id == p.proyecto_id,
                                                      RegistroPerfil.nombre == p.nombre))
            if r is None:
                r = RegistroPerfil(id=p.id, proyecto_id=p.proyecto_id, nombre=p.nombre, creado_en=p.creado_en)
            r.columnas, r.predeterminado, r.actualizado_en = [c.a_dict() for c in p.columnas], p.predeterminado, ahora()
            s.add(r)
            s.flush()
            if p.predeterminado:
                for otro in s.scalars(select(RegistroPerfil).where(RegistroPerfil.proyecto_id == p.proyecto_id,
                                                                   RegistroPerfil.id != r.id)):
                    otro.predeterminado = False
            s.commit()
            return _a_perfil(r)

    def obtener(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> PerfilDeColumnas:
        with self._fabrica() as s:
            r = s.get(RegistroPerfil, perfil_id)
            if r is None or r.proyecto_id != proyecto_id:
                raise NoEncontrado("El perfil no existe en este proyecto")
            return _a_perfil(r)

    def listar(self, proyecto_id: uuid.UUID) -> list[PerfilDeColumnas]:
        with self._fabrica() as s:
            q = select(RegistroPerfil).where(RegistroPerfil.proyecto_id == proyecto_id).order_by(RegistroPerfil.nombre)
            return [_a_perfil(r) for r in s.scalars(q)]

    def predeterminado(self, proyecto_id: uuid.UUID) -> PerfilDeColumnas | None:
        with self._fabrica() as s:
            r = s.scalar(select(RegistroPerfil).where(RegistroPerfil.proyecto_id == proyecto_id,
                                                      RegistroPerfil.predeterminado.is_(True)))
            return None if r is None else _a_perfil(r)

    def borrar(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroPerfil, perfil_id)
            if r is None or r.proyecto_id != proyecto_id:
                raise NoEncontrado("El perfil no existe en este proyecto")
            s.delete(r)
            s.commit()


def _a_busqueda(r: RegistroBusqueda) -> Busqueda:
    b = Busqueda(proyecto_id=r.proyecto_id, id=r.id, nombre=r.nombre, consulta=ConsultaDeBusqueda.desde_dict(r.consulta),
                 fuentes=tuple(str(f) for f in r.fuentes), limite_por_fuente=r.limite_por_fuente,
                 estado=EstadoBusqueda(r.estado),
                 progreso={k: ProgresoDeFuente.desde_dict(v) for k, v in r.progreso.items()},
                 total_unicos=r.total_unicos, terminada_en=r.terminada_en)
    b.creado_en = r.creado_en
    return b


def _a_candidato(r: RegistroCandidato) -> Candidato:
    c = Candidato(proyecto_id=r.proyecto_id, id=r.id, clave=r.clave, titulo=r.titulo, doi=r.doi, anio=r.anio,
                  autores=[Autor.desde_dict(a) for a in r.autores], revista=r.revista, resumen=r.resumen,
                  palabras_clave=[str(p) for p in r.palabras_clave], idioma=r.idioma, tipo=r.tipo, url_oa=r.url_oa,
                  es_preprint=r.es_preprint, fuentes=[str(f) for f in r.fuentes], estado=EstadoCandidato(r.estado),
                  motivo=r.motivo, en_matriz=r.en_matriz, articulo_id=r.articulo_id)
    c.creado_en, c.actualizado_en = r.creado_en, r.actualizado_en
    return c


class RepositorioDeBusquedasSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def guardar(self, b: Busqueda) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroBusqueda, b.id) or RegistroBusqueda(id=b.id, creado_en=b.creado_en)
            r.proyecto_id, r.nombre, r.consulta = b.proyecto_id, b.nombre, b.consulta.a_dict()
            r.fuentes, r.limite_por_fuente, r.estado = list(b.fuentes), b.limite_por_fuente, b.estado.value
            r.progreso = {k: p.a_dict() for k, p in b.progreso.items()}
            r.total_unicos, r.terminada_en = b.total_unicos, b.terminada_en
            s.add(r)
            s.commit()

    def obtener(self, proyecto_id: uuid.UUID, busqueda_id: uuid.UUID) -> Busqueda:
        with self._fabrica() as s:
            r = s.get(RegistroBusqueda, busqueda_id)
            if r is None or r.proyecto_id != proyecto_id:
                raise NoEncontrado("La búsqueda no existe en este proyecto")
            return _a_busqueda(r)

    def listar(self, proyecto_id: uuid.UUID, cuantas: int = 50) -> list[Busqueda]:
        with self._fabrica() as s:
            q = (select(RegistroBusqueda).where(RegistroBusqueda.proyecto_id == proyecto_id)
                 .order_by(RegistroBusqueda.creado_en.desc()).limit(cuantas))
            return [_a_busqueda(r) for r in s.scalars(q)]

    def registrar_hallazgo(self, busqueda_id: uuid.UUID, candidato_id: uuid.UUID, fuente: str, posicion: int) -> None:
        with self._fabrica() as s:
            existe = s.scalar(select(RegistroHallazgo.id).where(
                RegistroHallazgo.busqueda_id == busqueda_id, RegistroHallazgo.candidato_id == candidato_id,
                RegistroHallazgo.fuente == fuente))
            if existe is None:
                s.add(RegistroHallazgo(busqueda_id=busqueda_id, candidato_id=candidato_id, fuente=fuente,
                                       posicion=posicion, visto_en=ahora()))
                s.commit()

    def candidatos_de(self, busqueda_id: uuid.UUID) -> set[uuid.UUID]:
        with self._fabrica() as s:
            return set(s.scalars(select(RegistroHallazgo.candidato_id).where(RegistroHallazgo.busqueda_id == busqueda_id)))


class RepositorioDeCandidatosSql:
    def __init__(self, fabrica: Callable[[], Session]) -> None:
        self._fabrica = fabrica

    def guardar(self, c: Candidato) -> None:
        with self._fabrica() as s:
            r = s.get(RegistroCandidato, c.id) or RegistroCandidato(id=c.id, creado_en=c.creado_en)
            r.proyecto_id, r.clave, r.doi, r.titulo, r.anio = c.proyecto_id, c.clave, c.doi, c.titulo, c.anio
            r.autores = [a.a_dict() for a in c.autores]
            r.revista, r.resumen, r.palabras_clave = c.revista[:300], c.resumen, list(c.palabras_clave)
            r.idioma, r.tipo, r.url_oa, r.es_preprint = c.idioma[:10], c.tipo[:30], (c.url_oa or None), c.es_preprint
            r.fuentes, r.estado, r.motivo, r.en_matriz = list(c.fuentes), c.estado.value, c.motivo, c.en_matriz
            r.articulo_id, r.actualizado_en = c.articulo_id, c.actualizado_en
            s.add(r)
            s.commit()

    def obtener(self, proyecto_id: uuid.UUID, candidato_id: uuid.UUID) -> Candidato:
        with self._fabrica() as s:
            r = s.get(RegistroCandidato, candidato_id)
            if r is None or r.proyecto_id != proyecto_id:
                raise NoEncontrado("El candidato no existe en este proyecto")
            return _a_candidato(r)

    def por_clave(self, proyecto_id: uuid.UUID, clave: str) -> Candidato | None:
        with self._fabrica() as s:
            r = s.scalar(select(RegistroCandidato).where(
                RegistroCandidato.proyecto_id == proyecto_id, RegistroCandidato.clave == clave))
            return None if r is None else _a_candidato(r)

    def por_ids(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Candidato]:
        if not ids:
            return []
        with self._fabrica() as s:
            q = select(RegistroCandidato).where(RegistroCandidato.proyecto_id == proyecto_id,
                                                RegistroCandidato.id.in_(ids))
            return [_a_candidato(r) for r in s.scalars(q)]

    def indice(self, proyecto_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str, int | None]]:
        with self._fabrica() as s:
            q = select(RegistroCandidato.id, RegistroCandidato.clave, RegistroCandidato.titulo, RegistroCandidato.anio
                       ).where(RegistroCandidato.proyecto_id == proyecto_id)
            return [(i, k, t, a) for i, k, t, a in s.execute(q)]

    def listar(self, proyecto_id: uuid.UUID, *, estado: EstadoCandidato | None = None,
               busqueda_id: uuid.UUID | None = None, texto: str | None = None, en_matriz: bool | None = None,
               desde: int = 0, cuantos: int = 100) -> tuple[list[Candidato], int]:
        with self._fabrica() as s:
            filtros: list[Any] = [RegistroCandidato.proyecto_id == proyecto_id]
            if estado is not None:
                filtros.append(RegistroCandidato.estado == estado.value)
            if en_matriz is not None:
                filtros.append(RegistroCandidato.en_matriz == en_matriz)
            if busqueda_id is not None:
                filtros.append(RegistroCandidato.id.in_(
                    select(RegistroHallazgo.candidato_id).where(RegistroHallazgo.busqueda_id == busqueda_id)))
            if texto and texto.strip():
                patron = f"%{texto.strip().lower()}%"
                filtros.append(or_(func.lower(RegistroCandidato.titulo).like(patron),
                                   func.lower(RegistroCandidato.resumen).like(patron),
                                   func.lower(func.coalesce(RegistroCandidato.doi, "")).like(patron)))
            total = s.scalar(select(func.count()).select_from(RegistroCandidato).where(*filtros)) or 0
            q = (select(RegistroCandidato).where(*filtros)
                 .order_by(RegistroCandidato.anio.desc().nulls_last(), RegistroCandidato.titulo)
                 .offset(desde).limit(cuantos))
            return [_a_candidato(r) for r in s.scalars(q)], int(total)

    def contadores(self, proyecto_id: uuid.UUID) -> dict[str, int]:
        with self._fabrica() as s:
            q = (select(RegistroCandidato.estado, func.count()).where(RegistroCandidato.proyecto_id == proyecto_id)
                 .group_by(RegistroCandidato.estado))
            cuenta = {e.value: 0 for e in EstadoCandidato}
            for estado, n in s.execute(q):
                cuenta[estado] = int(n)
            cuenta["EN_MATRIZ"] = int(s.scalar(select(func.count()).select_from(RegistroCandidato).where(
                RegistroCandidato.proyecto_id == proyecto_id, RegistroCandidato.en_matriz.is_(True))) or 0)
            return cuenta

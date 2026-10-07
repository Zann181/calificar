"""Repositorios SQL y unidad de trabajo de Biblioteca."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compartido.dominio import Entidad, NoEncontrado, ahora
from app.compartido.unidad_de_trabajo_sql import UnidadDeTrabajoSql
from app.contextos.biblioteca.adaptadores.tablas import RegistroArticulo, RegistroDocumento
from app.contextos.biblioteca.dominio.articulo import Articulo, DetalleError, EstadoArticulo
from app.contextos.biblioteca.dominio.documento import DocumentoEstructurado
from app.contextos.biblioteca.puertos import HuellaDuplicada


def _a_dominio(r: RegistroArticulo) -> Articulo:
    error = None
    if r.error:
        error = DetalleError(paso=EstadoArticulo(r.error["paso"]), mensaje=r.error["mensaje"],
                             fecha=datetime.fromisoformat(r.error["fecha"]))
    return Articulo(
        id=r.id, proyecto_id=r.proyecto_id, nombre_archivo=r.nombre_archivo, huella_sha256=r.huella_sha256,
        clave_almacen=r.clave_almacen, paginas=r.paginas, estado=EstadoArticulo(r.estado),
        estado_anterior=EstadoArticulo(r.estado_anterior) if r.estado_anterior else None,
        documento_estructurado_id=r.documento_estructurado_id, error=error, excluido_motivo=r.excluido_motivo,
        creado_en=r.creado_en, actualizado_en=r.actualizado_en,
    )


def _volcar(a: Articulo, r: RegistroArticulo) -> None:
    r.id, r.proyecto_id = a.id, a.proyecto_id
    r.nombre_archivo, r.huella_sha256, r.clave_almacen = a.nombre_archivo, a.huella_sha256, a.clave_almacen
    r.paginas, r.estado = a.paginas, a.estado.value
    r.estado_anterior = a.estado_anterior.value if a.estado_anterior else None
    r.documento_estructurado_id = a.documento_estructurado_id
    r.error = None if a.error is None else {"paso": a.error.paso.value, "mensaje": a.error.mensaje,
                                            "fecha": a.error.fecha.isoformat()}
    r.excluido_motivo = a.excluido_motivo
    r.creado_en, r.actualizado_en = a.creado_en, a.actualizado_en


class RepositorioDeArticulosSql:
    def __init__(self, sesion: Session, udt: UnidadDeTrabajoSql) -> None:
        self._s, self._udt = sesion, udt

    def agregar(self, articulo: Articulo) -> None:
        self._udt.seguir(articulo)

    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Articulo:
        r = self._s.get(RegistroArticulo, articulo_id)
        if r is None or r.proyecto_id != proyecto_id:
            raise NoEncontrado(f"Artículo {articulo_id} no existe en el proyecto")
        a = _a_dominio(r)
        self._udt.seguir(a)
        return a

    def por_huella(self, proyecto_id: uuid.UUID, huella: str) -> Articulo | None:
        r = self._s.scalar(select(RegistroArticulo).where(RegistroArticulo.proyecto_id == proyecto_id,
                                                          RegistroArticulo.huella_sha256 == huella))
        return None if r is None else _a_dominio(r)

    def listar(self, proyecto_id: uuid.UUID, estado: EstadoArticulo | None = None) -> list[Articulo]:
        q = select(RegistroArticulo).where(RegistroArticulo.proyecto_id == proyecto_id)
        if estado is not None:
            q = q.where(RegistroArticulo.estado == estado.value)
        return [_a_dominio(r) for r in self._s.scalars(q.order_by(RegistroArticulo.nombre_archivo))]

    def contar_por_estado(self, proyecto_id: uuid.UUID) -> dict[str, int]:
        filas = self._s.execute(select(RegistroArticulo.estado, func.count()).where(
            RegistroArticulo.proyecto_id == proyecto_id).group_by(RegistroArticulo.estado)).all()
        conteo = {e.value: 0 for e in EstadoArticulo}
        conteo.update({estado: n for estado, n in filas})
        return conteo

    def volcar(self, a: Articulo) -> None:
        r = self._s.get(RegistroArticulo, a.id) or RegistroArticulo()
        _volcar(a, r)
        self._s.add(r)


class RepositorioDeDocumentosSql:
    def __init__(self, sesion: Session, version_conversor: str | None = None) -> None:
        self._s, self._version = sesion, version_conversor

    def guardar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, documento: DocumentoEstructurado) -> uuid.UUID:
        r = RegistroDocumento(id=uuid.uuid4(), proyecto_id=proyecto_id, articulo_id=articulo_id,
                              contenido=documento.a_dict(), creado_en=ahora(),
                              version_conversor=str(documento.metadatos.get("conversor", ""))[:100] or None)
        self._s.add(r)
        return r.id

    def obtener(self, proyecto_id: uuid.UUID, documento_id: uuid.UUID) -> DocumentoEstructurado:
        r = self._s.get(RegistroDocumento, documento_id)
        if r is None or r.proyecto_id != proyecto_id:
            raise NoEncontrado(f"Documento {documento_id} no existe en el proyecto")
        return DocumentoEstructurado.desde_dict(r.contenido)


class UnidadDeTrabajoBibliotecaSql(UnidadDeTrabajoSql):
    articulos: RepositorioDeArticulosSql
    documentos: RepositorioDeDocumentosSql

    def _al_abrir(self) -> None:
        self.articulos = RepositorioDeArticulosSql(self.sesion, self)
        self.documentos = RepositorioDeDocumentosSql(self.sesion)

    def _guardar(self, agregado: Entidad) -> None:
        if isinstance(agregado, Articulo):
            self.articulos.volcar(agregado)

    def confirmar(self) -> None:
        try:
            super().confirmar()
        except IntegrityError as e:
            self.sesion.rollback()
            if "uq_articulo_huella" in str(e.orig):
                raise HuellaDuplicada(str(e.orig)) from e
            raise


def a_json(a: Articulo) -> dict[str, Any]:
    """Representación para la API."""
    return {
        "id": str(a.id), "nombre_archivo": a.nombre_archivo, "huella_sha256": a.huella_sha256,
        "estado": a.estado.value, "paginas": a.paginas,
        "documento_estructurado_id": str(a.documento_estructurado_id) if a.documento_estructurado_id else None,
        "error": None if a.error is None else {"paso": a.error.paso.value, "mensaje": a.error.mensaje,
                                               "fecha": a.error.fecha.isoformat()},
        "excluido_motivo": a.excluido_motivo, "creado_en": a.creado_en.isoformat(),
        "actualizado_en": a.actualizado_en.isoformat(),
    }

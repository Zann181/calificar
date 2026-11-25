"""Rutas de la pestaña «Buscar». Solo en el equipo local (en la nube no se incluyen: ADR 0009 y 0011)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.compartido.seguridad import proyecto_valido
from app.contextos.descubrimiento.aplicacion.casos_de_uso import CasosDeDescubrimiento
from app.contextos.descubrimiento.dominio.busqueda import (
    ANIO_DESDE_POR_DEFECTO,
    Busqueda,
    Concepto,
    ConsultaDeBusqueda,
    Filtros,
)
from app.contextos.descubrimiento.dominio.candidato import Candidato, EstadoCandidato
from app.contextos.descubrimiento.dominio.completitud import Evaluacion, Exigir, PerfilDeColumnas

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}", tags=["descubrimiento"])


def casos(request: Request) -> CasosDeDescubrimiento:
    c: CasosDeDescubrimiento = request.app.state.contenedor.descubrimiento
    return c


class ConceptoEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    terminos: list[str] = Field(min_length=1, max_length=60)
    obligatorio: bool = True


Idioma = Literal["en", "es", "pt"]


def _idiomas_por_defecto() -> list[Idioma]:
    return ["en", "es", "pt"]  # los mismos de IDIOMAS_POR_DEFECTO; aquí con el tipo literal que valida la entrada


class FiltrosEntrada(BaseModel):
    desde: int = Field(ANIO_DESDE_POR_DEFECTO, ge=1900, le=2100)
    hasta: int | None = Field(None, ge=1900, le=2100)
    idiomas: list[Idioma] = Field(default_factory=_idiomas_por_defecto, min_length=1)
    incluir_preprints: bool = True


class BusquedaNueva(BaseModel):
    nombre: str = ""
    conceptos: list[ConceptoEntrada] | None = None  # None: la cadena inicial
    filtros: FiltrosEntrada | None = None
    fuentes: list[str] | None = None  # None: todas las abiertas
    limite_por_fuente: int = Field(200, ge=1, le=2000)


class Decision(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    accion: Literal["priorizar", "descartar", "reactivar"]
    motivo: str | None = None


def busqueda_json(b: Busqueda) -> dict[str, Any]:
    return {"id": str(b.id), "nombre": b.nombre, "estado": b.estado.value, "creada_en": b.creado_en.isoformat(),
            "terminada_en": b.terminada_en.isoformat() if b.terminada_en else None, "fuentes": list(b.fuentes),
            "consulta": b.consulta.a_dict(), "cadena": b.consulta.booleana(),
            "progreso": {k: p.a_dict() for k, p in b.progreso.items()}, "total_unicos": b.total_unicos,
            "errores": b.errores, "limite_por_fuente": b.limite_por_fuente}


def perfil_json(p: PerfilDeColumnas) -> dict[str, Any]:
    return {"id": str(p.id), "nombre": p.nombre, "predeterminado": p.predeterminado,
            "columnas": [c.a_dict() for c in p.columnas]}


def candidato_json(c: Candidato, ev: Evaluacion | None = None) -> dict[str, Any]:
    return {"evaluacion": ev.a_dict() if ev else None, **candidato_base_json(c)}


def candidato_base_json(c: Candidato) -> dict[str, Any]:
    return {"id": str(c.id), "titulo": c.titulo, "doi": c.doi, "anio": c.anio, "revista": c.revista,
            "autores": [a.nombre for a in c.autores], "paises": c.paises, "resumen": c.resumen,
            "palabras_clave": c.palabras_clave, "idioma": c.idioma, "tipo": c.tipo, "url_oa": c.url_oa,
            "es_preprint": c.es_preprint, "fuentes": c.fuentes, "estado": c.estado.value, "motivo": c.motivo,
            "en_matriz": c.en_matriz, "articulo_id": str(c.articulo_id) if c.articulo_id else None}


@enrutador.get("/busqueda/configuracion")
def configuracion(proyecto_id: uuid.UUID = Depends(proyecto_valido),
                  c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Lo que la pestaña necesita para armar el formulario: la cadena inicial, las fuentes y los sitios con credenciales."""
    inicial = c.consultas.consulta_inicial()
    return {
        "consulta_inicial": inicial.a_dict(),
        "fuentes": [{"id": f.nombre, "etiqueta": f.etiqueta, "sitio_id": f.sitio_id,
                     "sesion": f.sesion.value if f.sesion else None, "utilizable": f.utilizable,
                     "desactivada": f.desactivada}
                    for f in c.consultas.fuentes()],
        "no_disponibles": [{"id": n.id, "etiqueta": n.etiqueta, "motivo": n.motivo} for n in c.consultas.no_disponibles()],
        "sitios": [{**s.a_dict(), "sesion": estado.value} for s, estado in c.consultas.sitios()],
    }


@enrutador.post("/busqueda/fuentes/{fuente}/reactivar")
def reactivar_fuente(fuente: str, proyecto_id: uuid.UUID = Depends(proyecto_valido),
                     c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, bool]:
    """Vuelve a encender una fuente que se apagó sola porque el sitio cambió de forma."""
    c.consultas.reactivar_fuente(fuente)
    return {"reactivada": True}


@enrutador.post("/busquedas", status_code=202)
def iniciar(datos: BusquedaNueva, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    base = c.consultas.consulta_inicial()
    conceptos = (tuple(Concepto(x.nombre, tuple(x.terminos), x.obligatorio) for x in datos.conceptos)
                 if datos.conceptos is not None else base.conceptos)
    filtros = (Filtros(desde=datos.filtros.desde, hasta=datos.filtros.hasta, idiomas=tuple(datos.filtros.idiomas),
                       incluir_preprints=datos.filtros.incluir_preprints) if datos.filtros else base.filtros)
    fuentes = tuple(datos.fuentes) if datos.fuentes else tuple(f.nombre for f in c.consultas.fuentes() if f.utilizable)
    b = c.buscar.iniciar(proyecto_id, datos.nombre, ConsultaDeBusqueda(conceptos, filtros), fuentes,
                         datos.limite_por_fuente)
    return busqueda_json(c.consultas.busqueda(proyecto_id, b.id))


@enrutador.get("/busquedas")
def listar_busquedas(proyecto_id: uuid.UUID = Depends(proyecto_valido),
                     c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    return {"busquedas": [busqueda_json(b) for b in c.consultas.busquedas(proyecto_id)]}


@enrutador.get("/busquedas/{busqueda_id}")
def ver_busqueda(busqueda_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
                 c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    return busqueda_json(c.consultas.busqueda(proyecto_id, busqueda_id))


@enrutador.post("/busquedas/{busqueda_id}/cancelar")
def cancelar(busqueda_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    c.consultas.busqueda(proyecto_id, busqueda_id)  # 404 si no es de este proyecto
    c.buscar.cancelar(busqueda_id)
    return {"cancelando": True}


@enrutador.get("/candidatos")
def candidatos(estado: EstadoCandidato | None = None, busqueda_id: uuid.UUID | None = None,
               q: str | None = Query(None, max_length=200), en_matriz: bool | None = None,
               perfil_id: uuid.UUID | None = None, orden: Literal["reciente", "puntaje"] = "reciente",
               exigir: Exigir = Exigir.NADA, desde: int = Query(0, ge=0), cuantos: int = Query(100, ge=1, le=500),
               proyecto_id: uuid.UUID = Depends(proyecto_valido),
               c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Candidatos evaluados con el perfil de columnas (el predeterminado si no se indica otro)."""
    r = c.evaluar.listar(proyecto_id, perfil_id=perfil_id, estado=estado, busqueda_id=busqueda_id, texto=q,
                         en_matriz=en_matriz, orden=orden, exigir=exigir, desde=desde, cuantos=cuantos)
    return {"candidatos": [candidato_json(x, ev) for x, ev in r.filas], "total": r.total, "contadores": r.contadores,
            "perfil": perfil_json(r.perfil)}


class SeleccionEntrada(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    perfil_id: uuid.UUID | None = None


class ExportarEntrada(SeleccionEntrada):
    formato: Literal["csv", "ris"] = "csv"


class ColumnaEntrada(BaseModel):
    clave: str = Field(min_length=1, max_length=200)
    prioridad: Literal["IMPRESCINDIBLE", "IMPORTANTE", "DESEABLE"] = "DESEABLE"


class PerfilEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    columnas: list[ColumnaEntrada] = Field(min_length=1, max_length=80)
    predeterminado: bool = False


@enrutador.get("/busqueda/columnas")
def columnas_elegibles(proyecto_id: uuid.UUID = Depends(proyecto_valido),
                       c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Las columnas del libro con su detectabilidad: M metadato, R resumen, T solo texto completo, X interna."""
    cols = c.perfiles.catalogo(proyecto_id)
    return {"columnas": [x.a_dict() for x in cols],
            "grupos": list(dict.fromkeys(x.grupo for x in cols)),
            "niveles": {"M": "Metadato de la fuente", "R": "Título, resumen o palabras clave",
                        "T": "Solo el texto completo (PDF)", "X": "Interna: la asigna el equipo o el programa"}}


@enrutador.get("/busqueda/perfiles")
def perfiles(proyecto_id: uuid.UUID = Depends(proyecto_valido),
             c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    return {"perfiles": [perfil_json(p) for p in c.perfiles.listar(proyecto_id)],
            "activo": perfil_json(c.perfiles.activo(proyecto_id)),
            "inicial": perfil_json(c.perfiles.inicial(proyecto_id))}


@enrutador.put("/busqueda/perfiles")
def guardar_perfil(datos: PerfilEntrada, proyecto_id: uuid.UUID = Depends(proyecto_valido),
                   c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Crea o reemplaza el perfil con ese nombre. Si es el predeterminado, la lista de candidatos lo usa."""
    p = c.perfiles.guardar(proyecto_id, datos.nombre, [(x.clave, x.prioridad) for x in datos.columnas],
                           datos.predeterminado)
    return perfil_json(p)


@enrutador.delete("/busqueda/perfiles/{perfil_id}")
def borrar_perfil(perfil_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
                  c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, bool]:
    c.perfiles.borrar(proyecto_id, perfil_id)
    return {"borrado": True}


@enrutador.post("/candidatos/vista-previa")
def vista_previa(datos: SeleccionEntrada, proyecto_id: uuid.UUID = Depends(proyecto_valido),
                 c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Cómo encajaría cada candidato seleccionado con las columnas elegidas. **Sin verificar: no escribe en la matriz.**"""
    perfil, pares = c.evaluar.vista_previa(proyecto_id, datos.ids, datos.perfil_id)
    return {"perfil": perfil_json(perfil), "sin_verificar": True,
            "candidatos": [candidato_json(x, ev) for x, ev in pares]}


@enrutador.post("/candidatos/exportar")
def exportar(datos: ExportarEntrada, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             c: CasosDeDescubrimiento = Depends(casos)) -> Response:
    nombre, contenido, mime = c.evaluar.exportar(proyecto_id, datos.ids, datos.formato, datos.perfil_id)
    return Response(contenido.encode("utf-8"), media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


class ImportarEntrada(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


@enrutador.post("/candidatos/importar")
def importar(datos: ImportarEntrada, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Consigue el PDF abierto de cada candidato (hasta 10) y lo deja en «Nuevo» en Artículos. No extrae ni toca la matriz."""
    r = c.importar.ejecutar(proyecto_id, datos.ids)
    return {"resultados": [{"id": str(x.candidato_id), "titulo": x.titulo, "estado": x.estado.value,
                            "mensaje": x.mensaje, "articulo_id": str(x.articulo_id) if x.articulo_id else None}
                           for x in r]}


@enrutador.post("/candidatos/analizar")
def analizar(datos: ImportarEntrada, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    """Etapa B: lee el texto completo del PDF abierto (hasta 10) y guarda solo los indicios con su página."""
    r = c.analizar.ejecutar(proyecto_id, datos.ids)
    return {"resultados": [{"id": str(x.candidato_id), "titulo": x.titulo, "estado": x.estado.value,
                            "mensaje": x.mensaje, "con_indicio": x.con_indicio} for x in r]}


@enrutador.post("/candidatos/decision")
def decidir(datos: Decision, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            c: CasosDeDescubrimiento = Depends(casos)) -> dict[str, Any]:
    r = c.decidir.ejecutar(proyecto_id, datos.ids, datos.accion, datos.motivo)
    return {"cambiados": [candidato_json(x) for x in r.cambiados],
            "rechazados": {str(k): v for k, v in r.rechazados.items()}}

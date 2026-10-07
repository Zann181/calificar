"""Lanzar extracciones desde la interfaz y consultar su avance.

POST /extracciones           encola artículos (corren en segundo plano, uno tras otro)
POST /extracciones/retomar   vuelve a lanzar artículos en Error con los datos de su último intento
GET  /extracciones/avance    extracciones en curso o terminadas hace poco, con porcentaje y paso actual,
                             más los artículos que esperan en cola
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.compartido.dominio import ErrorDeDominio, ahora
from app.compartido.seguridad import Usuario, proyecto_valido, usuario_actual
from app.composicion import Contenedor
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.extraccion.aplicacion.casos_de_uso import OpcionesDeExtraccion
from app.contextos.extraccion.aplicacion.ejecutor import PedidoDeExtraccion
from app.contextos.extraccion.dominio.extraccion import PASOS, EstadoExtraccion, Extraccion

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}", tags=["extraccion"])

# Un PDF Nuevo o Convirtiéndose también se acepta: el pedido lo convierte primero y luego lo extrae.
EXTRAIBLES = (EstadoArticulo.NUEVO, EstadoArticulo.CONVIRTIENDO, EstadoArticulo.LISTO, EstadoArticulo.HEREDADO,
              EstadoArticulo.ERROR, EstadoArticulo.POR_REVISAR)
SIN_ACTIVIDAD_S = 30 * 60  # una extracción en curso sin avanzar tanto tiempo se da por colgada


class ArticuloAExtraer(BaseModel):
    articulo_id: uuid.UUID
    documento: int = Field(ge=1, description="número del artículo en la matriz (columna A)")
    estudio: int | None = Field(None, ge=1)
    covidence: int | None = Field(None, ge=1)
    via: str = "Covidence"


class PedidoDeLote(BaseModel):
    articulos: list[ArticuloAExtraer] = Field(min_length=1)
    confirmar_reextraccion: bool = False
    motivo: str | None = None


def _contenedor(request: Request) -> Contenedor:
    c: Contenedor = request.app.state.contenedor
    return c


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _avance_de(e: Extraccion) -> dict[str, Any]:
    _, hasta, tipicos, texto = PASOS.get(e.paso, PASOS["preparando"])
    inactiva = (not e.terminada) and (ahora() - _aware(e.paso_desde)).total_seconds() > SIN_ACTIVIDAD_S
    return {
        "extraccion_id": str(e.id), "articulo_id": str(e.articulo_id), "estado": e.estado.value,
        "progreso": e.progreso, "paso": e.paso, "paso_texto": texto, "hasta": hasta, "segundos_tipicos": tipicos,
        "paso_desde": _aware(e.paso_desde).isoformat(), "iniciada_en": _aware(e.iniciada_en).isoformat(),
        "terminada_en": _aware(e.terminada_en).isoformat() if e.terminada_en else None,
        "error": e.error, "inactiva": inactiva, "fallida": e.estado == EstadoExtraccion.FALLIDA,
        "costo_usd": round(sum(float(r.get("costo_usd") or 0) for r in e.uso_tokens.values()), 2),
        "estudios": e.estudios_reservados, "acuerdo": e.acuerdo_campos_criticos,
    }


@enrutador.get("/extracciones/avance")
def avance(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
           _: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    c = _contenedor(request)
    ultimas: dict[uuid.UUID, Extraccion] = {}  # una por artículo: la más reciente
    for e in c.extraccion.consultas.recientes(proyecto_id):
        ultimas[e.articulo_id] = e
    en_cola = c.ejecutor.pendientes(proyecto_id)
    return {"extracciones": [_avance_de(e) for e in ultimas.values()],
            "en_cola": [{"articulo_id": str(p.articulo_id), "posicion": p.posicion, "fase": p.fase,
                         "desde": datetime.fromtimestamp(p.desde, UTC).isoformat()} for p in en_cola]}


@enrutador.post("/extracciones")
def extraer(datos: PedidoDeLote, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            _: Usuario = Depends(usuario_actual)) -> list[dict[str, Any]]:
    c = _contenedor(request)
    return [_encolar(c, proyecto_id, a, datos.confirmar_reextraccion, datos.motivo) for a in datos.articulos]


class PedidoDeRetomar(BaseModel):
    articulos: list[uuid.UUID] = Field(min_length=1)


@enrutador.post("/extracciones/retomar")
def retomar(datos: PedidoDeRetomar, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            _: Usuario = Depends(usuario_actual)) -> list[dict[str, Any]]:
    """«Extraer» sobre un artículo en Error: lo vuelve a lanzar con los datos del equipo de su último intento."""
    c = _contenedor(request)
    resultado: list[dict[str, Any]] = []
    for articulo_id in datos.articulos:
        previos = [e.datos_del_equipo for e in c.extraccion.consultas.de_articulo(proyecto_id, articulo_id)
                   if e.datos_del_equipo.get("documento")]
        if not previos:
            resultado.append({"articulo_id": str(articulo_id), "encolado": False, "sin_datos": True,
                              "error": "No hay un intento anterior con sus datos: indíquelos con «Extraer seleccionados»"})
            continue
        d = previos[-1]
        a = ArticuloAExtraer(articulo_id=articulo_id, documento=d["documento"], estudio=d.get("estudio_inicial"),
                             covidence=d.get("covidence"), via=d.get("via") or "Covidence")
        item = _encolar(c, proyecto_id, a, False, None)
        item["sin_datos"] = a.covidence is None and a.via == "Covidence"  # falta el Covidence #: hay que indicarlo
        resultado.append(item)
    return resultado


def _encolar(c: Contenedor, proyecto_id: uuid.UUID, a: ArticuloAExtraer, confirmar_reextraccion: bool,
             motivo: str | None) -> dict[str, Any]:
    item: dict[str, Any] = {"articulo_id": str(a.articulo_id), "encolado": False, "error": None}
    try:
        articulo = c.biblioteca.consultas.articulo(proyecto_id, a.articulo_id)
        if articulo.estado not in EXTRAIBLES:
            raise ErrorDeDominio(f"«{articulo.nombre_archivo}» está en estado {articulo.estado.value} y no se "
                                 "puede extraer ahora")
        if articulo.estado == EstadoArticulo.POR_REVISAR and not confirmar_reextraccion:
            raise ErrorDeDominio(f"«{articulo.nombre_archivo}» ya tiene filas por revisar: confirme la reextracción")
        if a.covidence is None and a.via == "Covidence":  # V06: el modelo no puede corregirlo
            raise ErrorDeDominio(f"«{articulo.nombre_archivo}»: falta Covidence #. Indíquelo, o elija otra vía "
                                 "de identificación si el artículo no pasó por Covidence")
        opciones = OpcionesDeExtraccion(documento=a.documento, estudio_inicial=a.estudio, covidence=a.covidence,
                                        via=a.via, confirmar_reextraccion=confirmar_reextraccion, motivo=motivo)
        item["posicion"] = c.ejecutor.encolar(
            PedidoDeExtraccion(proyecto_id, a.articulo_id, articulo.nombre_archivo, opciones)) + 1
        item["encolado"] = True
    except (ErrorDeDominio, LookupError) as e:
        item["error"] = str(e)
    return item

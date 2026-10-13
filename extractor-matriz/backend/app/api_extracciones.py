"""Lanzar extracciones desde la interfaz y consultar su avance.

POST /extracciones           encola artículos (corren en segundo plano, uno tras otro)
POST /extracciones/retomar   vuelve a lanzar artículos en Error con los datos de su último intento
POST /extracciones/continuar termina los artículos detenidos (a medias sin trabajo activo), sin restablecerlos
POST /extracciones/{id}/cancelar  saca de la cola un artículo que todavía no empezó a extraer
GET  /extracciones/avance    extracciones en curso o terminadas hace poco, con porcentaje y paso actual,
                             más los artículos que esperan en cola
GET  /extracciones/modelos   qué modelo atendió cada rol en la última extracción de cada artículo (ADR 0005)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
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
# Estados intermedios: un artículo en uno de ellos sin trabajo activo en el ejecutor está detenido.
INTERMEDIOS = (EstadoArticulo.CONVIRTIENDO, EstadoArticulo.EN_COLA, EstadoArticulo.EXTRAYENDO,
               EstadoArticulo.AUDITANDO)


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
    pausados = {p.articulo_id for p in en_cola if p.fase == "pausada"}  # su último intento no es un fallo
    return {"detenidos": [str(a.id) for a in _detenidos(c, proyecto_id)],
            "extracciones": [_avance_de(e) for a, e in ultimas.items() if a not in pausados],
            "en_cola": [{"articulo_id": str(p.articulo_id), "posicion": p.posicion, "fase": p.fase,
                         "desde": datetime.fromtimestamp(p.desde, UTC).isoformat(),
                         "reanuda": datetime.fromtimestamp(p.reanuda, UTC).isoformat() if p.reanuda else None}
                        for p in en_cola]}


ROLES = ("extractor", "auditor", "ciego", "conciliador")


def _modelos_de(e: Extraccion) -> dict[str, Any]:
    """Por rol: {modelo: llamadas}. None si la extracción es anterior al portero y no guardó el modelo por llamada."""
    roles = {rol: (e.uso_tokens[rol].get("modelos") if rol in e.uso_tokens else {}) for rol in ROLES}
    return {"extraccion_id": str(e.id), "estado": e.estado.value, "iniciada_en": _aware(e.iniciada_en).isoformat(),
            "registrado": any(roles.values()), "roles": roles}


@enrutador.get("/extracciones/modelos")
def modelos(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            _: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    c = _contenedor(request)
    return {str(a): _modelos_de(e) for a, e in c.extraccion.consultas.ultimas_por_articulo(proyecto_id).items()}


@enrutador.post("/extracciones")
def extraer(datos: PedidoDeLote, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            _: Usuario = Depends(usuario_actual)) -> list[dict[str, Any]]:
    c = _contenedor(request)
    _respetar_tope(c, proyecto_id, len(datos.articulos))
    return [_encolar(c, proyecto_id, a, datos.confirmar_reextraccion, datos.motivo) for a in datos.articulos]


def _respetar_tope(c: Contenedor, proyecto_id: uuid.UUID, articulos: int) -> None:
    """Con TOPE_TOKENS_MENSUAL definido, rechaza el lote entero si lo usado este mes más lo estimado lo supera
    (sección 11)."""
    tope = c.ajustes.tope_tokens_mensual
    if tope is None:
        return
    usados = c.extraccion.consultas.tokens_del_mes(proyecto_id)
    estimado = articulos * c.extraccion.consultas.tokens_por_articulo(proyecto_id)
    if usados + estimado > tope:
        raise HTTPException(status_code=409, detail=(
            f"El lote supera el tope mensual de tokens: este mes van {usados:,} y {articulos} artículo(s) "
            f"suman unos {estimado:,} más; el tope es {tope:,}. Extraiga menos artículos o suba "
            "TOPE_TOKENS_MENSUAL.").replace(",", "."))


class PedidoDeRetomar(BaseModel):
    articulos: list[uuid.UUID] = Field(min_length=1)


@enrutador.post("/extracciones/retomar")
def retomar(datos: PedidoDeRetomar, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            _: Usuario = Depends(usuario_actual)) -> list[dict[str, Any]]:
    """«Extraer» sobre un artículo en Error: lo vuelve a lanzar con los datos del equipo de su último intento."""
    c = _contenedor(request)
    _respetar_tope(c, proyecto_id, len(datos.articulos))
    return [_relanzar(c, proyecto_id, articulo_id) for articulo_id in datos.articulos]


def _relanzar(c: Contenedor, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> dict[str, Any]:
    """Encola de nuevo la extracción con los datos del equipo de su último intento."""
    previos = [e.datos_del_equipo for e in c.extraccion.consultas.de_articulo(proyecto_id, articulo_id)
               if e.datos_del_equipo.get("documento")]
    if not previos:
        return {"articulo_id": str(articulo_id), "encolado": False, "sin_datos": True,
                "error": "No hay un intento anterior con sus datos: indíquelos con «Extraer seleccionados»"}
    d = previos[-1]
    a = ArticuloAExtraer(articulo_id=articulo_id, documento=d["documento"], estudio=d.get("estudio_inicial"),
                         covidence=d.get("covidence"), via=d.get("via") or "Covidence")
    item = _encolar(c, proyecto_id, a, False, None)
    item["sin_datos"] = a.covidence is None and a.via == "Covidence"  # falta el Covidence #: hay que indicarlo
    return item


def _detenidos(c: Contenedor, proyecto_id: uuid.UUID) -> list[Any]:
    """Artículos a medias (convirtiendo, en cola, extrayendo o auditando) sin trabajo activo en el ejecutor."""
    return [a for estado in INTERMEDIOS for a in c.biblioteca.consultas.listar(proyecto_id, estado).articulos
            if not c.ejecutor.activo(a.id)]


class PedidoDeContinuar(BaseModel):
    articulos: list[uuid.UUID] | None = None  # None: todos los detenidos


@enrutador.post("/extracciones/continuar")
def continuar(datos: PedidoDeContinuar, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
              _: Usuario = Depends(usuario_actual)) -> list[dict[str, Any]]:
    """Termina lo que quedó a medias, sin restablecer (ADR 0006).

    - Conversión cortada: se termina con MinerU en segundo plano; el artículo queda Convertido. No gasta créditos.
    - Extracción cortada: el intento colgado se cierra como interrumpido y la extracción se vuelve a encolar con los
      datos del equipo de su último intento (la llamada al modelo no se puede retomar a medias). Gasta créditos.
    """
    c = _contenedor(request)
    pedidos = set(datos.articulos) if datos.articulos is not None else None
    detenidos = [a for a in _detenidos(c, proyecto_id) if pedidos is None or a.id in pedidos]
    _respetar_tope(c, proyecto_id, sum(1 for a in detenidos if a.estado != EstadoArticulo.CONVIRTIENDO))
    resultado: list[dict[str, Any]] = []
    for articulo in detenidos:
        if articulo.estado == EstadoArticulo.CONVIRTIENDO:
            if c.mineru() is None:
                resultado.append({"articulo_id": str(articulo.id), "accion": "convertir", "encolado": False,
                                  "error": f"«{articulo.nombre_archivo}»: MinerU no responde; ábralo y vuelva a pulsar"})
                continue
            c.terminar_conversion(proyecto_id, articulo.id)
            resultado.append({"articulo_id": str(articulo.id), "accion": "convertir", "encolado": True, "error": None})
            continue
        # La extracción colgada se cierra: el artículo pasa a Error con el paso que falló y la nueva lo retoma.
        c.extraccion.extraer.cerrar_interrumpidas({articulo.id}, float("inf"))
        estado = c.biblioteca.consultas.articulo(proyecto_id, articulo.id).estado
        if estado in INTERMEDIOS:  # sin extracción abierta (p. ej. pausada y la aplicación se cerró)
            c.biblioteca.extraccion.fallar(proyecto_id, articulo.id, estado,
                                           "Interrumpida: quedó a medias sin trabajo activo")
        item = _relanzar(c, proyecto_id, articulo.id)
        item["accion"] = "extraer"
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


@enrutador.post("/extracciones/{articulo_id}/cancelar")
def cancelar(articulo_id: uuid.UUID, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             _: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    """Cancela un pedido en cola, convirtiéndose o esperando a MinerU. Uno que ya extrae no se corta."""
    c = _contenedor(request)
    c.biblioteca.consultas.articulo(proyecto_id, articulo_id)  # 404 si no es del proyecto
    nombre = c.ejecutor.cancelar(articulo_id)  # 409 si no está en cola o ya extrae
    return {"articulo_id": str(articulo_id), "cancelado": True, "nombre": nombre}

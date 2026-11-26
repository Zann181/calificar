"""Rutas de Sincronización.

Locales (MODO=local): `/proyectos/{id}/sincronizacion/*`, el panel «Configuración › Nube» (sección 7).
De la nube (MODO=nube): `/sync/*`, solo con el token de servicio del agente (sección 6.3).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.compartido.seguridad import proyecto_valido
from app.compartido.sobre import ESQUEMA, Sobre
from app.contextos.sincronizacion.adaptadores.cliente_http import validar_url
from app.contextos.sincronizacion.aplicacion.ingesta import EsquemaDesconocido, Ingesta, LoteInvalido
from app.contextos.sincronizacion.aplicacion.sincronizador import SinConfigurar
from app.contextos.sincronizacion.dominio.plan import (
    ConflictoDeInstalacion,
    ErrorDeSincronizacion,
    Opciones,
    normalizar_correo,
)
from app.contextos.sincronizacion.puertos import Destino

# ----------------------------------------------------------------------------------------------------- locales


class CorreoNuevo(BaseModel):
    correo: str

local = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}/sincronizacion", tags=["sincronización"])


def _c(request: Request) -> Any:
    return request.app.state.contenedor


def _ajustes_json(c: Any, d: Destino) -> dict[str, Any]:
    return {"url": d.url, "automatico": d.automatico, "pausado": d.pausado, "agrupar_s": d.agrupar_s,
            "reconciliar_s": d.reconciliar_s, "opciones": d.opciones.a_dict(), "sede": d.sede,
            "token_guardado": bool(c.credenciales.token(d.proyecto_id))}  # nunca el token


class AjustesNuevos(BaseModel):
    url: str | None = None
    token: str | None = None  # solo escritura: vacío o ausente = no cambia
    automatico: bool | None = None
    pausado: bool | None = None
    agrupar_s: int | None = Field(None, ge=1, le=300)
    reconciliar_s: int | None = Field(None, ge=30, le=86400)
    opciones: dict[str, bool] | None = None


@local.get("/ajustes")
def ver_ajustes(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    c = _c(request)
    return _ajustes_json(c, c.destinos.obtener(proyecto_id) or Destino(proyecto_id=proyecto_id))


@local.put("/ajustes")
def guardar_ajustes(datos: AjustesNuevos, request: Request,
                    proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    c = _c(request)
    d = c.destinos.obtener(proyecto_id) or Destino(proyecto_id=proyecto_id, instalacion_id=uuid.uuid4().hex)
    if not d.instalacion_id:
        d = replace(d, instalacion_id=uuid.uuid4().hex)
    if datos.url is not None:
        url = datos.url.strip()
        if url:
            try:
                url = validar_url(url)
            except ErrorDeSincronizacion as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        d = replace(d, url=url)
    for campo in ("automatico", "pausado", "agrupar_s", "reconciliar_s"):
        valor = getattr(datos, campo)
        if valor is not None:
            d = replace(d, **{campo: valor})
    if datos.opciones is not None:
        d = replace(d, opciones=Opciones.desde_dict({**d.opciones.a_dict(), **datos.opciones}))
    c.destinos.guardar(d)
    if datos.token:
        c.credenciales.guardar(proyecto_id, datos.token.strip())
    if d.url and not d.pausado:
        c.agente.notificar(proyecto_id)
    return _ajustes_json(c, d)


@local.delete("/token")
def borrar_token(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, bool]:
    _c(request).credenciales.borrar(proyecto_id)
    return {"token_guardado": False}


@local.post("/probar")
def probar(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    """Comprueba URL, token, versión de esquema, nube despierta y base disponible, y dice qué falló."""
    c = _c(request)
    pasos: list[dict[str, Any]] = []

    def paso(nombre: str, ok: bool, detalle: str = "") -> bool:
        pasos.append({"nombre": nombre, "ok": ok, "detalle": detalle})
        return ok

    d = c.destinos.obtener(proyecto_id)
    if d is None or not d.url:
        paso("URL de la nube", False, "Escriba la URL de la nube (https://….onrender.com)")
        return {"ok": False, "pasos": pasos}
    try:
        validar_url(d.url)
        paso("URL de la nube", True, d.url)
    except ErrorDeSincronizacion as e:
        paso("URL de la nube", False, str(e))
        return {"ok": False, "pasos": pasos}
    if not paso("Token de sincronización", bool(c.credenciales.token(proyecto_id)),
                "Guardado en el Administrador de credenciales" if c.credenciales.token(proyecto_id)
                else "Falta el token: péguelo y guarde"):
        return {"ok": False, "pasos": pasos}
    try:
        salud = c.sincronizador.conectar(proyecto_id)[1].salud()
    except ErrorDeSincronizacion as e:
        if e.codigo == 401:
            paso("Nube despierta", True, "La nube respondió")
            paso("Token aceptado", False, str(e))
        else:
            paso("Nube despierta", False, str(e) + (" Si Render estaba dormido, reintente en un minuto."
                                                    if e.reintentable else ""))
        return {"ok": False, "pasos": pasos}
    paso("Nube despierta", True, "La nube respondió")
    paso("Token aceptado", True)
    esquema = int(salud.get("esquema", 0))
    paso("Versión de esquema", esquema >= ESQUEMA,
         f"Nube con esquema {esquema}, equipo con {ESQUEMA}" if esquema < ESQUEMA else f"Esquema {esquema}")
    paso("Base de datos", salud.get("base") == "ok", str(salud.get("base_detalle") or "Disponible"))
    return {"ok": all(p["ok"] for p in pasos), "pasos": pasos, "revision": salud.get("revision")}


@local.post("/ahora")
def sincronizar_ahora(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    c = _c(request)
    _exigir_configurada(c, proyecto_id)
    c.agente.ahora(proyecto_id)
    return {"aceptado": True}


@local.post("/reenviar")
def reenviar_todo(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    """Vuelve a mandar todo y toma el control de la nube (si otro equipo la sincronizaba)."""
    c = _c(request)
    _exigir_configurada(c, proyecto_id)
    c.agente.ahora(proyecto_id, todo=True, tomar_control=True)
    return {"aceptado": True}


@local.post("/verificar")
def verificar(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    """Compara el equipo con la nube sin enviar nada."""
    c = _c(request)
    try:
        plan = c.sincronizador.pendientes(proyecto_id)
    except SinConfigurar as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ErrorDeSincronizacion as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": plan.vacio, "por_subir": len(plan.subir), "por_eliminar": len(plan.eliminar),
            "archivos": len(plan.archivos),
            "detalle": "El equipo y la nube coinciden" if plan.vacio else "Hay diferencias: pulse «Sincronizar ahora»"}


@local.get("/estado")
def estado(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    resultado: dict[str, Any] = _c(request).agente.estado(proyecto_id).a_dict()
    return resultado


@local.get("/corridas")
def corridas(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> list[dict[str, Any]]:
    return [{"id": str(k.id), "iniciada_en": _utc(k.iniciada_en),
             "terminada_en": _utc(k.terminada_en) if k.terminada_en else None, "motivo": k.motivo,
             "estado": k.estado, "sobres": k.sobres, "eliminados": k.eliminados, "archivos": k.archivos,
             "bytes_enviados": k.bytes_enviados, "revision": k.revision, "detalle": k.detalle}
            for k in _c(request).destinos.ultimas(proyecto_id)]


def _con_nube(c: Any, proyecto_id: uuid.UUID, accion: Any) -> dict[str, Any]:
    _exigir_configurada(c, proyecto_id)
    try:
        resultado: dict[str, Any] = accion(c.sincronizador.conectar(proyecto_id)[1])
        return resultado
    except ErrorDeSincronizacion as e:
        raise HTTPException(status_code=409 if e.codigo == 409 else 502, detail=str(e)) from e


@local.get("/lectores")
def lectores(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    """Quién puede entrar al visor de la nube: los fijos (variable de Render) y los agregados desde aquí."""
    return _con_nube(_c(request), proyecto_id, lambda n: n.lectores())


@local.post("/lectores")
def alta_de_lector(datos: CorreoNuevo, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    return _con_nube(_c(request), proyecto_id, lambda n: n.agregar_lector(datos.correo))


@local.delete("/lectores")
def baja_de_lector(correo: str, request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    return _con_nube(_c(request), proyecto_id, lambda n: n.quitar_lector(correo))


class PedidoDeRestauracion(BaseModel):
    reemplazar: bool = False


@local.post("/restaurar/plan")
def plan_de_restauracion(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    """Qué bajaría «Descargar proyecto desde la nube»: lo que falta, lo que difiere y lo que solo hay aquí."""
    c = _c(request)
    _exigir_configurada(c, proyecto_id)
    try:
        resultado: dict[str, Any] = c.agente.plan_de_restauracion(proyecto_id)
        return resultado
    except ErrorDeSincronizacion as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@local.post("/restaurar")
def restaurar(datos: PedidoDeRestauracion, request: Request,
              proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, bool]:
    """Baja el proyecto de la nube en segundo plano (nunca borra nada local). Sin `reemplazar`, se rehúsa si hay
    diferencias."""
    c = _c(request)
    _exigir_configurada(c, proyecto_id)
    c.agente.restaurar(proyecto_id, reemplazar=datos.reemplazar)
    return {"aceptado": True}


@local.get("/restaurar/estado")
def estado_de_restauracion(request: Request, proyecto_id: uuid.UUID = Depends(proyecto_valido)) -> dict[str, Any]:
    resultado: dict[str, Any] = _c(request).agente.estado_de_restauracion(proyecto_id)
    return resultado


def _utc(t: datetime) -> str:
    """SQLite devuelve las fechas sin zona: son UTC, y el navegador debe saberlo."""
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def _exigir_configurada(c: Any, proyecto_id: uuid.UUID) -> None:
    d = c.destinos.obtener(proyecto_id)
    if d is None or not d.url or not c.credenciales.token(proyecto_id):
        raise HTTPException(status_code=409, detail="Falta la URL de la nube o el token de sincronización")


# ------------------------------------------------------------------------------------------------------- nube
nube = APIRouter(prefix="/api/v1/sync", tags=["sincronización (nube)"])


def hash_de_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def servicio_autenticado(request: Request) -> None:
    """Solo el agente, con el token de servicio. Un lector con sesión NO pasa por aquí (y el token no lee la API)."""
    esperado = _c(request).ajustes.sync_token_hash
    cab = request.headers.get("authorization", "")
    token = cab[7:].strip() if cab.lower().startswith("bearer ") else ""
    if not esperado or not token or not hmac.compare_digest(hash_de_token(token), esperado.lower()):
        raise HTTPException(status_code=401, detail="Token de sincronización inválido")


def _ingesta(request: Request) -> Ingesta:
    i: Ingesta = _c(request).ingesta
    return i


@nube.get("/salud")
def salud_sync(request: Request, _: None = Depends(servicio_autenticado),
               i: Ingesta = Depends(_ingesta)) -> dict[str, Any]:
    try:
        rev = i.revision()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"La base de datos no responde: {type(e).__name__}") from e
    return {"modo": "nube", "esquema": ESQUEMA, "revision": rev, "base": "ok"}


@nube.get("/manifiesto")
def manifiesto(proyecto: uuid.UUID, _: None = Depends(servicio_autenticado),
               i: Ingesta = Depends(_ingesta)) -> dict[str, Any]:
    m = i.manifiesto(proyecto)
    return {"revision": m.revision, "items": m.items, "archivos": m.archivos}


@nube.get("/pendientes")
def pendientes_de_recoger(proyecto: uuid.UUID, _: None = Depends(servicio_autenticado),
                          i: Ingesta = Depends(_ingesta)) -> dict[str, Any]:
    return {"paquetes": i.pendientes(proyecto)}


@nube.put("/archivos")
async def subir_archivo(request: Request, clave: str, _: None = Depends(servicio_autenticado),
                        i: Ingesta = Depends(_ingesta)) -> dict[str, Any]:
    sha = request.headers.get("x-sha256", "")
    datos = await request.body()
    try:
        i.recibir_archivo(clave, sha, datos)
    except LoteInvalido as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"clave": clave, "tamano": len(datos)}


@nube.get("/proyectos")
def proyectos_de_la_nube(_: None = Depends(servicio_autenticado), i: Ingesta = Depends(_ingesta)) -> list[dict[str, str]]:
    return i.proyectos()


@nube.get("/sobres")
def bajar_sobres(proyecto: uuid.UUID, tipo: str, _: None = Depends(servicio_autenticado),
                 i: Ingesta = Depends(_ingesta)) -> StreamingResponse:
    """Los sobres de un tipo, uno por línea (NDJSON): el equipo los aplica sin cargar todo en memoria."""
    try:
        sobres = i.sobres_de(proyecto, tipo)
    except LoteInvalido as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return StreamingResponse((json.dumps(s.a_json(), ensure_ascii=False) + "\n" for s in sobres),
                             media_type="application/x-ndjson")


@nube.get("/archivos")
def bajar_archivo(clave: str, _: None = Depends(servicio_autenticado), i: Ingesta = Depends(_ingesta)) -> Response:
    try:
        datos, sha = i.leer_archivo(clave)
    except LoteInvalido as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"No existe el archivo {clave}") from e
    return Response(datos, media_type="application/octet-stream", headers={"X-Sha256": sha})


def _lectores_json(c: Any) -> dict[str, Any]:
    return {"fijos": sorted(c.ajustes.lectores),
            "agregados": [{"correo": k, "agregado_en": _utc(t)} for k, t in c.lectores.agregados()]}


@nube.get("/lectores")
def ver_lectores(request: Request, _: None = Depends(servicio_autenticado)) -> dict[str, Any]:
    return _lectores_json(_c(request))


@nube.put("/lectores")
def agregar_lector(datos: CorreoNuevo, request: Request, _: None = Depends(servicio_autenticado)) -> dict[str, Any]:
    c = _c(request)
    try:
        correo = normalizar_correo(datos.correo)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    c.lectores.agregar(correo)
    return _lectores_json(c)


@nube.delete("/lectores")
def quitar_lector(correo: str, request: Request, _: None = Depends(servicio_autenticado)) -> dict[str, Any]:
    c = _c(request)
    try:
        correo = normalizar_correo(correo)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if correo in c.ajustes.lectores:
        raise HTTPException(status_code=409, detail=f"{correo} es un lector fijo (variable LECTORES_PERMITIDOS de la "
                                                    "nube): se quita allí, no desde el panel")
    c.lectores.quitar(correo)
    return _lectores_json(c)


class LoteEnviado(BaseModel):
    esquema: int
    sobres: list[dict[str, Any]]


@nube.put("/lote")
def aplicar_lote(datos: LoteEnviado, request: Request, _: None = Depends(servicio_autenticado),
                 i: Ingesta = Depends(_ingesta)) -> dict[str, Any]:
    try:
        r = i.aplicar_lote(
            [Sobre.desde_json(s) for s in datos.sobres], esquema=datos.esquema,
            instalacion=request.headers.get("x-instalacion"),
            tomar_control=request.headers.get("x-tomar-control") == "1",
            clave_idempotencia=request.headers.get("idempotency-key"))
    except EsquemaDesconocido as e:
        raise HTTPException(status_code=426, detail=str(e)) from e
    except LoteInvalido as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConflictoDeInstalacion as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"revision": r.revision, "aplicados": r.aplicados, "iguales": r.iguales}

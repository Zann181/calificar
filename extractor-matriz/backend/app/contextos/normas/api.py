"""Router /normas."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.compartido.seguridad import proyecto_valido
from app.contextos.normas.aplicacion.casos_de_uso import CasosDeNormas
from app.contextos.normas.dominio.modelos import VersionDelLibro

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}/normas", tags=["normas"])


def casos(request: Request) -> CasosDeNormas:
    c: CasosDeNormas = request.app.state.contenedor.normas
    return c


def _version_json(v: VersionDelLibro) -> dict[str, Any]:
    return {"id": str(v.id), "version": v.version, "hash": v.hash, "activa": v.activa,
            "publicada_en": v.publicada_en.isoformat() if v.publicada_en else None}


@enrutador.get("/columnas")
def columnas(proyecto_id: uuid.UUID = Depends(proyecto_valido), c: CasosDeNormas = Depends(casos)) -> list[dict[str, Any]]:
    return [col.a_dict() for col in c.consultas.columnas(proyecto_id)]


@enrutador.get("/protocolo")
def protocolo(proyecto_id: uuid.UUID = Depends(proyecto_valido), c: CasosDeNormas = Depends(casos)) -> dict[str, Any]:
    return c.consultas.protocolo(proyecto_id)


@enrutador.get("/libros")
def versiones(proyecto_id: uuid.UUID = Depends(proyecto_valido), c: CasosDeNormas = Depends(casos)) -> list[dict[str, Any]]:
    return [_version_json(v) for v in c.consultas.versiones(proyecto_id)]


@enrutador.post("/libros")
async def publicar(archivo: UploadFile = File(...), proyecto_id: uuid.UUID = Depends(proyecto_valido),
                   c: CasosDeNormas = Depends(casos)) -> dict[str, Any]:
    try:
        contenido = json.loads(await archivo.read())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"El libro no es JSON válido: {e}") from e
    return _version_json(c.publicar.ejecutar(proyecto_id, contenido))

"""Router /articulos."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

from app.compartido.seguridad import proyecto_valido
from app.contextos.biblioteca.adaptadores.repositorio_sql import a_json
from app.contextos.biblioteca.aplicacion.casos_de_uso import CasosDeBiblioteca
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}", tags=["biblioteca"])


def casos(request: Request) -> CasosDeBiblioteca:
    c: CasosDeBiblioteca = request.app.state.contenedor.biblioteca
    return c


class Motivo(BaseModel):
    motivo: str


@enrutador.post("/articulos")
async def cargar(archivos: list[UploadFile] = File(...), proyecto_id: uuid.UUID = Depends(proyecto_valido),
                 c: CasosDeBiblioteca = Depends(casos)) -> list[dict[str, Any]]:
    resultados = []
    for archivo in archivos:
        r = c.cargar.ejecutar(proyecto_id, archivo.filename or "sin_nombre.pdf", await archivo.read())
        resultados.append({
            "nombre_archivo": r.nombre_archivo, "articulo_id": str(r.articulo_id) if r.articulo_id else None,
            "duplicado": r.duplicado, "duplicado_de": r.duplicado_de, "error": r.error,
        })
    return resultados


@enrutador.get("/articulos")
def listar(estado: EstadoArticulo | None = None, proyecto_id: uuid.UUID = Depends(proyecto_valido),
           c: CasosDeBiblioteca = Depends(casos)) -> dict[str, Any]:
    listado = c.consultas.listar(proyecto_id, estado)
    return {"articulos": [a_json(a) for a in listado.articulos], "contadores": listado.contadores}


@enrutador.get("/articulos/{articulo_id}")
def detalle(articulo_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            c: CasosDeBiblioteca = Depends(casos)) -> dict[str, Any]:
    return a_json(c.consultas.articulo(proyecto_id, articulo_id))


@enrutador.post("/articulos/{articulo_id}/excluir")
def excluir(articulo_id: uuid.UUID, datos: Motivo, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            c: CasosDeBiblioteca = Depends(casos)) -> dict[str, Any]:
    return a_json(c.excluir.ejecutar(proyecto_id, articulo_id, datos.motivo))


@enrutador.post("/articulos/{articulo_id}/reactivar")
def reactivar(articulo_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
              c: CasosDeBiblioteca = Depends(casos)) -> dict[str, Any]:
    return a_json(c.reactivar.ejecutar(proyecto_id, articulo_id))


@enrutador.get("/articulos/{articulo_id}/pdf")
def pdf(articulo_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
        c: CasosDeBiblioteca = Depends(casos)) -> Response:
    articulo = c.consultas.articulo(proyecto_id, articulo_id)
    url = c.almacen.url_temporal(articulo.clave_almacen)
    if url.startswith(("http://", "https://")):
        return RedirectResponse(url, status_code=307)
    # Almacén en disco o en memoria: no hay URL firmada, la API entrega el PDF.
    return Response(c.almacen.leer(articulo.clave_almacen), media_type="application/pdf")


@enrutador.get("/articulos/{articulo_id}/documento")
def documento(articulo_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
              c: CasosDeBiblioteca = Depends(casos)) -> dict[str, Any]:
    return c.consultas.documento(proyecto_id, articulo_id).a_dict()

"""Router /exportaciones."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.compartido.seguridad import proyecto_valido
from app.contextos.exportacion.aplicacion.casos_de_uso import TIPO_XLSX, ExportarMatriz

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}/exportaciones", tags=["exportación"])


def caso(request: Request) -> ExportarMatriz:
    c: ExportarMatriz = request.app.state.contenedor.exportar
    return c


@enrutador.post("")
def generar(proyecto_id: uuid.UUID = Depends(proyecto_valido), c: ExportarMatriz = Depends(caso)) -> dict[str, Any]:
    e = c.ejecutar(proyecto_id)
    return {"id": str(e.id), "filas_heredadas": e.filas_heredadas, "filas_extraidas": e.filas_extraidas,
            "descarga": f"/api/v1/proyectos/{proyecto_id}/exportaciones/{e.id}"}


@enrutador.get("/{exportacion_id}")
def descargar(exportacion_id: uuid.UUID, proyecto_id: uuid.UUID = Depends(proyecto_valido),
              c: ExportarMatriz = Depends(caso)) -> Response:
    datos = c.leer(proyecto_id, exportacion_id)
    return Response(datos, media_type=TIPO_XLSX, headers={
        "Content-Disposition": f'attachment; filename="Matriz_de_sintesis_{exportacion_id.hex[:8]}.xlsx"'})

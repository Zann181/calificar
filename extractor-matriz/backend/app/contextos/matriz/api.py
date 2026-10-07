"""Router /matriz e /importaciones."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel

from app.compartido.seguridad import Usuario, proyecto_valido, usuario_actual
from app.contextos.matriz.aplicacion.casos_de_uso import CasosDeMatriz
from app.contextos.matriz.dominio.fila import Celda, FilaDeEfecto

enrutador = APIRouter(prefix="/api/v1/proyectos/{proyecto_id}", tags=["matriz"])


def casos(request: Request) -> CasosDeMatriz:
    c: CasosDeMatriz = request.app.state.contenedor.matriz
    return c


def _columnas_de(lista: Any, campo: str) -> set[str]:
    return {str(x.get(campo)) for x in lista or [] if isinstance(x, dict)}


def _hallazgos(fila: FilaDeEfecto, clave: str) -> list[dict[str, Any]]:
    """Hallazgos de auditoría de la celda que siguen pendientes."""
    return [h for h in fila.trazabilidad.get("auditoria", []) or []
            if isinstance(h, dict) and h.get("columna") == clave and h.get("estado", "Pendiente") == "Pendiente"]


def _discrepancias(fila: FilaDeEfecto, clave: str) -> list[dict[str, Any]]:
    salida = fila.trazabilidad.get("salida") or {}
    lista = (salida.get("trazabilidad") or {}).get("discrepancias_en_el_articulo") or []
    return [d for d in lista if isinstance(d, dict) and d.get("columna") == clave]


def _celda_resumen(fila: FilaDeEfecto, c: Celda) -> dict[str, Any]:
    return {
        "valor": c.valor, "estado_dato": c.estado_dato,
        "tipo_valor": c.tipo_valor.value if c.tipo_valor else None,
        "estado_revision": c.estado_revision.value,
        "nivel_ancla": c.nivel_ancla,
        "evidencias": len(c.evidencias),
        "discrepancia": bool(_discrepancias(fila, c.clave)),
        "hallazgo": bool(_hallazgos(fila, c.clave)),
        "nota_heredada": c.clave in fila.trazabilidad.get("notas_heredadas", {}),
        "fuera_de_vocabulario": c.clave in fila.trazabilidad.get("fuera_de_vocabulario", []),
    }


def _fila_json(f: FilaDeEfecto) -> dict[str, Any]:
    return {
        "id": str(f.id), "estudio": f.estudio, "documento": f.documento, "origen": f.origen.value,
        "articulo_id": str(f.articulo_id) if f.articulo_id else None, "aprobada": f.aprobada,
        "version_desactualizada": f.version_desactualizada,
        "celdas": {k: _celda_resumen(f, c) for k, c in f.celdas.items()},
    }


@enrutador.get("/matriz/filas")
def filas(pagina: int = 1, tam: int = 100, documento: int | None = None,
          proyecto_id: uuid.UUID = Depends(proyecto_valido), c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    lista, total = c.consultas.pagina(proyecto_id, pagina=pagina, tam=tam, documento=documento)
    return {"total": total, "pagina": pagina, "tam": tam, "filas": [_fila_json(f) for f in lista]}


@enrutador.get("/matriz/filas/{estudio}/celdas/{clave}")
def celda(estudio: int, clave: str, proyecto_id: uuid.UUID = Depends(proyecto_valido),
          c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    fila = c.consultas.fila(proyecto_id, estudio)
    cel = fila.celda(clave)
    return {
        "estudio": fila.estudio, "documento": fila.documento, "origen": fila.origen.value, "clave": clave,
        "articulo_id": str(fila.articulo_id) if fila.articulo_id else None,
        **_celda_resumen(fila, cel),
        "evidencias": [asdict(e) for e in cel.evidencias],
        "inferencia": asdict(cel.inferencia) if cel.inferencia else None,
        "nota_heredada": fila.trazabilidad.get("notas_heredadas", {}).get(clave),
        "hallazgos": _hallazgos(fila, clave),
        "discrepancias": _discrepancias(fila, clave),
        "historial": [{**asdict(h), "fecha": h.fecha.isoformat()} for h in cel.historial],
    }


class Revision(BaseModel):
    motivo: str | None = None


class Correccion(BaseModel):
    valor: Any = None
    motivo: str
    estado_dato: str | None = None


@enrutador.post("/matriz/filas/{estudio}/celdas/{clave}/aprobar")
def aprobar(estudio: int, clave: str, datos: Revision, proyecto_id: uuid.UUID = Depends(proyecto_valido),
            u: Usuario = Depends(usuario_actual), c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    fila = c.revisar.aprobar(proyecto_id, estudio, clave, autor=u.correo, motivo=datos.motivo)
    return _celda_resumen(fila, fila.celda(clave))


@enrutador.post("/matriz/filas/{estudio}/celdas/{clave}/corregir")
def corregir(estudio: int, clave: str, datos: Correccion, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             u: Usuario = Depends(usuario_actual), c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    fila = c.revisar.corregir(proyecto_id, estudio, clave, autor=u.correo, valor=datos.valor, motivo=datos.motivo,
                              estado_dato=datos.estado_dato)
    return _celda_resumen(fila, fila.celda(clave))


@enrutador.post("/matriz/filas/{estudio}/celdas/{clave}/rechazar")
def rechazar(estudio: int, clave: str, datos: Revision, proyecto_id: uuid.UUID = Depends(proyecto_valido),
             u: Usuario = Depends(usuario_actual), c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    fila = c.revisar.rechazar(proyecto_id, estudio, clave, autor=u.correo, motivo=datos.motivo or "")
    return _celda_resumen(fila, fila.celda(clave))


@enrutador.post("/importaciones/matriz")
async def importar(archivo: UploadFile = File(...), reemplazar: bool = Form(False),
                   proyecto_id: uuid.UUID = Depends(proyecto_valido), c: CasosDeMatriz = Depends(casos)) -> dict[str, Any]:
    r = c.importar.ejecutar(proyecto_id, await archivo.read(), archivo.filename or "matriz.xlsx", reemplazar)
    return asdict(r)

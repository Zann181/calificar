"""Caso de uso ExportarMatriz.

1. Parte del Excel importado (formato, notas de encabezado, hoja Guía de columnas).
2. Escribe las filas HEREDADAS tal como se importaron, con sus notas heredadas.
3. Pasa las filas EXTRAÍDAS por recursos/escribir_matriz.py (comentarios de fuente, colores,
   hojas Trazabilidad y Auditoria), sin reescribir el script.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.contextos.exportacion.puertos import (
    AlmacenDeExportaciones,
    EscritorDeHeredadas,
    EscritorDeMatriz,
    FuenteDeMatriz,
)

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Exportacion:
    id: uuid.UUID
    clave_almacen: str
    filas_heredadas: int
    filas_extraidas: int


class ExportarMatriz:
    def __init__(self, fuente: FuenteDeMatriz, heredadas: EscritorDeHeredadas, escritor: EscritorDeMatriz,
                 almacen: AlmacenDeExportaciones) -> None:
        self._fuente, self._heredadas, self._escritor, self._almacen = fuente, heredadas, escritor, almacen

    def ejecutar(self, proyecto_id: uuid.UUID) -> Exportacion:
        columnas = self._fuente.columnas(proyecto_id)
        base = self._fuente.base(proyecto_id)
        filas = self._fuente.filas(proyecto_id)
        heredadas = [f for f in filas if f.origen == "HEREDADA"]
        extraidas = [f for f in filas if f.origen == "EXTRAIDA" and f.salida is not None]

        datos = self._heredadas.escribir(base, heredadas, columnas)
        if extraidas:
            datos = self._escritor.escribir(
                salida=[f.salida for f in extraidas if f.salida is not None],
                libro=self._fuente.libro(proyecto_id),
                matriz_base=datos,
                auditoria=[a for f in extraidas for a in f.auditoria],
            )
        id_ = uuid.uuid4()
        clave = self.clave(proyecto_id, id_)
        self._almacen.guardar(clave, datos, TIPO_XLSX)
        return Exportacion(id=id_, clave_almacen=clave, filas_heredadas=len(heredadas), filas_extraidas=len(extraidas))

    @staticmethod
    def clave(proyecto_id: uuid.UUID, exportacion_id: uuid.UUID) -> str:
        return f"exportaciones/{proyecto_id}/{exportacion_id}.xlsx"

    def leer(self, proyecto_id: uuid.UUID, exportacion_id: uuid.UUID) -> bytes:
        return self._almacen.leer(self.clave(proyecto_id, exportacion_id))

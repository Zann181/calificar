"""Normas con adaptadores SQL: publicar versiones del libro y ver las columnas que derivan de él."""

from __future__ import annotations

import uuid
from typing import Any

from app.composicion import Contenedor


def test_publicar_el_mismo_libro_no_duplica(contenedor: Contenedor, proyecto: uuid.UUID,
                                            libro_json: dict[str, Any]) -> None:
    contenedor.normas.publicar.ejecutar(proyecto, libro_json)
    assert len(contenedor.normas.consultas.versiones(proyecto)) == 1


def test_libro_nuevo_desactiva_el_anterior_y_cambia_las_columnas(contenedor: Contenedor, proyecto: uuid.UUID,
                                                                  libro_json: dict[str, Any]) -> None:
    libro_json["metadatos"]["version"] = "2.2-prueba"
    libro_json["columnas"]["Pais"]["encabezado_original"] = "País (prueba)"
    v = contenedor.normas.publicar.ejecutar(proyecto, libro_json)
    versiones = contenedor.normas.consultas.versiones(proyecto)
    assert len(versiones) == 2
    assert [x.version for x in versiones if x.activa] == ["2.2-prueba"]
    assert contenedor.normas.consultas.libro_activo(proyecto).id == v.id
    pais = next(c for c in contenedor.normas.consultas.columnas(proyecto) if c.clave == "Pais")
    assert pais.encabezado_excel == "País (prueba)"

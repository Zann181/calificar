"""CatalogoDeColumnas: las columnas salen del libro de códigos, nunca del código (aceptación de F1)."""

from __future__ import annotations

import json
from typing import Any

import openpyxl
import pytest

from app.compartido.columnas import DefinicionDeColumna
from app.contextos.normas.dominio.catalogo import (
    CatalogoDeColumnas,
    LibroInvalido,
    derivar_columnas,
    derivar_protocolo,
)
from app.contextos.normas.dominio.modelos import VersionDelLibro
from tests.conftest import LIBRO_V22, MATRIZ


def test_59_columnas_en_orden_de_posicion(columnas: list[DefinicionDeColumna]) -> None:
    assert len(columnas) == 59
    assert [c.posicion for c in columnas] == list(range(1, 60))
    assert columnas[0].clave == "Documento"
    assert columnas[0].letra == "A"


def test_tipos_y_vocabularios_vienen_del_libro(libro: dict[str, Any], por_clave: dict[str, DefinicionDeColumna]) -> None:
    for clave, col in libro["columnas"].items():
        io = col["instruccion_operativa"]
        d = por_clave[clave]
        assert d.tipo_de_dato == io["tipo_de_dato"]
        assert d.requiere_evidencia == bool(io["requiere_evidencia"])
        permitidos = io.get("valores_permitidos")
        assert d.valores_permitidos == (tuple(permitidos) if isinstance(permitidos, list) else None)


def test_cambiar_una_columna_en_el_libro_se_refleja_en_el_catalogo(libro: dict[str, Any]) -> None:
    """Aceptación de F1: una prueba cambia una columna en un libro de prueba y la ve reflejada."""
    col = libro["columnas"]["Incluir en meta análisi"]
    col["encabezado_original"] = "Incluir (prueba)"
    col["instruccion_operativa"]["valores_permitidos"] = ["SI", "No", "Quizás"]
    col["instruccion_operativa"]["obligatorio"] = False

    d = CatalogoDeColumnas(libro).columna("Incluir en meta análisi")
    assert d.encabezado_excel == "Incluir (prueba)"
    assert d.valores_permitidos == ("SI", "No", "Quizás")
    assert d.obligatorio is False
    assert "Quizás" in d.nota_encabezado


def test_agregar_una_columna_en_el_libro_la_agrega_al_catalogo(libro: dict[str, Any]) -> None:
    nueva = dict(libro["columnas"]["Conclusion"], posicion=60, letra_excel="BH", encabezado_original="Nueva")
    libro["columnas"]["Columna nueva"] = nueva
    claves = CatalogoDeColumnas(libro).claves()
    assert len(claves) == 60
    assert claves[-1] == "Columna nueva"


def test_las_notas_de_encabezado_coinciden_con_el_excel(columnas: list[DefinicionDeColumna], libro: dict[str, Any]) -> None:
    """Las 54 notas del Excel salen del libro. Las de columnas cuya instrucción cambió en la v2.3 (refuerzos del
    manual) y las 5 columnas nuevas ya no coinciden con el Excel viejo, por diseño."""
    anterior = json.loads(LIBRO_V22.read_text(encoding="utf-8"))["columnas"]
    ws = openpyxl.load_workbook(MATRIZ)["Extracción completa.csv"]
    comparadas = 0
    for c in columnas:
        if c.agregada_en_version or libro["columnas"][c.clave]["instruccion_operativa"] != anterior[c.clave]["instruccion_operativa"]:
            continue
        comparadas += 1
        comentario = ws.cell(1, c.posicion).comment
        assert comentario is not None, c.clave
        assert comentario.text == c.nota_encabezado, c.clave
    assert comparadas >= 35


def test_libro_sin_seccion_obligatoria(libro: dict[str, Any]) -> None:
    del libro["esquema_de_salida"]
    with pytest.raises(LibroInvalido, match="esquema_de_salida"):
        derivar_columnas(libro)


def test_columna_sin_campo_obligatorio(libro: dict[str, Any]) -> None:
    del libro["columnas"]["Pais"]["instruccion_operativa"]
    with pytest.raises(LibroInvalido, match="Pais"):
        derivar_columnas(libro)


def test_posiciones_repetidas(libro: dict[str, Any]) -> None:
    libro["columnas"]["Pais"]["posicion"] = 1
    with pytest.raises(LibroInvalido, match="posición"):
        derivar_columnas(libro)


def test_version_del_libro(libro: dict[str, Any]) -> None:
    import uuid

    v = VersionDelLibro.publicar(proyecto_id=uuid.uuid4(), contenido=libro)
    assert v.version == "2.3"
    assert v.activa
    otra = VersionDelLibro.publicar(proyecto_id=v.proyecto_id, contenido=libro)
    assert otra.hash == v.hash
    assert len(v.catalogo().columnas) == 59


def test_la_guia_de_cada_columna_sale_del_libro(libro: dict[str, Any], por_clave: dict[str, DefinicionDeColumna]) -> None:
    for clave, col in libro["columnas"].items():
        guia = por_clave[clave].guia
        assert guia["para_que_sirve"] == col["descripcion"]
        assert bool(guia.get("donde_buscar")) == bool(col["instruccion_operativa"].get("donde_buscar"))
    beta = por_clave["Beta Fel 1- JP"].guia
    campos = {c["campo"] for c in beta["campos_de_trazabilidad"]}
    assert {"tipo_de_efecto", "tecnica_del_beta", "covariables_del_beta"} <= campos
    assert "evidencia" not in campos
    assert por_clave["Incluir en meta análisi"].guia["campos_de_trazabilidad"]


def test_el_protocolo_trae_las_reglas_generales_del_libro(libro: dict[str, Any]) -> None:
    protocolo = derivar_protocolo(libro)
    assert len(protocolo["principios_de_veracidad"]) == 12
    assert protocolo["precedencia_de_fuentes"][0].startswith("1.")
    assert "No indica" in protocolo["faltantes"]
    assert protocolo["como_se_construye_cada_fila"]["regla_para_abrir_una_fila_nueva"]

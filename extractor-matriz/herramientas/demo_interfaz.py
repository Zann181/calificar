"""Datos de demostración para la interfaz: Kumar y Singh como filas EXTRAÍDAS, con evidencias ancladas.

No es el motor de extracción (F2). Toma lo que ya existe:
- las salidas guardadas de MinerU (recursos/fixtures/mineru) para convertir los dos artículos sin MinerU;
- las extracciones de la prueba F0 (docs/decisiones/f0/extraccion/*__claude-opus-5-5);
- un anclaje provisional según la sección 8.4, que F2 llevará al contexto Extracción.

Uso (desde backend/, con la base local ya sembrada e importada; ver README.md):
    .venv/Scripts/python ../herramientas/demo_interfaz.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from sqlalchemy import select  # noqa: E402

from app.compartido.db import RegistroProyecto  # noqa: E402
from app.compartido.normalizacion import norm  # noqa: E402
from app.composicion import Contenedor, construir  # noqa: E402
from app.config import settings  # noqa: E402
from app.contextos.biblioteca.adaptadores.mineru import ConversorFijo  # noqa: E402
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo  # noqa: E402
from app.contextos.biblioteca.dominio.documento import Bloque, DocumentoEstructurado  # noqa: E402
from app.contextos.matriz.dominio.fila import (  # noqa: E402
    Celda,
    Evidencia,
    FilaDeEfecto,
    Inferencia,
    TipoValor,
)

FIXTURES = RAIZ / "recursos" / "fixtures"
F0 = RAIZ / "docs" / "decisiones" / "f0" / "extraccion"
ARTICULOS = {"kumar_2022": "kumar_2022__claude-opus-5-5", "singh_2023": "singh_2023__claude-opus-5-5"}
UMBRAL = 95


# ------------------------------------------------------------------ anclaje provisional (sección 8.4)

def _ancla(nivel: str, b: Bloque | None, similitud: float, nota: str = "") -> dict[str, Any]:
    return {"nivel": nivel, "bloque_id": b.id if b else None, "pagina": b.pagina if b else None,
            "rect": b.rect.a_lista() if b else None, "similitud": round(similitud, 1), "nota": nota}


def anclar(e: dict[str, Any], doc: DocumentoEstructurado) -> dict[str, Any]:
    q = norm(e.get("cita_textual") or "")
    citado = doc.bloque(e["bloque_id"]) if e.get("bloque_id") else None
    if citado is not None and citado.tabla is not None and e.get("fila_tabla") and e.get("columna_tabla"):
        for c in citado.tabla.celdas:
            if (fuzz.ratio(norm(c.etiqueta_fila), norm(e["fila_tabla"])) >= 90
                    and fuzz.ratio(norm(c.etiqueta_columna), norm(e["columna_tabla"])) >= 90
                    and q and q in norm(c.texto)):
                return _ancla("VERIFICADA", citado, 100, "celda de tabla")
    if citado is not None and q and q in citado.texto_norm:
        return _ancla("VERIFICADA", citado, 100)
    for x in doc.bloques:
        if q and q in x.texto_norm:
            return _ancla("VERIFICADA_CON_CORRECCION", x, 100, f"la cita está en {x.id}, no en {e.get('bloque_id')}")
    pagina = int(e.get("pagina_pdf") or 0)
    vecinos = [x for x in doc.bloques if abs(x.pagina - pagina) <= 1 and x.texto_norm]
    mejor = max(vecinos, key=lambda x: fuzz.partial_ratio(q, x.texto_norm), default=None)
    similitud = fuzz.partial_ratio(q, mejor.texto_norm) if mejor is not None and q else 0.0
    if mejor is not None and similitud >= UMBRAL:
        return _ancla("POR_CONFIRMAR", mejor, similitud)
    if e.get("leido_de_figura") and citado is not None and (
            citado.tipo == "figura" or (citado.tabla is not None and citado.tabla.es_imagen)):
        return _ancla("POR_CONFIRMAR", citado, similitud, "leído de figura: verificar a mano")
    return _ancla("NO_VERIFICABLE", citado or mejor, similitud)


# ------------------------------------------------------------------ armado de filas

def _proyecto(c: Contenedor) -> uuid.UUID:
    with c.fabrica() as s:
        p = s.scalar(select(RegistroProyecto).where(RegistroProyecto.nombre == c.ajustes.proyecto_nombre))
        if p is None:
            sys.exit("Primero: python -m app.cli semilla, importar-matriz y cargar-carpeta")
        return p.id


def _salida(carpeta: Path) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = json.loads((carpeta / "salida.json").read_text(encoding="utf-8"))
    anclas = carpeta / "anclas.json"
    if anclas.exists():  # corridas anteriores al libro v2.2 guardaron bloque_id aparte
        for k, bloque in json.loads(anclas.read_text(encoding="utf-8")).items():
            i, col, j = k.split("|")
            ev = salida[int(i)]["trazabilidad"]["evidencia"].get(col) or []
            if int(j) < len(ev):
                ev[int(j)].setdefault("bloque_id", bloque)
    return salida


def _tipo(clave: str, valor: Any, evidencias: list[dict[str, Any]], inferidas: set[str]) -> TipoValor:
    if valor is None:
        return TipoValor.FALTANTE
    if clave in inferidas:
        return TipoValor.INFERIDO
    v = norm(str(valor))
    return TipoValor.LITERAL if any(v and v in norm(e.get("cita_textual") or "") for e in evidencias) else TipoValor.CODIFICADO


def armar_fila(c: Contenedor, pid: uuid.UUID, articulo_id: uuid.UUID, item: dict[str, Any],
               doc: DocumentoEstructurado, auditoria: list[dict[str, Any]]) -> FilaDeEfecto:
    fila, traz = item["fila"], item["trazabilidad"]
    inferencias = {i.get("columna"): i for i in traz.get("inferencias") or [] if isinstance(i, dict)}
    columnas = c.normas.consultas.columnas(pid)
    celdas: dict[str, Celda] = {}
    for col in columnas:
        valor = fila.get(col.clave)
        crudas = traz.get("evidencia", {}).get(col.clave) or []
        evidencias = [Evidencia(pagina_pdf=int(e["pagina_pdf"]), ubicacion=e.get("ubicacion", ""),
                                cita_textual=e.get("cita_textual", ""), leido_de_figura=bool(e.get("leido_de_figura")),
                                fila_tabla=e.get("fila_tabla"), columna_tabla=e.get("columna_tabla"),
                                bloque_id=e.get("bloque_id"), ancla=anclar(e, doc)) for e in crudas]
        inf = inferencias.get(col.clave)
        celdas[col.clave] = Celda.extraida(
            clave=col.clave, valor=valor,
            estado_dato=(traz.get("estado_del_dato") or {}).get(col.clave) if valor is None else None,
            tipo_valor=_tipo(col.clave, valor, crudas, set(inferencias)), evidencias=evidencias,
            inferencia=Inferencia(regla=str(inf.get("regla_aplicada", "")), razonamiento=str(inf.get("razonamiento", "")))
            if inf else None)
    claves = {col.clave for col in columnas}
    hallazgos = []
    for h in auditoria:
        h = dict(h)
        if h.get("columna") not in claves:  # hallazgos de fila (número de filas, mapa de efectos)
            h["hallazgo"] = f"[{h.get('columna')}] {h.get('hallazgo')}"
            h["columna"] = "Estudio"
        hallazgos.append(h)
    return FilaDeEfecto.extraida(
        proyecto_id=pid, estudio=int(fila["Estudio"]), documento=int(fila["Documento"]), articulo_id=articulo_id,
        version_libro_id=c.normas.consultas.libro_activo(pid).id, celdas=celdas,
        trazabilidad={"salida": item, "auditoria": hallazgos, "origen_demo": "Prueba F0 (no es el motor de F2)"})


def main() -> None:
    ajustes = settings()
    with tempfile.TemporaryDirectory() as tmp:
        for nombre in ARTICULOS:  # ConversorFijo busca <sha256 del PDF>.zip
            sha = hashlib.sha256((FIXTURES / f"{nombre}.pdf").read_bytes()).hexdigest()
            shutil.copy(FIXTURES / "mineru" / f"{nombre}.zip", Path(tmp) / f"{sha}.zip")
        c = construir(ajustes, conversor=ConversorFijo(Path(tmp)))
        pid = _proyecto(c)
        articulos = {a.huella_sha256: a for a in c.biblioteca.consultas.listar(pid).articulos}
        filas = []
        for nombre, carpeta in ARTICULOS.items():
            sha = hashlib.sha256((FIXTURES / f"{nombre}.pdf").read_bytes()).hexdigest()
            art = articulos.get(sha)
            if art is None:
                sys.exit(f"{nombre}: el PDF no está cargado (python -m app.cli cargar-carpeta ...)")
            if art.estado != EstadoArticulo.LISTO:
                print(f"{art.nombre_archivo}: {c.biblioteca.convertir.ejecutar(pid, art.id)}")
            doc = c.biblioteca.consultas.documento(pid, art.id)
            ruta_aud = F0 / carpeta / "auditoria_evidencia.json"
            auditoria = json.loads(ruta_aud.read_text(encoding="utf-8")) if ruta_aud.exists() else []
            for item in _salida(F0 / carpeta):
                fila = armar_fila(c, pid, art.id, item, doc, auditoria)
                niveles: dict[str, int] = {}
                for celda in fila.celdas.values():
                    for e in celda.evidencias:
                        n = (e.ancla or {}).get("nivel", "?")
                        niveles[n] = niveles.get(n, 0) + 1
                print(f"Estudio {fila.estudio} ({art.nombre_archivo}): anclas {niveles}")
                filas.append(fila)
        reemplazadas = c.matriz.escribir_extraidas.ejecutar(pid, filas)
        print(f"{len(filas)} filas extraídas escritas; {reemplazadas} filas heredadas reemplazadas")


if __name__ == "__main__":
    main()

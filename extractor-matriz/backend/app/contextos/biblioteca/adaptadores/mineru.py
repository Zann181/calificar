"""Adaptadores de ConversorPDF sobre MinerU (sección 7 de la especificación).

normalizar(zip) convierte la salida cruda en DocumentoEstructurado:
1. Orden de lectura y página de cada bloque desde content_list.json; page_idx es base 0 → +1.
2. Rectángulo en puntos PDF, origen arriba a la izquierda (ADR 0001):
   content_list trae bbox en escala 0-1000 de la página; x_pt = bbox_x / 1000 × ancho_pt y
   y_pt = bbox_y / 1000 × alto_pt, con ancho y alto de middle.json (pdf_info[].page_size).
3. id = p{pagina:02d}-b{orden:02d} según el orden dentro de la página (estable para la misma
   salida de MinerU; lo verifica tests/unitarias/test_mineru.py).
4. Tablas: HTML → celdas con etiqueta_fila (primera columna) y etiqueta_columna (fila de
   encabezado). Sin HTML → es_imagen = true.
5. texto_norm con compartido.normalizacion.norm().
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.contextos.biblioteca.dominio.documento import (
    Bloque,
    CeldaTabla,
    DocumentoEstructurado,
    Pagina,
    Rect,
    Tabla,
    id_de_bloque,
)
from app.contextos.biblioteca.puertos import Conversion

ESCALA_CONTENT_LIST = 1000.0

_TIPOS = {
    "table": "tabla",
    "image": "figura",
    "chart": "figura",
    "equation": "ecuacion",
    "interline_equation": "ecuacion",
    "page_footnote": "nota",
    "header": "otro",
    "footer": "otro",
    "page_number": "otro",
    "aside_text": "otro",
    "code": "parrafo",
    "list": "parrafo",
    "ref_text": "parrafo",
}


class ErrorDeConversion(RuntimeError):
    pass


def _tipo(item: dict[str, Any]) -> str:
    t = item.get("type", "")
    if t == "text":
        return "titulo" if item.get("text_level") else "parrafo"
    return _TIPOS.get(t, "otro")


def _grilla(html: str) -> list[list[str]]:
    """HTML de tabla → grilla rectangular, expandiendo rowspan y colspan."""
    soup = BeautifulSoup(html, "lxml")
    grilla: list[list[str | None]] = []
    for i, tr in enumerate(soup.find_all("tr")):
        while len(grilla) <= i:
            grilla.append([])
        j = 0
        for td in tr.find_all(["td", "th"]):
            while j < len(grilla[i]) and grilla[i][j] is not None:
                j += 1
            texto = td.get_text(" ", strip=True)
            filas, cols = int(str(td.get("rowspan") or 1)), int(str(td.get("colspan") or 1))
            for di in range(filas):
                while len(grilla) <= i + di:
                    grilla.append([])
                fila = grilla[i + di]
                while len(fila) < j + cols:
                    fila.append(None)
                for dj in range(cols):
                    fila[j + dj] = texto
            j += cols
    ancho = max((len(f) for f in grilla), default=0)
    return [[c or "" for c in f] + [""] * (ancho - len(f)) for f in grilla]


def tabla_desde_html(html: str | None) -> Tabla:
    if not html or "<tr" not in html:
        return Tabla(html=html or "", celdas=(), es_imagen=True)
    g = _grilla(html)
    encabezado = g[0] if g else []
    celdas = tuple(
        CeldaTabla(fila=i, columna=j, texto=texto, etiqueta_fila=fila[0] if fila else "",
                   etiqueta_columna=encabezado[j] if j < len(encabezado) else "")
        for i, fila in enumerate(g) for j, texto in enumerate(fila) if i > 0 and j > 0 and texto
    )
    return Tabla(html=html, celdas=celdas, es_imagen=False)


def _texto_de_tabla(item: dict[str, Any], tabla: Tabla) -> str:
    partes = list(item.get("table_caption") or [])
    if not tabla.es_imagen:
        partes += [" ".join(fila) for fila in _grilla(tabla.html)]
    partes += list(item.get("table_footnote") or [])
    return "\n".join(p for p in partes if p)


def _texto(item: dict[str, Any], tipo_mineru: str) -> str:
    if tipo_mineru == "list":
        return "\n".join(item.get("list_items") or [])
    if tipo_mineru in ("image", "chart"):
        partes = list(item.get(f"{tipo_mineru}_caption") or []) + [item.get("content") or ""]
        partes += list(item.get(f"{tipo_mineru}_footnote") or [])
        return "\n".join(p for p in partes if p)
    return str(item.get("text") or item.get("content") or "")


def normalizar(crudo: bytes) -> DocumentoEstructurado:
    with zipfile.ZipFile(io.BytesIO(crudo)) as z:
        nombres = set(z.namelist())
        if "content_list.json" not in nombres or "middle.json" not in nombres:
            raise ErrorDeConversion("La salida de MinerU no trae content_list.json y middle.json")
        contenido = json.loads(z.read("content_list.json"))
        medio = json.loads(z.read("middle.json"))
        servicio = json.loads(z.read("servicio.json")) if "servicio.json" in nombres else {}

    paginas = []
    for info in medio["pdf_info"]:
        ancho, alto = info["page_size"]
        paginas.append(Pagina(numero=int(info["page_idx"]) + 1, ancho_pt=float(ancho), alto_pt=float(alto)))
    por_numero = {p.numero: p for p in paginas}

    bloques: list[Bloque] = []
    orden: dict[int, int] = {}
    for item in contenido:
        numero = int(item["page_idx"]) + 1
        pagina = por_numero.get(numero)
        if pagina is None or "bbox" not in item:
            continue
        orden[numero] = orden.get(numero, 0) + 1
        x0, y0, x1, y1 = (float(v) for v in item["bbox"])
        rect = Rect(
            round(x0 / ESCALA_CONTENT_LIST * pagina.ancho_pt, 2), round(y0 / ESCALA_CONTENT_LIST * pagina.alto_pt, 2),
            round(x1 / ESCALA_CONTENT_LIST * pagina.ancho_pt, 2), round(y1 / ESCALA_CONTENT_LIST * pagina.alto_pt, 2),
        )
        tipo_mineru = item.get("type", "")
        tipo = _tipo(item)
        tabla = None
        if tipo == "tabla":
            tabla = tabla_desde_html(item.get("table_body"))
            texto = _texto_de_tabla(item, tabla)
        else:
            texto = _texto(item, tipo_mineru)
        bloques.append(Bloque(id=id_de_bloque(numero, orden[numero]), pagina=numero, tipo=tipo, rect=rect,
                              texto=texto, tabla=tabla, imagen=item.get("img_path")))

    metadatos = {
        "conversor": f"mineru {servicio.get('mineru', '?')} {servicio.get('backend', 'pipeline')}",
        "backend_mineru": medio.get("_backend"),
        "segundos": servicio.get("segundos"),
        "huella_crudo": hashlib.sha256(crudo).hexdigest(),
    }
    return DocumentoEstructurado(paginas=tuple(paginas), bloques=tuple(bloques), metadatos=metadatos)


class MineruHttp:
    """Llama a servicio-mineru (POST /convertir) y normaliza la respuesta."""

    def __init__(self, url: str, tiempo_max: float = 1800) -> None:
        self._url, self._tiempo = url.rstrip("/"), tiempo_max

    def convertir(self, pdf: bytes, nombre: str) -> Conversion:
        r = httpx.post(f"{self._url}/convertir", files={"archivo": (nombre, pdf, "application/pdf")},
                       timeout=self._tiempo)
        if r.status_code != 200:
            raise ErrorDeConversion(f"servicio-mineru respondió {r.status_code}: {r.text[:500]}")
        return Conversion(documento=normalizar(r.content), crudo=r.content)

    def salud(self) -> dict[str, Any]:
        datos: dict[str, Any] = httpx.get(f"{self._url}/salud", timeout=10).json()
        return datos


class ConversorFijo:
    """Adaptador de prueba: devuelve salidas guardadas en recursos/fixtures/mineru/<sha256 del PDF>.zip
    o, si no existe, <nombre sin extensión>.zip."""

    def __init__(self, carpeta: Path) -> None:
        self._carpeta = carpeta

    def convertir(self, pdf: bytes, nombre: str) -> Conversion:
        candidatos = [self._carpeta / f"{hashlib.sha256(pdf).hexdigest()}.zip", self._carpeta / f"{Path(nombre).stem}.zip"]
        for ruta in candidatos:
            if ruta.exists():
                crudo = ruta.read_bytes()
                return Conversion(documento=normalizar(crudo), crudo=crudo)
        raise ErrorDeConversion(f"No hay salida guardada para {nombre}")

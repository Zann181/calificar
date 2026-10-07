"""Algoritmo de anclaje (sección 8.4): comprueba dónde está cada cita en el documento estructurado.

Cada bloque se busca en dos textos normalizados: el que vio el modelo en el texto etiquetado
(capa del PDF para los bloques H1 y H3, sin escapes H9) y el de MinerU. Basta con que la cita
esté en uno de los dos.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rapidfuzz import fuzz

from app.compartido.normalizacion import norm
from app.contextos.extraccion.dominio.documento import BloqueDeTrabajo, DocumentoDeTrabajo

UMBRAL_ETIQUETA = 90


class NivelAncla(StrEnum):
    VERIFICADA = "VERIFICADA"
    VERIFICADA_CON_CORRECCION = "VERIFICADA_CON_CORRECCION"
    POR_CONFIRMAR = "POR_CONFIRMAR"
    NO_VERIFICABLE = "NO_VERIFICABLE"


ORDEN_NIVELES = tuple(NivelAncla)


def nivel_mas_bajo(niveles: list[NivelAncla]) -> NivelAncla | None:
    return max(niveles, key=ORDEN_NIVELES.index) if niveles else None


@dataclass(frozen=True)
class Ancla:
    estudio: int
    columna: str
    indice_evidencia: int
    nivel: NivelAncla
    similitud: float
    bloque_id: str | None = None
    pagina: int | None = None
    rect: tuple[float, float, float, float] | None = None
    rango: tuple[int, int] | None = None
    leido_de_figura: bool = False
    nota: str = ""

    def a_dict(self) -> dict[str, Any]:
        return {"estudio": self.estudio, "columna": self.columna, "indice_evidencia": self.indice_evidencia,
                "nivel": self.nivel.value, "similitud": self.similitud, "bloque_id": self.bloque_id,
                "pagina": self.pagina, "rect": list(self.rect) if self.rect else None,
                "rango": list(self.rango) if self.rango else None, "leido_de_figura": self.leido_de_figura,
                "nota": self.nota}

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> Ancla:
        rect, rango = d.get("rect"), d.get("rango")
        return cls(estudio=int(d["estudio"]), columna=d["columna"], indice_evidencia=int(d["indice_evidencia"]),
                   nivel=NivelAncla(d["nivel"]), similitud=float(d["similitud"]), bloque_id=d.get("bloque_id"),
                   pagina=d.get("pagina"), rect=(rect[0], rect[1], rect[2], rect[3]) if rect else None,
                   rango=(rango[0], rango[1]) if rango else None, leido_de_figura=bool(d.get("leido_de_figura")),
                   nota=d.get("nota", ""))


class Anclador:
    def __init__(self, doc: DocumentoDeTrabajo, efectivo_norm: dict[str, str] | None = None,
                 umbral_similitud: float = 95) -> None:
        self._doc, self._umbral = doc, umbral_similitud
        efectivo_norm = efectivo_norm or {}
        self._textos: dict[str, tuple[str, ...]] = {
            b.id: tuple(t for t in dict.fromkeys((efectivo_norm.get(b.id, ""), b.texto_norm)) if t)
            for b in doc.bloques
        }

    @property
    def documento(self) -> DocumentoDeTrabajo:
        return self._doc

    def _posicion(self, q: str, b: BloqueDeTrabajo) -> tuple[int, int] | None:
        """Rango de caracteres de q en el primer texto del bloque que la contiene."""
        for t in self._textos[b.id]:
            i = t.find(q)
            if i >= 0:
                return (i, i + len(q))
        return None

    def anclar(self, evidencia: dict[str, Any], *, estudio: int, columna: str, indice: int) -> Ancla:
        q = norm(str(evidencia.get("cita_textual") or ""))
        citado = self._doc.bloque(evidencia.get("bloque_id"))
        figura = bool(evidencia.get("leido_de_figura"))

        def ancla(nivel: NivelAncla, b: BloqueDeTrabajo | None, similitud: float, *,
                  rango: tuple[int, int] | None = None, nota: str = "") -> Ancla:
            return Ancla(estudio=estudio, columna=columna, indice_evidencia=indice, nivel=nivel,
                         similitud=round(similitud, 1), bloque_id=b.id if b else None,
                         pagina=b.pagina if b else None, rect=b.rect if b else None, rango=rango,
                         leido_de_figura=figura, nota=nota)

        if q:
            # 1. Celda de tabla por sus etiquetas de fila y columna.
            fila_t, col_t = evidencia.get("fila_tabla"), evidencia.get("columna_tabla")
            if citado is not None and citado.es_tabla and fila_t and col_t:
                for c in citado.celdas:
                    if (fuzz.ratio(norm(c.etiqueta_fila), norm(str(fila_t))) >= UMBRAL_ETIQUETA
                            and fuzz.ratio(norm(c.etiqueta_columna), norm(str(col_t))) >= UMBRAL_ETIQUETA
                            and q in norm(c.texto)):
                        return ancla(NivelAncla.VERIFICADA, citado, 100, nota="celda de tabla")
            # 2. En el bloque citado.
            if citado is not None:
                rango = self._posicion(q, citado)
                if rango is not None:
                    return ancla(NivelAncla.VERIFICADA, citado, 100, rango=rango)
            # 3. En otro bloque.
            for x in self._doc.bloques:
                rango = self._posicion(q, x)
                if rango is not None:
                    return ancla(NivelAncla.VERIFICADA_CON_CORRECCION, x, 100, rango=rango,
                                 nota=f"la cita está en {x.id}, no en {evidencia.get('bloque_id')}")
        # 4. Coincidencia aproximada en la página citada y las adyacentes.
        pagina = int(evidencia.get("pagina_pdf") or (citado.pagina if citado else 0))
        mejor: BloqueDeTrabajo | None = None
        similitud = 0.0
        if q:
            for x in self._doc.bloques:
                if abs(x.pagina - pagina) > 1:
                    continue
                for t in self._textos[x.id]:
                    s = fuzz.partial_ratio(q, t)
                    if s > similitud:
                        mejor, similitud = x, s
        if mejor is not None and similitud >= self._umbral:
            return ancla(NivelAncla.POR_CONFIRMAR, mejor, similitud, nota="coincidencia aproximada")
        # 5. Leído de una figura o de una tabla en imagen.
        if figura and citado is not None and citado.es_imagen:
            return ancla(NivelAncla.POR_CONFIRMAR, citado, similitud, nota="leído de figura: verificar a mano")
        # 6.
        return ancla(NivelAncla.NO_VERIFICABLE, citado or mejor, similitud)

    def anclar_salida(self, salida: list[dict[str, Any]]) -> list[Ancla]:
        anclas: list[Ancla] = []
        for i, item in enumerate(salida):
            estudio = _estudio(item, i)
            for columna, evidencias in ((item.get("trazabilidad") or {}).get("evidencia") or {}).items():
                for j, e in enumerate(evidencias or []):
                    if isinstance(e, dict):
                        anclas.append(self.anclar(e, estudio=estudio, columna=columna, indice=j))
        return anclas


def _estudio(item: dict[str, Any], posicion: int) -> int:
    valor = (item.get("fila") or {}).get("Estudio")
    return int(valor) if isinstance(valor, int | float) and not isinstance(valor, bool) else -(posicion + 1)


def resumen_de_niveles(anclas: list[Ancla]) -> dict[str, int]:
    conteo = {n.value: 0 for n in NivelAncla}
    for a in anclas:
        conteo[a.nivel.value] += 1
    return conteo

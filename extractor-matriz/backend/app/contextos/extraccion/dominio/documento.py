"""Vista del documento estructurado que usa Extracción (texto etiquetado y anclaje).

Extracción no importa el modelo de Biblioteca (contextos independientes): recibe el documento en
el formato persistido (DocumentoEstructurado.a_dict()) y lo lee con sus propias clases. La raíz de
composición agrega a cada tabla `filas_grilla`, las filas del HTML unidas por espacios, que el
texto etiquetado usa para separar leyenda, celdas y notas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.compartido.normalizacion import norm


@dataclass(frozen=True)
class CeldaDeTabla:
    texto: str
    etiqueta_fila: str
    etiqueta_columna: str


@dataclass(frozen=True)
class BloqueDeTrabajo:
    id: str
    pagina: int
    tipo: str
    rect: tuple[float, float, float, float]
    texto: str
    texto_norm: str
    es_tabla: bool = False
    tabla_es_imagen: bool = False
    celdas: tuple[CeldaDeTabla, ...] = ()
    filas_grilla: tuple[str, ...] = ()

    @property
    def es_imagen(self) -> bool:
        """Figura o tabla que el modelo solo puede leer en la imagen de la página."""
        return self.tipo == "figura" or (self.es_tabla and self.tabla_es_imagen)


@dataclass(frozen=True)
class DocumentoDeTrabajo:
    bloques: tuple[BloqueDeTrabajo, ...]

    def bloque(self, id_bloque: str | None) -> BloqueDeTrabajo | None:
        if not id_bloque:
            return None
        return next((b for b in self.bloques if b.id == id_bloque), None)

    def paginas_con_imagen(self) -> list[int]:
        return sorted({b.pagina for b in self.bloques if b.es_imagen})

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> DocumentoDeTrabajo:
        bloques = []
        for b in d["bloques"]:
            t = b.get("tabla")
            texto = str(b.get("texto") or "")
            bloques.append(BloqueDeTrabajo(
                id=b["id"], pagina=int(b["pagina"]), tipo=b["tipo"],
                rect=(float(b["rect"][0]), float(b["rect"][1]), float(b["rect"][2]), float(b["rect"][3])),
                texto=texto, texto_norm=b.get("texto_norm") or norm(texto),
                es_tabla=t is not None, tabla_es_imagen=bool(t and t.get("es_imagen")),
                celdas=tuple(CeldaDeTabla(texto=c["texto"], etiqueta_fila=c["etiqueta_fila"],
                                          etiqueta_columna=c["etiqueta_columna"]) for c in (t or {}).get("celdas", [])),
                filas_grilla=tuple((t or {}).get("filas_grilla") or ()),
            ))
        return cls(bloques=tuple(bloques))

"""Casos de uso de Matriz: importar la matriz vigente (filas HEREDADAS) y consultar filas y celdas."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio
from app.compartido.normalizacion import norm
from app.contextos.matriz.dominio.fila import (
    Celda,
    Evidencia,
    FilaDeEfecto,
    Inferencia,
    TipoValor,
    valor_permitido,
)
from app.contextos.matriz.puertos import (
    AlmacenDeMatrices,
    BaseDeMatriz,
    ConsultaDeColumnas,
    LectorDeMatriz,
    UnidadDeTrabajoMatriz,
)

FabricaUdT = Callable[[], UnidadDeTrabajoMatriz]
CLAVE_DOCUMENTO, CLAVE_ESTUDIO = "Documento", "Estudio"


class MatrizNoVacia(ErrorDeDominio):
    pass


@dataclass
class ResultadoImportacion:
    filas: int
    notas_heredadas: int
    documentos: int
    fuera_de_vocabulario: list[dict[str, Any]] = field(default_factory=list)
    reemplazadas: int = 0


def _entero(valor: Any, que: str, fila_excel: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int | float) or int(valor) != valor:
        raise ErrorDeDominio(f"Fila {fila_excel} del Excel: {que} debe ser entero y es {valor!r}")
    return int(valor)


class ImportarMatriz:
    """Importa la matriz actual como filas HEREDADAS, sin depurar valores (ida y vuelta exacta)."""

    def __init__(self, udt: FabricaUdT, columnas: ConsultaDeColumnas, lector: LectorDeMatriz,
                 almacen: AlmacenDeMatrices) -> None:
        self._udt, self._columnas, self._lector, self._almacen = udt, columnas, lector, almacen

    def ejecutar(self, proyecto_id: uuid.UUID, datos: bytes, nombre_archivo: str,
                 reemplazar: bool = False) -> ResultadoImportacion:
        columnas = self._columnas.columnas(proyecto_id)
        version_id = self._columnas.version_activa_id(proyecto_id)
        leida = self._lector.leer(datos, columnas)
        por_posicion: dict[int, DefinicionDeColumna] = {c.posicion: c for c in columnas}
        huella = hashlib.sha256(datos).hexdigest()
        clave_base = f"matrices/{proyecto_id}/base-{huella[:12]}.xlsx"

        with self._udt() as u:
            reemplazadas = 0
            if u.filas.cuantas(proyecto_id):
                if not reemplazar:
                    raise MatrizNoVacia("La matriz ya tiene filas; use reemplazar=true para reimportar las heredadas")
                if u.filas.hay_extraidas(proyecto_id):
                    raise MatrizNoVacia("Hay filas extraídas: reimportar la matriz las dejaría inconsistentes")
                reemplazadas = u.filas.borrar_heredadas(proyecto_id)

            vistos: set[int] = set()
            documentos: set[int] = set()
            fuera: list[dict[str, Any]] = []
            notas = 0
            for f in leida.filas:
                valores = {c.clave: f.valores.get(c.posicion) for c in columnas}
                estudio = _entero(valores[CLAVE_ESTUDIO], CLAVE_ESTUDIO, f.fila_excel)
                documento = _entero(valores[CLAVE_DOCUMENTO], CLAVE_DOCUMENTO, f.fila_excel)
                if estudio in vistos:
                    raise ErrorDeDominio(f"Estudio {estudio} repetido en el Excel (fila {f.fila_excel})")
                vistos.add(estudio)
                documentos.add(documento)
                notas_fila = {por_posicion[p].clave: {"autor": n.autor, "texto": n.texto}
                              for p, n in f.notas.items() if p in por_posicion}
                notas += len(notas_fila)
                fila = FilaDeEfecto.importar_heredada(
                    proyecto_id=proyecto_id, estudio=estudio, documento=documento, valores=valores,
                    version_libro_id=version_id, notas_heredadas=notas_fila, fila_excel=f.fila_excel)
                fuera_fila = [c.clave for c in columnas if not valor_permitido(c, valores[c.clave])]
                if fuera_fila:
                    fila.trazabilidad["fuera_de_vocabulario"] = fuera_fila
                    fuera += [{"estudio": estudio, "columna": k, "valor": valores[k]} for k in fuera_fila]
                u.filas.agregar(fila)

            self._almacen.guardar(clave_base, datos,
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            u.filas.guardar_base(proyecto_id, BaseDeMatriz(clave_almacen=clave_base, nombre_archivo=nombre_archivo,
                                                           huella_sha256=huella, hoja=leida.hoja))
            u.filas.ajustar_secuencia(proyecto_id, max(vistos, default=0) + 1)
            u.confirmar()

        return ResultadoImportacion(filas=len(leida.filas), notas_heredadas=notas, documentos=len(documentos),
                                    fuera_de_vocabulario=fuera, reemplazadas=reemplazadas)


class ConsultasDeMatriz:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def pagina(self, proyecto_id: uuid.UUID, *, pagina: int = 1, tam: int = 100,
               documento: int | None = None) -> tuple[list[FilaDeEfecto], int]:
        if pagina < 1 or not 1 <= tam <= 500:
            raise ErrorDeDominio("Página o tamaño fuera de rango")
        with self._udt() as u:
            return u.filas.pagina(proyecto_id, desde=(pagina - 1) * tam, cuantas=tam, documento=documento)

    def fila(self, proyecto_id: uuid.UUID, estudio: int) -> FilaDeEfecto:
        with self._udt() as u:
            return u.filas.por_estudio(proyecto_id, estudio)

    def todas(self, proyecto_id: uuid.UUID) -> list[FilaDeEfecto]:
        with self._udt() as u:
            return u.filas.todas(proyecto_id)

    def base(self, proyecto_id: uuid.UUID) -> BaseDeMatriz | None:
        with self._udt() as u:
            return u.filas.base(proyecto_id)

    def siguiente_estudio(self, proyecto_id: uuid.UUID) -> int:
        with self._udt() as u:
            return u.filas.siguiente_estudio(proyecto_id)


class MarcarVersionDeFilas:
    """Manejador de LibroPublicado: marca como desactualizadas las filas extraídas con otra versión."""

    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, version_libro_id: uuid.UUID) -> int:
        with self._udt() as u:
            filas = u.filas.todas(proyecto_id)
            for f in filas:
                f.marcar_version(version_libro_id)
                u.filas.agregar(f)
            u.confirmar()
            return sum(f.version_desactualizada for f in filas)


class EscribirFilasExtraidas:
    """Escribe las filas de una extracción. Una fila con el mismo Estudio (heredada o de una extracción
    anterior) se reemplaza, como hace escribir_matriz.py."""

    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, filas: list[FilaDeEfecto]) -> int:
        with self._udt() as u:
            reemplazadas = 0
            for f in filas:
                if f.proyecto_id != proyecto_id:
                    raise ErrorDeDominio("La fila no pertenece al proyecto")
                reemplazadas += u.filas.quitar(proyecto_id, f.estudio)
                u.filas.agregar(f)
            u.filas.ajustar_secuencia(proyecto_id, max((f.estudio for f in filas), default=0) + 1)
            u.confirmar()
            return reemplazadas


@dataclass(frozen=True)
class FilasDeExtraccion:
    """Lo que Matriz recibe de una extracción completada (evento ExtraccionCompletada).

    `salida` sigue esquema_de_salida del libro; cada evidencia trae `bloque_id` y `ancla` (nivel, rect,
    rango, similitud). `auditoria` usa el formato de la hoja Auditoria de escribir_matriz.py.
    """

    articulo_id: uuid.UUID
    version_libro_id: uuid.UUID
    salida: list[dict[str, Any]]
    auditoria: list[dict[str, Any]] = field(default_factory=list)
    trazabilidad_extra: dict[str, Any] = field(default_factory=dict)


def _entero_de_salida(fila: dict[str, Any], clave: str) -> int:
    valor = fila.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, int | float) or int(valor) != valor:
        raise ErrorDeDominio(f"La salida de la extracción trae {clave} = {valor!r}; debe ser entero")
    return int(valor)


def _tipo_valor(clave: str, valor: Any, evidencias: list[dict[str, Any]], inferidas: set[str]) -> TipoValor:
    if valor is None:
        return TipoValor.FALTANTE
    if clave in inferidas:
        return TipoValor.INFERIDO
    v = norm(str(valor))
    citado = any(v and v in norm(str(e.get("cita_textual") or "")) for e in evidencias)
    return TipoValor.LITERAL if citado else TipoValor.CODIFICADO


def _sin_anclas(item: dict[str, Any]) -> dict[str, Any]:
    traz = dict(item.get("trazabilidad") or {})
    traz["evidencia"] = {col: [{k: v for k, v in e.items() if k != "ancla"} if isinstance(e, dict) else e
                               for e in (evs or [])]
                         for col, evs in (traz.get("evidencia") or {}).items()}
    return {**item, "trazabilidad": traz}


class EscribirFilasDeExtraccion:
    """Arma las filas EXTRAIDAS de una extracción y las escribe (sección 8.3, paso 9).

    El estado de revisión de cada celda sale del ancla más baja de sus evidencias (sección 8.4).
    """

    def __init__(self, udt: FabricaUdT, columnas: ConsultaDeColumnas) -> None:
        self._escribir, self._columnas = EscribirFilasExtraidas(udt), columnas

    def armar(self, proyecto_id: uuid.UUID, datos: FilasDeExtraccion) -> list[FilaDeEfecto]:
        columnas = self._columnas.columnas(proyecto_id)
        claves = {c.clave for c in columnas}
        filas = []
        for item in datos.salida:
            fila, traz = item.get("fila") or {}, item.get("trazabilidad") or {}
            estudio = _entero_de_salida(fila, CLAVE_ESTUDIO)
            inferencias = {i.get("columna"): i for i in traz.get("inferencias") or [] if isinstance(i, dict)}
            estados = traz.get("estado_del_dato") or {}
            celdas: dict[str, Celda] = {}
            for col in columnas:
                valor = fila.get(col.clave)
                crudas = [e for e in (traz.get("evidencia") or {}).get(col.clave) or [] if isinstance(e, dict)]
                evidencias = [Evidencia(pagina_pdf=int(e.get("pagina_pdf") or 0), ubicacion=str(e.get("ubicacion") or ""),
                                        cita_textual=str(e.get("cita_textual") or ""),
                                        leido_de_figura=bool(e.get("leido_de_figura")), fila_tabla=e.get("fila_tabla"),
                                        columna_tabla=e.get("columna_tabla"), bloque_id=e.get("bloque_id"),
                                        ancla=e.get("ancla")) for e in crudas]
                inf = inferencias.get(col.clave)
                celdas[col.clave] = Celda.extraida(
                    clave=col.clave, valor=valor,
                    estado_dato=estados.get(col.clave) if valor is None and isinstance(estados, dict) else None,
                    tipo_valor=_tipo_valor(col.clave, valor, crudas, {str(k) for k in inferencias}), evidencias=evidencias,
                    inferencia=Inferencia(regla=str(inf.get("regla_aplicada") or inf.get("regla") or ""),
                                          razonamiento=str(inf.get("razonamiento") or ""))
                    if inf else None)
            auditoria = []
            for h in datos.auditoria:
                if h.get("estudio") not in (estudio, None):
                    continue
                h = {**h, "estudio": estudio}
                if h.get("columna") not in claves:  # hallazgos de fila o de trazabilidad
                    h["hallazgo"] = f"[{h.get('columna')}] {h.get('hallazgo')}"
                    h["columna"] = CLAVE_ESTUDIO
                auditoria.append(h)
            filas.append(FilaDeEfecto.extraida(
                proyecto_id=proyecto_id, estudio=estudio,
                documento=_entero_de_salida(fila, CLAVE_DOCUMENTO), articulo_id=datos.articulo_id,
                version_libro_id=datos.version_libro_id, celdas=celdas,
                trazabilidad={"salida": _sin_anclas(item), "auditoria": auditoria, **datos.trazabilidad_extra}))
        return filas

    def ejecutar(self, proyecto_id: uuid.UUID, datos: FilasDeExtraccion) -> list[FilaDeEfecto]:
        filas = self.armar(proyecto_id, datos)
        self._escribir.ejecutar(proyecto_id, filas)
        return filas


class RevisarCelda:
    """Aprobar, corregir o rechazar una celda (sección 5.4). El autor es el usuario de la sesión."""

    def __init__(self, udt: FabricaUdT, columnas: ConsultaDeColumnas) -> None:
        self._udt, self._columnas = udt, columnas

    def aprobar(self, proyecto_id: uuid.UUID, estudio: int, clave: str, *, autor: str,
                motivo: str | None = None) -> FilaDeEfecto:
        with self._udt() as u:
            fila = u.filas.por_estudio(proyecto_id, estudio)
            fila.aprobar_celda(clave, autor=autor, motivo=motivo)
            u.filas.agregar(fila)
            u.confirmar()
            return fila

    def corregir(self, proyecto_id: uuid.UUID, estudio: int, clave: str, *, autor: str, valor: Any,
                 motivo: str, estado_dato: str | None = None) -> FilaDeEfecto:
        definicion = next((c for c in self._columnas.columnas(proyecto_id) if c.clave == clave), None)
        if definicion is None:
            raise ErrorDeDominio(f"Columna desconocida: {clave}")
        with self._udt() as u:
            fila = u.filas.por_estudio(proyecto_id, estudio)
            fila.corregir_celda(clave, autor=autor, valor=valor, motivo=motivo, definicion=definicion,
                                estado_dato=estado_dato)
            u.filas.agregar(fila)
            u.confirmar()
            return fila

    def rechazar(self, proyecto_id: uuid.UUID, estudio: int, clave: str, *, autor: str,
                 motivo: str) -> FilaDeEfecto:
        with self._udt() as u:
            fila = u.filas.por_estudio(proyecto_id, estudio)
            fila.rechazar_celda(clave, autor=autor, motivo=motivo)
            u.filas.agregar(fila)
            u.confirmar()
            return fila


@dataclass
class CasosDeMatriz:
    importar: ImportarMatriz
    consultas: ConsultasDeMatriz
    marcar_version: MarcarVersionDeFilas
    escribir_extraidas: EscribirFilasExtraidas
    revisar: RevisarCelda
    escribir_extraccion: EscribirFilasDeExtraccion

"""Casos de uso de Matriz: importar la matriz vigente (filas HEREDADAS) y consultar filas y celdas."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.compartido.columnas import DefinicionDeColumna
from app.compartido.dominio import ErrorDeDominio, ahora
from app.compartido.normalizacion import norm
from app.contextos.matriz.dominio import derivadas
from app.contextos.matriz.dominio.fila import (
    REVISADAS,
    CambioDeCelda,
    Celda,
    EstadoRevision,
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


def _muestras_provisionales(columnas: list[DefinicionDeColumna], filas: list[dict[str, Any]]) -> dict[int, int]:
    """Número de muestra provisional por Estudio para las filas heredadas (ver derivadas.asignar_muestras)."""
    col = next((c for c in columnas if c.es_derivada and (c.derivada or {}).get("muestra_provisional_por")), None)
    if col is None or col.derivada is None:
        return {}
    datos = []
    for v in filas:
        e, d = v.get(CLAVE_ESTUDIO), v.get(CLAVE_DOCUMENTO)
        if isinstance(e, int | float) and isinstance(d, int | float):
            datos.append((int(e), int(d), v))
    return derivadas.asignar_muestras(col.derivada, datos)


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
            muestras = _muestras_provisionales(columnas, [
                {c.clave: f.valores.get(c.posicion) for c in columnas} for f in leida.filas])
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
                for col in columnas:  # las que calcula el programa (libro v2.3): provisionales en filas heredadas
                    if col.es_derivada:
                        fila.celdas[col.clave] = _celda_derivada(col, valores, {}, documento=documento,
                                                                 provisional=True, muestra=muestras.get(estudio, 1))
                        valores[col.clave] = fila.celdas[col.clave].valor
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


def _celda_derivada(col: DefinicionDeColumna, valores: dict[str, Any], trazabilidad: dict[str, Any], *,
                    documento: int | None, provisional: bool = False, muestra: int = 1) -> Celda:
    """Celda de una columna que calcula el programa (libro v2.3): inferida, con el porqué; sin valor, pendiente."""
    d = derivadas.calcular(col, valores, trazabilidad, documento=documento, provisional=provisional, muestra=muestra)
    if d.valor is None:
        return Celda.extraida(clave=col.clave, valor=None, estado_dato=None, tipo_valor=TipoValor.FALTANTE, evidencias=[])
    return Celda.extraida(clave=col.clave, valor=d.valor, estado_dato=None, tipo_valor=TipoValor.INFERIDO,
                          evidencias=[], inferencia=Inferencia(regla="Columna derivada (libro v2.3)",
                                                               razonamiento=d.razon))


@dataclass(frozen=True)
class ResultadoDeMigracion:
    filas: int
    celdas_agregadas: int
    calculadas: int


def _es_provisional(celda: Celda) -> bool:
    return celda.inferencia is not None and celda.inferencia.razonamiento.startswith("Provisional")


class AgregarColumnasDelLibro:
    """Agrega a las filas ya guardadas las columnas que el libro activo trae y la fila no tiene (libro v2.3).

    Las derivables se calculan (ID muestra provisional, Cultura Hofstede, y las que salgan de la trazabilidad);
    el resto queda pendiente. También recalcula las celdas provisionales de las filas heredadas (por ejemplo, el
    número de muestra por país y población). No lee PDF ni llama al modelo. Es idempotente.
    """

    def __init__(self, udt: FabricaUdT, columnas: ConsultaDeColumnas) -> None:
        self._udt, self._columnas = udt, columnas

    def ejecutar(self, proyecto_id: uuid.UUID) -> ResultadoDeMigracion:
        columnas = self._columnas.columnas(proyecto_id)
        version_id = self._columnas.version_activa_id(proyecto_id)
        agregadas = calculadas = filas_tocadas = 0
        with self._udt() as u:
            filas = u.filas.todas(proyecto_id)
            muestras = _muestras_provisionales(columnas, [
                {**f.valores(), CLAVE_ESTUDIO: f.estudio, CLAVE_DOCUMENTO: f.documento}
                for f in filas if f.origen.value == "HEREDADA"])
            for f in filas:
                heredada = f.origen.value == "HEREDADA"
                faltan = [c for c in columnas if c.clave not in f.celdas]
                # Se recalculan las derivadas provisionales (heredadas) y las de filas extraídas que nadie revisó.
                refrescar = [c for c in columnas if c.es_derivada and c.clave in f.celdas
                             and (_es_provisional(f.celdas[c.clave]) if heredada
                                  else f.celdas[c.clave].estado_revision not in REVISADAS)]
                if not faltan and not refrescar:
                    continue
                traz = ((f.trazabilidad.get("salida") or {}).get("trazabilidad") or {}) if not heredada else {}
                valores = f.valores()
                cambio = False
                for col in faltan + refrescar:
                    if col.es_derivada:
                        celda = _celda_derivada(col, valores, traz, documento=f.documento, provisional=heredada,
                                                muestra=muestras.get(f.estudio, 1))
                    else:
                        celda = Celda(clave=col.clave, valor=None, tipo_valor=TipoValor.FALTANTE,
                                      estado_revision=EstadoRevision.SIN_EVIDENCIA)
                    if col in refrescar and celda.valor == f.celdas[col.clave].valor:
                        continue
                    nueva = col in faltan
                    f.celdas[col.clave] = celda
                    cambio = True
                    agregadas += nueva
                    calculadas += celda.valor is not None
                if cambio:
                    filas_tocadas += 1
                    f.version_libro_id = version_id
                    u.filas.agregar(f)
            u.confirmar()
        return ResultadoDeMigracion(filas=filas_tocadas, celdas_agregadas=agregadas, calculadas=calculadas)


class ReasignarDocumento:
    """Cambia el Documento de un artículo (dato del equipo) y lo que de él depende: la celda Documento, la fila
    de la salida guardada y el ID muestra (D<Documento>-M<n>) en la celda y en la trazabilidad.

    Existe porque dos artículos con el mismo Documento comparten ID muestra y el metaanálisis de tres niveles los
    tomaría por la misma muestra. Rechaza un Documento que ya usa otro artículo.
    """

    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, documento: int, *, autor: str,
                 motivo: str) -> int:
        if documento < 1:
            raise ErrorDeDominio("El Documento es un entero positivo")
        with self._udt() as u:
            filas = u.filas.todas(proyecto_id)
            propias = [f for f in filas if f.articulo_id == articulo_id]
            if not propias:
                raise ErrorDeDominio("Ese artículo no tiene filas en la matriz")
            ajeno = next((f for f in filas if f.documento == documento and f.articulo_id != articulo_id), None)
            if ajeno is not None:
                raise ErrorDeDominio(f"El Documento {documento} ya lo usa otro artículo (Estudio {ajeno.estudio})")
            for f in propias:
                anterior = f.documento
                f.documento = documento
                celda = f.celdas.get(CLAVE_DOCUMENTO)
                if celda is not None:
                    celda.historial.append(CambioDeCelda(autor=autor, fecha=ahora(), accion="REASIGNAR_DOCUMENTO",
                                                         valor_anterior=celda.valor, valor_nuevo=documento,
                                                         motivo=motivo))
                    celda.valor = documento
                salida = f.trazabilidad.get("salida") or {}
                if isinstance(salida.get("fila"), dict):
                    salida["fila"][CLAVE_DOCUMENTO] = documento
                traz = salida.get("trazabilidad") or {}
                if isinstance(traz.get("id_muestra"), str):
                    traz["id_muestra"] = re.sub(r"^D\d+-", f"D{documento}-", traz["id_muestra"])
                id_celda = f.celdas.get("ID muestra")
                if id_celda is not None and isinstance(id_celda.valor, str):
                    nuevo = re.sub(r"^D\d+-", f"D{documento}-", id_celda.valor)
                    id_celda.historial.append(CambioDeCelda(
                        autor=autor, fecha=ahora(), accion="REASIGNAR_DOCUMENTO", valor_anterior=id_celda.valor,
                        valor_nuevo=nuevo, motivo=f"Documento {anterior} → {documento}: {motivo}"))
                    id_celda.valor = nuevo
                f.trazabilidad = {**f.trazabilidad, "salida": salida}
                u.filas.agregar(f)
            u.confirmar()
            return len(propias)


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
                if col.es_derivada:  # las calcula el programa al final, con las demás celdas
                    continue
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
            for col in columnas:
                if col.es_derivada:
                    celdas[col.clave] = _celda_derivada(col, fila, traz, documento=_entero_de_salida(fila, CLAVE_DOCUMENTO))
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
    agregar_columnas: AgregarColumnasDelLibro
    reasignar_documento: ReasignarDocumento
    escribir_extraidas: EscribirFilasExtraidas
    revisar: RevisarCelda
    escribir_extraccion: EscribirFilasDeExtraccion

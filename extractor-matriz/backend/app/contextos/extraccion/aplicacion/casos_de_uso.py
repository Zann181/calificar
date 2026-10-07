"""Caso de uso ExtraerArticulo (sección 8.3) y consultas de Extracción.

1. Número de Estudio inicial (el siguiente libre del proyecto, o el que indique el equipo).
2. Extractor → salida.
3. Validador; con errores, se reenvían al extractor (hasta MAX_ITERACIONES_VALIDADOR). Si persisten,
   la extracción queda FALLIDA y no se escribe nada en Matriz.
4. Anclaje de cada evidencia.
5. Auditor y codificador ciego en paralelo.
6. Comparación salida contra ciega en los campos críticos.
7. Conciliador para cada diferencia y cada hallazgo REFUTADO; su decisión también se ancla. Si cambia
   un valor, la salida se vuelve a validar.
8. Acuerdo en campos críticos.
9. ExtraccionCompletada: Matriz escribe las filas en POR_REVISAR (lo conecta app.composicion).
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.compartido.dominio import ErrorDeDominio
from app.contextos.extraccion.aplicacion import roles
from app.contextos.extraccion.dominio.anclaje import Anclador, NivelAncla, resumen_de_niveles
from app.contextos.extraccion.dominio.comparacion import (
    CAMPO_NUMERO_DE_FILAS,
    CRITICOS_TRAZABILIDAD,
    Comparacion,
    comparar,
)
from app.contextos.extraccion.dominio.documento import DocumentoDeTrabajo
from app.contextos.extraccion.dominio.etiquetado import TextoEtiquetado, necesita_capa, texto_etiquetado
from app.contextos.extraccion.dominio.extraccion import (
    Auditor,
    EstadoExtraccion,
    Extraccion,
    Hallazgo,
    Veredicto,
    veredicto_de,
)
from app.contextos.extraccion.dominio.libro import DatosDelEquipo, libro_para_sistema, regla_para_campo
from app.contextos.extraccion.puertos import (
    FuenteDeArticulos,
    FuenteDeNormas,
    LectorPdf,
    ModeloDeLenguaje,
    NumeracionDeEstudios,
    RespuestaModelo,
    UnidadDeTrabajoExtraccion,
    ValidadorDeExtraccion,
)

FabricaUdT = Callable[[], UnidadDeTrabajoExtraccion]
log = logging.getLogger("extraccion")

# Paso del artículo (Biblioteca) en el que falló cada estado de la extracción: el reintento parte de ahí.
PASO_DEL_ARTICULO = {
    EstadoExtraccion.EXTRAYENDO: "EXTRAYENDO", EstadoExtraccion.VALIDANDO: "EXTRAYENDO",
    EstadoExtraccion.ANCLANDO: "EXTRAYENDO", EstadoExtraccion.AUDITANDO: "AUDITANDO",
    EstadoExtraccion.CONCILIANDO: "AUDITANDO",
}


@dataclass(frozen=True)
class OpcionesDeExtraccion:
    documento: int
    estudio_inicial: int | None = None  # None: el siguiente libre del proyecto
    covidence: int | None = None
    via: str = "Covidence"
    confirmar_reextraccion: bool = False
    motivo: str | None = None


@dataclass(frozen=True)
class ParametrosDelMotor:
    max_iteraciones_validador: int = 3
    umbral_similitud: float = 95
    concurrencia: int = 2


@dataclass
class ResultadoExtraccion:
    extraccion_id: uuid.UUID
    estado: str
    estudios: list[int] = field(default_factory=list)
    acuerdo: float | None = None
    anclas: dict[str, int] = field(default_factory=dict)
    hallazgos_pendientes: int = 0
    errores: list[str] = field(default_factory=list)
    costo_usd: float = 0.0


@dataclass
class _Contexto:
    libro: dict[str, Any]
    libro_sistema: str
    pdf: bytes
    documento: DocumentoDeTrabajo
    etiquetado: TextoEtiquetado
    imagenes: dict[str, bytes]
    datos: DatosDelEquipo


@dataclass
class _Punto:
    """Algo que el conciliador debe decidir: una diferencia con el ciego o un hallazgo REFUTADO."""

    indice_hallazgo: int
    fila: int | None
    estudio: Any
    campo: str
    valor_extractor: Any
    valor_alternativo: Any
    origen: str
    detalle: Any
    bloques: str


class ExtraerArticulo:
    def __init__(self, udt: FabricaUdT, articulos: FuenteDeArticulos, normas: FuenteDeNormas,
                 numeracion: NumeracionDeEstudios, modelo: ModeloDeLenguaje, validador: ValidadorDeExtraccion,
                 lector: LectorPdf, parametros: ParametrosDelMotor | None = None) -> None:
        self._udt, self._articulos, self._normas, self._numeracion = udt, articulos, normas, numeracion
        self._modelo, self._validador, self._lector = modelo, validador, lector
        self._p = parametros or ParametrosDelMotor()

    # ------------------------------------------------------------------ principal
    def ejecutar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID,
                 opciones: OpcionesDeExtraccion) -> ResultadoExtraccion:
        self._articulos.iniciar(proyecto_id, articulo_id, confirmar_reextraccion=opciones.confirmar_reextraccion,
                                motivo=opciones.motivo)
        articulo = self._articulos.obtener(proyecto_id, articulo_id)
        libro = self._normas.libro_activo(proyecto_id)
        estudio = opciones.estudio_inicial or self._numeracion.siguiente(proyecto_id)
        ext = Extraccion.iniciar(proyecto_id=proyecto_id, articulo_id=articulo_id, version_libro_id=libro.id,
                                 estudios_reservados=[estudio])
        self._guardar(ext)
        try:
            datos = DatosDelEquipo(documento=opciones.documento, estudio_inicial=estudio,
                                   covidence=opciones.covidence, via=opciones.via)
            ctx = self._preparar(libro.contenido, articulo.pdf, articulo.documento, datos)
            if not self._extraer(ext, ctx):
                return self._resultado(ext)
            self._anclar(ext, ctx)
            self._articulos.pasar_a_auditoria(proyecto_id, articulo_id)
            comparacion = self._auditar(ext, ctx)
            self._conciliar(ext, ctx, comparacion)
            ext.completar(acuerdo=comparar(ext.salida, ext.codificacion_ciega).acuerdo)
            self._guardar(ext)
        except Exception as e:
            log.exception("Extracción %s del artículo %s falló en %s", ext.id, articulo_id, ext.estado)
            self._fallar(ext, f"{type(e).__name__}: {e}")
        return self._resultado(ext)

    # ------------------------------------------------------------------ pasos
    def _preparar(self, libro: dict[str, Any], pdf: bytes, documento: dict[str, Any],
                  datos: DatosDelEquipo) -> _Contexto:
        doc = DocumentoDeTrabajo.desde_dict(documento)
        pedir = {b.id: (b.pagina, b.rect) for b in doc.bloques if necesita_capa(b)}
        capa = self._lector.textos_en_rect(pdf, pedir) if pedir else {}
        paginas = doc.paginas_con_imagen()
        imagenes = {f"pag-{p:02d}.png": png for p, png in self._lector.renderizar(pdf, paginas).items()} if paginas else {}
        return _Contexto(libro=libro, libro_sistema=libro_para_sistema(libro), pdf=pdf, documento=doc,
                         etiquetado=texto_etiquetado(doc, capa), imagenes=imagenes, datos=datos)

    def _llamar(self, ext: Extraccion, rol: str, sistema: str, mensaje: str, ctx: _Contexto,
                con_imagenes: bool = True) -> RespuestaModelo:
        r = self._modelo.completar(rol=rol, sistema=sistema, mensaje=mensaje,
                                   imagenes=ctx.imagenes if con_imagenes else None)
        ext.registrar_uso(rol, r.uso)
        return r

    def _extraer(self, ext: Extraccion, ctx: _Contexto) -> bool:
        """Pasos 2 y 3. Devuelve False si la salida no pasó el validador."""
        sistema, mensaje = roles.extractor(ctx.libro, ctx.libro_sistema, ctx.datos, ctx.etiquetado.texto,
                                           sorted(ctx.imagenes))
        salida = roles.lista_de(self._llamar(ext, "extractor", sistema, mensaje, ctx).texto)
        for iteracion in range(1, self._p.max_iteraciones_validador + 1):
            ext.registrar_salida(salida)
            r = self._validador.validar(salida, ctx.libro, ctx.pdf)
            ext.registrar_validacion(r.errores, r.avisos)
            self._guardar(ext)
            if not r.errores:
                return True
            if iteracion == self._p.max_iteraciones_validador:
                break
            ext.pasar(EstadoExtraccion.EXTRAYENDO)
            texto = self._llamar(ext, "extractor", sistema, roles.correccion(mensaje, salida, r.errores), ctx).texto
            salida = roles.lista_de(texto)
        self._fallar(ext, f"El validador mantiene {len(ext.errores_validador)} errores tras "
                          f"{ext.iteraciones_validador} iteraciones: " + " | ".join(ext.errores_validador[:10]))
        return False

    def _anclador(self, ctx: _Contexto) -> Anclador:
        return Anclador(ctx.documento, ctx.etiquetado.efectivo_norm, self._p.umbral_similitud)

    def _anclar(self, ext: Extraccion, ctx: _Contexto) -> None:
        ext.pasar(EstadoExtraccion.ANCLANDO)
        ext.registrar_anclas(self._anclador(ctx).anclar_salida(ext.salida))
        self._guardar(ext)

    def _auditar(self, ext: Extraccion, ctx: _Contexto) -> Comparacion:
        ext.pasar(EstadoExtraccion.AUDITANDO)
        self._guardar(ext)
        imagenes = sorted(ctx.imagenes)
        s_aud, m_aud = roles.auditor(ctx.libro_sistema, ext.salida, [a.a_dict() for a in ext.anclas],
                                     ctx.etiquetado.texto, imagenes)
        s_cie, m_cie = roles.ciego(ctx.libro_sistema, ctx.datos, ctx.etiquetado.texto, imagenes)
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_aud = ex.submit(self._modelo.completar, rol="auditor", sistema=s_aud, mensaje=m_aud, imagenes=ctx.imagenes)
            f_cie = ex.submit(self._modelo.completar, rol="ciego", sistema=s_cie, mensaje=m_cie, imagenes=ctx.imagenes)
            r_aud, r_cie = f_aud.result(), f_cie.result()
        ext.registrar_uso("auditor", r_aud.uso)
        ext.registrar_uso("ciego", r_cie.uso)
        auditoria = roles.lista_de(r_aud.texto) if r_aud.texto.strip() not in ("", "[]") else []
        ciega = roles.lista_de(r_cie.texto)
        hallazgos = [Hallazgo(estudio=_entero(h.get("estudio")), columna=str(h.get("columna") or "Estudio"),
                              auditor=Auditor.AUDITOR_EVIDENCIA, veredicto=veredicto_de(h.get("veredicto")),
                              detalle=str(h.get("hallazgo") or ""), evidencia_propuesta=h.get("evidencia"))
                     for h in auditoria]
        hallazgos = [h for h in hallazgos if h.veredicto != Veredicto.CONFIRMADO]
        comparacion = comparar(ext.salida, ciega)
        for d in comparacion.diferencias:
            evidencia = None
            if d.fila is not None and d.fila < len(ciega):
                evidencia = ((ciega[d.fila].get("trazabilidad") or {}).get("evidencia") or {}).get(d.campo)
            hallazgos.append(Hallazgo(
                estudio=_entero(d.estudio), columna=d.campo, auditor=Auditor.CODIFICADOR_CIEGO,
                veredicto=Veredicto.REFUTADO, evidencia_propuesta=evidencia,
                detalle=f"Extractor: {json.dumps(d.valor_a, ensure_ascii=False)}; "
                        f"codificador ciego: {json.dumps(d.valor_b, ensure_ascii=False)}"))
        ext.registrar_hallazgos(ciega, hallazgos)
        self._guardar(ext)
        return comparacion

    def _puntos(self, ext: Extraccion, ctx: _Contexto, comparacion: Comparacion) -> list[_Punto]:
        salida, ciega, por_bloque = ext.salida, ext.codificacion_ciega, ctx.etiquetado.por_bloque
        puntos: list[_Punto] = []
        diferencias = iter(comparacion.diferencias)
        for i, h in enumerate(ext.hallazgos):
            if h.auditor == Auditor.CODIFICADOR_CIEGO:
                d = next(diferencias)
                fila_a = salida[d.fila] if d.fila is not None and d.fila < len(salida) else {}
                fila_b = ciega[d.fila] if d.fila is not None and d.fila < len(ciega) else {}
                puntos.append(_Punto(i, d.fila, d.estudio, d.campo, d.valor_a, d.valor_b, "Codificador ciego",
                                     h.detalle, roles.bloques_citados(por_bloque, fila_a, fila_b)))
            elif h.veredicto == Veredicto.REFUTADO:
                fila = _posicion_de_estudio(salida, h.estudio)
                valor = _valor(salida[fila], h.columna) if fila is not None else None
                puntos.append(_Punto(i, fila, h.estudio, h.columna, valor, h.evidencia_propuesta,
                                     "Auditor de evidencia", h.detalle,
                                     roles.bloques_citados(por_bloque, h.evidencia_propuesta,
                                                           salida[fila] if fila is not None else salida)))
        return puntos

    def _decidir(self, ctx: _Contexto, p: _Punto) -> tuple[dict[str, Any], dict[str, Any]]:
        mensaje = roles.conciliador(estudio=p.estudio, campo=p.campo, valor_extractor=p.valor_extractor,
                                    valor_alternativo=p.valor_alternativo, origen=p.origen, detalle=p.detalle,
                                    regla=regla_para_campo(ctx.libro, p.campo), bloques=p.bloques)
        try:
            r = self._modelo.completar(rol="conciliador", sistema=roles.SISTEMA_CONCILIADOR, mensaje=mensaje)
        except Exception as e:  # una conciliación que falla queda PENDIENTE; no tumba la extracción
            return {"decision": "PENDIENTE", "razonamiento": f"Error al llamar al conciliador: {e}"}, {}
        try:
            decision = roles.json_de(r.texto)
        except roles.RespuestaInvalida as e:
            decision = {"decision": "PENDIENTE", "razonamiento": str(e)}
        return (decision if isinstance(decision, dict) else {"decision": "PENDIENTE"}), r.uso

    def _conciliar(self, ext: Extraccion, ctx: _Contexto, comparacion: Comparacion) -> None:
        ext.pasar(EstadoExtraccion.CONCILIANDO)
        puntos = self._puntos(ext, ctx, comparacion)
        with ThreadPoolExecutor(max_workers=max(1, self._p.concurrencia)) as ex:
            decisiones = list(ex.map(lambda p: self._decidir(ctx, p), puntos))
        anclador = self._anclador(ctx)
        nueva = copy.deepcopy(ext.salida)
        con_cambio = list(ext.hallazgos)  # si se aplican los cambios
        sin_cambio = list(ext.hallazgos)  # si el validador los rechaza
        cambios = 0
        for p, (d, uso) in zip(puntos, decisiones, strict=True):
            if uso:
                ext.registrar_uso("conciliador", uso)
            h = ext.hallazgos[p.indice_hallazgo]
            tipo = str(d.get("decision") or "PENDIENTE").upper()
            razon = str(d.get("razonamiento") or "")
            if tipo == "VALOR_EXTRACTOR":
                con_cambio[p.indice_hallazgo] = sin_cambio[p.indice_hallazgo] = h.resolver(
                    f"Conciliador: se mantiene el valor del extractor. {razon}".strip())
                continue
            if tipo in ("VALOR_ALTERNATIVO", "OTRO"):
                motivo = self._aplicar(nueva, p, d, anclador)
                if motivo is None:
                    cambios += 1
                    con_cambio[p.indice_hallazgo] = h.resolver(
                        f"Conciliador: {json.dumps(d.get('valor'), ensure_ascii=False)} "
                        f"({d.get('bloque_id')}). {razon}".strip())
                    sin_cambio.append(_pendiente(p, "El cambio del conciliador no pasó el validador; "
                                                    f"propuesta: {json.dumps(d.get('valor'), ensure_ascii=False)}. {razon}"))
                    continue
                razon = f"{motivo}. {razon}"
            nota = _pendiente(p, f"PENDIENTE para el responsable del dominio. {razon}".strip())
            con_cambio.append(nota)
            sin_cambio.append(nota)
        if cambios:
            r = self._validador.validar(nueva, ctx.libro, ctx.pdf)
            aplicada = ext.aplicar_conciliacion(salida=nueva, anclas=anclador.anclar_salida(nueva), hallazgos=con_cambio,
                                                errores=r.errores, avisos=r.avisos)
            if not aplicada:
                ext.registrar_conciliacion(sin_cambio)
        else:
            ext.registrar_conciliacion(con_cambio)
        self._guardar(ext)

    @staticmethod
    def _aplicar(salida: list[dict[str, Any]], p: _Punto, d: dict[str, Any], anclador: Anclador) -> str | None:
        """Aplica la decisión en `salida`. Devuelve None si la aplicó o el motivo por el que no."""
        if p.campo == CAMPO_NUMERO_DE_FILAS or p.fila is None or p.fila >= len(salida):
            return "El conciliador no puede abrir ni cerrar filas"
        if "valor" not in d:
            return "La decisión no trae valor"
        item = salida[p.fila]
        fila, traz = item.setdefault("fila", {}), item.setdefault("trazabilidad", {})
        if p.campo not in fila and p.campo not in CRITICOS_TRAZABILIDAD and p.campo not in traz:
            return f"Campo desconocido: {p.campo}"
        evidencia = {"pagina_pdf": None, "ubicacion": "Conciliación", "fila_tabla": None, "columna_tabla": None,
                     "cita_textual": str(d.get("cita_textual") or ""), "leido_de_figura": False,
                     "bloque_id": d.get("bloque_id")}
        estudio = _entero(fila.get("Estudio")) or 0
        bloque = anclador.documento.bloque(d.get("bloque_id"))
        evidencia["pagina_pdf"] = bloque.pagina if bloque else None
        ancla = anclador.anclar(evidencia, estudio=estudio, columna=p.campo, indice=0)
        if ancla.nivel == NivelAncla.NO_VERIFICABLE:
            return "La cita del conciliador no se encontró en el artículo"
        evidencia["pagina_pdf"] = ancla.pagina
        if p.campo in fila:
            fila[p.campo] = d["valor"]
            traz.setdefault("evidencia", {})[p.campo] = [evidencia]
        else:
            traz[p.campo] = d["valor"]
        return None

    # ------------------------------------------------------------------ apoyo
    def _guardar(self, ext: Extraccion) -> None:
        with self._udt() as u:
            u.extracciones.agregar(ext)
            u.confirmar()

    def _fallar(self, ext: Extraccion, mensaje: str) -> None:
        paso = PASO_DEL_ARTICULO.get(ext.estado, "EXTRAYENDO")
        if not ext.terminada:
            ext.fallar(mensaje)
        self._guardar(ext)
        self._articulos.fallar(ext.proyecto_id, ext.articulo_id, paso, mensaje)

    @staticmethod
    def _resultado(ext: Extraccion) -> ResultadoExtraccion:
        return ResultadoExtraccion(
            extraccion_id=ext.id, estado=ext.estado.value,
            estudios=[int(f["fila"]["Estudio"]) for f in ext.salida] if ext.estado == EstadoExtraccion.COMPLETADA else [],
            acuerdo=ext.acuerdo_campos_criticos, anclas=resumen_de_niveles(ext.anclas),
            hallazgos_pendientes=sum(h.estado.value == "PENDIENTE" for h in ext.hallazgos),
            errores=list(ext.errores_validador) or ([ext.error] if ext.error else []),
            costo_usd=round(sum(float(r.get("costo_usd") or 0) for r in ext.uso_tokens.values()), 4))


def _entero(valor: Any) -> int | None:
    try:
        return int(valor) if valor is not None and not isinstance(valor, bool) else None
    except (TypeError, ValueError):
        return None


def _posicion_de_estudio(salida: list[dict[str, Any]], estudio: int | None) -> int | None:
    for i, item in enumerate(salida):
        if _entero((item.get("fila") or {}).get("Estudio")) == estudio:
            return i
    return 0 if len(salida) == 1 else None


def _valor(item: dict[str, Any], campo: str) -> Any:
    fila = item.get("fila") or {}
    return fila[campo] if campo in fila else (item.get("trazabilidad") or {}).get(campo)


def _pendiente(p: _Punto, detalle: str) -> Hallazgo:
    return Hallazgo(estudio=_entero(p.estudio), columna=p.campo, auditor=Auditor.CONCILIADOR,
                    veredicto=Veredicto.NO_VERIFICABLE, detalle=detalle)


class ConsultasDeExtraccion:
    def __init__(self, udt: FabricaUdT) -> None:
        self._udt = udt

    def obtener(self, proyecto_id: uuid.UUID, extraccion_id: uuid.UUID) -> Extraccion:
        with self._udt() as u:
            return u.extracciones.obtener(proyecto_id, extraccion_id)

    def de_articulo(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> list[Extraccion]:
        with self._udt() as u:
            return u.extracciones.de_articulo(proyecto_id, articulo_id)

    def ultima_completada(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> Extraccion:
        completadas = [e for e in self.de_articulo(proyecto_id, articulo_id) if e.estado == EstadoExtraccion.COMPLETADA]
        if not completadas:
            raise ErrorDeDominio("El artículo no tiene extracciones completadas")
        return max(completadas, key=lambda e: e.iniciada_en)


@dataclass
class CasosDeExtraccion:
    extraer: ExtraerArticulo
    consultas: ConsultasDeExtraccion


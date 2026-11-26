"""Casos de uso de Descubrimiento: buscar, listar y decidir sobre candidatos.

Nada aquí escribe en la matriz ni llama a un modelo de lenguaje: lo encontrado son indicios, y quien decide es la persona.
Los fallos de una fuente se registran como ERROR (origen «descubrimiento») y no detienen a las demás.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import date

from app.compartido.dominio import ErrorDeDominio, ahora
from app.contextos.descubrimiento.aplicacion.analizar import AnalizarTextoCompleto
from app.contextos.descubrimiento.aplicacion.columnas import EvaluarCandidatos, GestionarPerfiles
from app.contextos.descubrimiento.aplicacion.importar import ImportarCandidatos
from app.contextos.descubrimiento.dominio.busqueda import (
    Busqueda,
    ConsultaDeBusqueda,
    EstadoDeFuente,
    Origen,
    ProgresoDeFuente,
    consulta_inicial,
)
from app.contextos.descubrimiento.dominio.candidato import (
    Candidato,
    EstadoCandidato,
    RegistroBibliografico,
    clave_del_registro,
    mismo_trabajo,
    titulo_plano,
)
from app.contextos.descubrimiento.dominio.errores import ErrorDeEstructura, ErrorDeFuente
from app.contextos.descubrimiento.dominio.sitios import EstadoDeSesion, SitioConCredenciales
from app.contextos.descubrimiento.puertos import (
    CatalogoDeSitios,
    ComprobadorDePdf,
    EstadoDeSesiones,
    FuenteDeLiteratura,
    RepositorioDeBusquedas,
    RepositorioDeCandidatos,
    SaludDeFuentes,
    TitulosEnMatriz,
)

log = logging.getLogger("descubrimiento")
MAX_PDFS_POR_REGISTRO = 3
TAMANO_DE_TANDA = 16  # resultados cuyos PDF se comprueban a la vez

Lanzador = Callable[[Callable[[], None]], None]


def lanzar_en_hilo(trabajo: Callable[[], None]) -> None:
    threading.Thread(target=trabajo, name="descubrimiento", daemon=True).start()


def lanzar_aqui(trabajo: Callable[[], None]) -> None:
    """Para las pruebas: la búsqueda corre de inmediato, en el mismo hilo."""
    trabajo()


def esta_en_matriz(titulo: str, titulos_planos: set[str], titulos_matriz: list[str]) -> bool:
    plano_ = titulo_plano(titulo)
    if not plano_:
        return False
    return plano_ in titulos_planos or any(mismo_trabajo(titulo, None, t, None) for t in titulos_matriz)


@dataclass(frozen=True)
class FuenteDisponible:
    nombre: str
    etiqueta: str
    sitio_id: str | None
    sesion: EstadoDeSesion | None  # None: fuente abierta, no necesita sesión
    desactivada: str | None = None  # el motivo, si se apagó sola por fallos de estructura seguidos

    @property
    def utilizable(self) -> bool:
        return self.desactivada is None and (self.sesion is None or self.sesion == EstadoDeSesion.VIGENTE)


@dataclass(frozen=True)
class FuenteNoDisponible:
    """Una fuente que se pensó y **no** se ofrece, con el motivo (p. ej. su robots.txt lo prohíbe)."""

    id: str
    etiqueta: str
    motivo: str


def _por_tandas(registros: Iterable[RegistroBibliografico], n: int) -> Iterator[list[RegistroBibliografico]]:
    """Grupos de hasta `n`. Si la fuente falla a mitad de camino, lo que alcanzó a traer se entrega antes del error."""
    tanda: list[RegistroBibliografico] = []
    try:
        for r in registros:
            tanda.append(r)
            if len(tanda) == n:
                yield tanda
                tanda = []
    except Exception:
        if tanda:
            yield tanda
        raise
    if tanda:
        yield tanda


class EjecutarBusqueda:
    def __init__(self, busquedas: RepositorioDeBusquedas, candidatos: RepositorioDeCandidatos,
                 fuentes: Mapping[str, FuenteDeLiteratura], titulos: TitulosEnMatriz, sesiones: EstadoDeSesiones,
                 pdf: ComprobadorDePdf, lanzar: Lanzador = lanzar_en_hilo, hoy: Callable[[], date] = date.today,
                 salud: SaludDeFuentes | None = None,
                 al_cambiar: Callable[[uuid.UUID], None] = lambda _pid: None,
                 origen: Origen = Origen.EQUIPO) -> None:
        self._busquedas, self._candidatos, self._fuentes = busquedas, candidatos, fuentes
        self._titulos, self._sesiones, self._lanzar, self._hoy = titulos, sesiones, lanzar, hoy
        self._pdf = pdf
        self._salud = salud
        self._al_cambiar = al_cambiar
        self._canceladas: set[uuid.UUID] = set()
        self._origen = origen
        self._cerrojo = threading.Lock()

    def iniciar(self, proyecto_id: uuid.UUID, nombre: str, consulta: ConsultaDeBusqueda, fuentes: tuple[str, ...],
                limite_por_fuente: int = 200) -> Busqueda:
        desconocidas = [f for f in fuentes if f not in self._fuentes]
        if desconocidas:
            raise ErrorDeDominio(f"Fuente desconocida: {', '.join(desconocidas)}")
        b = Busqueda.crear(proyecto_id=proyecto_id, nombre=nombre, consulta=consulta, fuentes=fuentes,
                           limite_por_fuente=limite_por_fuente, origen=self._origen)
        with self._cerrojo:
            # En la web hay varios lectores y un servidor pequeño: una búsqueda a la vez (ADR 0012).
            if self._origen == Origen.NUBE and any(o.proyecto_id == proyecto_id for o in self._busquedas.en_curso()):
                raise ErrorDeDominio("Ya hay una búsqueda en curso: espere a que termine o cancélela")
            self._busquedas.guardar(b)
        log.info("Búsqueda «%s» iniciada en %s (%d–%s)", b.nombre, ", ".join(fuentes), consulta.filtros.desde,
                 consulta.filtros.hasta or "hoy")
        self._lanzar(lambda: self.correr(proyecto_id, b.id))
        return b

    def cancelar(self, busqueda_id: uuid.UUID) -> None:
        self._canceladas.add(busqueda_id)

    def cerrar_interrumpidas(self) -> int:
        """Al arrancar la aplicación: una búsqueda que sigue «en curso» se cortó al cerrarla y nadie la va a terminar.

        Queda terminada con errores, conserva lo que alcanzó a encontrar y así también puede viajar a la nube."""
        cortadas = self._busquedas.en_curso()
        for b in cortadas:
            for p in b.progreso.values():
                if p.estado in (EstadoDeFuente.PENDIENTE, EstadoDeFuente.BUSCANDO):
                    p.estado, p.errores = EstadoDeFuente.ERROR, p.errores + 1
                    p.ultimo_error = "Interrumpida: la aplicación se cerró o el servidor se reinició durante la búsqueda"
            b.total_unicos = len(self._busquedas.candidatos_de(b.id))
            b.terminar(cuando=ahora())
            self._busquedas.guardar(b)
            log.error("Búsqueda «%s» interrumpida al cerrar la aplicación; quedan %d candidatos. Repítala para completarla",
                      b.nombre, b.total_unicos)
        return len(cortadas)

    def correr(self, proyecto_id: uuid.UUID, busqueda_id: uuid.UUID) -> None:
        b = self._busquedas.obtener(proyecto_id, busqueda_id)
        hoy = self._hoy()
        titulos_matriz = self._titulos.titulos(proyecto_id)
        planos = {titulo_plano(t) for t in titulos_matriz}
        indice = self._candidatos.indice(proyecto_id)
        por_clave = {clave: cid for cid, clave, _t, _a in indice}
        # Lo que el equipo ya tiene no se toca desde la web: así el próximo envío no encuentra diferencias que pisar.
        intocables = self._busquedas.candidatos_del_equipo(proyecto_id) if b.origen == Origen.NUBE else set()
        con_pdf = self._candidatos.con_pdf(proyecto_id)
        comprobados: dict[str, bool] = {}  # cada enlace se prueba una sola vez por búsqueda
        vistos: set[uuid.UUID] = set()
        cancelada = False
        for nombre in b.fuentes:
            if busqueda_id in self._canceladas:
                cancelada = True
                break
            fuente = self._fuentes[nombre]
            progreso = b.progreso[nombre]
            frágil = self._salud is not None and getattr(fuente, "autodesactivable", False)
            motivo_apagada = self._salud.desactivada(nombre) if self._salud and frágil else None
            if motivo_apagada:
                progreso.estado = EstadoDeFuente.OMITIDA
                progreso.errores += 1
                progreso.ultimo_error = f"Desactivada: {motivo_apagada}"
                log.error("%s: omitida, está desactivada (%s). Reactívela desde la pestaña cuando el sitio vuelva a responder bien",
                          fuente.etiqueta, motivo_apagada)
                self._busquedas.guardar(b)
                continue
            if fuente.sitio_id and self._sesiones.estado(fuente.sitio_id) != EstadoDeSesion.VIGENTE:
                progreso.estado = EstadoDeFuente.OMITIDA
                progreso.errores += 1
                progreso.ultimo_error = "Sin sesión: inicie sesión en el sitio y vuelva a buscar"
                log.error("%s: omitida, no hay sesión vigente en «%s»", fuente.etiqueta, fuente.sitio_id)
                self._busquedas.guardar(b)
                continue
            progreso.estado = EstadoDeFuente.BUSCANDO
            self._busquedas.guardar(b)
            try:
                admitidos = (r for r in fuente.buscar(b.consulta, b.limite_por_fuente, hoy)
                             if self._admite(b.consulta, r, hoy))
                for r, existente in self._con_pdf_probados(admitidos, por_clave, indice, con_pdf, comprobados):
                    if busqueda_id in self._canceladas:
                        cancelada = True
                        break
                    if existente not in con_pdf:  # solo entra lo que entrega un PDF gratuito (ADR 0013)
                        url = self._pdf_que_entrega(r, comprobados)
                        if url is None:
                            progreso.sin_pdf += 1
                            self._avisar_avance(b, progreso)
                            continue
                        r = replace(r, url_pdf=url)
                    progreso.encontrados += 1
                    c, nuevo = self._incorporar(proyecto_id, r, existente, por_clave, indice, planos, titulos_matriz,
                                                intocables)
                    progreso.nuevos += 1 if nuevo else 0
                    vistos.add(c.id)
                    if c.url_pdf:
                        con_pdf.add(c.id)
                    self._busquedas.registrar_hallazgo(b.id, c.id, nombre, r.posicion)
                    self._avisar_avance(b, progreso)
                progreso.estado = EstadoDeFuente.LISTA
                if self._salud and frágil:
                    self._salud.exito(nombre)
            except ErrorDeFuente as e:
                progreso.estado, progreso.errores, progreso.ultimo_error = EstadoDeFuente.ERROR, progreso.errores + 1, e.causa
                log.error("%s: la búsqueda quedó incompleta (%s)", fuente.etiqueta, e.causa)
                if isinstance(e, ErrorDeEstructura) and self._salud and frágil and self._salud.fallo_de_estructura(
                        nombre, e.causa):
                    log.error("%s: se desactivó sola tras fallos seguidos de estructura: el sitio cambió y el adaptador ya no "
                              "lo entiende. No devolverá resultados hasta que se corrija y se reactive", fuente.etiqueta)
            except Exception as e:  # una fuente rota nunca tumba la búsqueda
                progreso.estado, progreso.errores = EstadoDeFuente.ERROR, progreso.errores + 1
                progreso.ultimo_error = f"{type(e).__name__}: {e}"[:300]
                log.exception("%s: fallo inesperado", fuente.etiqueta)
            self._busquedas.guardar(b)
            if cancelada:
                break
        b.total_unicos = len(vistos)
        b.terminar(cancelada=cancelada, cuando=ahora())
        self._busquedas.guardar(b)
        self._canceladas.discard(busqueda_id)
        resumen = ", ".join(f"{n}: {p.encontrados}" for n, p in b.progreso.items())
        if b.errores:
            malas = ", ".join(n for n, p in b.progreso.items() if p.errores)
            log.error("Búsqueda «%s» terminó con errores en %s (%d candidatos únicos; %s)", b.nombre, malas,
                      b.total_unicos, resumen)
        else:
            log.info("Búsqueda «%s» terminada: %d candidatos únicos (%s)", b.nombre, b.total_unicos, resumen)
        self._al_cambiar(proyecto_id)

    @staticmethod
    def _admite(consulta: ConsultaDeBusqueda, r: RegistroBibliografico, hoy: date) -> bool:
        """Red de seguridad: cada fuente filtra por su cuenta, pero no todas con la misma exactitud."""
        f = consulta.filtros
        if r.anio is not None and not f.desde <= r.anio <= f.hasta_efectivo(hoy):
            return False
        if r.es_preprint and not f.incluir_preprints:
            return False
        return bool(r.titulo.strip())

    def _avisar_avance(self, b: Busqueda, p: ProgresoDeFuente) -> None:
        """Comprobar los PDF toma tiempo: el avance se guarda cada pocos resultados para que se vea."""
        if (p.encontrados + p.sin_pdf) % 5 == 0:
            self._busquedas.guardar(b)

    def _con_pdf_probados(self, registros: Iterable[RegistroBibliografico], por_clave: dict[str, uuid.UUID],
                          indice: list[tuple[uuid.UUID, str, str, int | None]], con_pdf: set[uuid.UUID],
                          comprobados: dict[str, bool]) -> Iterator[tuple[RegistroBibliografico, uuid.UUID | None]]:
        """Los resultados en su orden, cada uno con su candidato si ya existe; antes de entregarlos por tandas se
        prueban a la vez los enlaces de los que todavía no tienen un PDF comprobado."""
        for tanda in _por_tandas(registros, TAMANO_DE_TANDA):
            self._probar([r for r in tanda if self._existente(r, por_clave, indice) not in con_pdf], comprobados)
            for r in tanda:  # el candidato se mira ahora: uno anterior de la misma tanda pudo haberlo creado
                yield r, self._existente(r, por_clave, indice)

    def _probar(self, registros: list[RegistroBibliografico], comprobados: dict[str, bool]) -> None:
        """Primero el mejor enlace de cada resultado; a quien le falle, el siguiente. Cada enlace, una sola vez."""
        for turno in range(MAX_PDFS_POR_REGISTRO):
            urls = [r.pdfs[turno] for r in registros
                    if len(r.pdfs) > turno and r.pdfs[turno] not in comprobados
                    and not any(comprobados.get(u) for u in r.pdfs[:turno])]
            if urls:
                comprobados.update(self._pdf.entregan(urls))

    @staticmethod
    def _pdf_que_entrega(r: RegistroBibliografico, comprobados: dict[str, bool]) -> str | None:
        return next((u for u in r.pdfs[:MAX_PDFS_POR_REGISTRO] if comprobados.get(u)), None)

    @staticmethod
    def _existente(r: RegistroBibliografico, por_clave: dict[str, uuid.UUID],
                   indice: list[tuple[uuid.UUID, str, str, int | None]]) -> uuid.UUID | None:
        """El candidato que ya es este mismo trabajo: por su identificador o, sin él, por un título casi igual."""
        por_identificador = por_clave.get(clave_del_registro(r))
        if por_identificador is not None:
            return por_identificador
        return next((cid for cid, _k, t, a in indice if mismo_trabajo(r.titulo, r.anio, t, a)), None)

    def _incorporar(self, proyecto_id: uuid.UUID, r: RegistroBibliografico, existente_id: uuid.UUID | None,
                    por_clave: dict[str, uuid.UUID], indice: list[tuple[uuid.UUID, str, str, int | None]],
                    planos: set[str], titulos_matriz: list[str], intocables: set[uuid.UUID]) -> tuple[Candidato, bool]:
        if existente_id is not None:
            c = self._candidatos.obtener(proyecto_id, existente_id)
            sin_pdf = c.url_pdf is None
            cambio = c.absorber(r)
            ahora_en_matriz = esta_en_matriz(c.titulo, planos, titulos_matriz)
            if ahora_en_matriz != c.en_matriz:
                c.en_matriz, cambio = ahora_en_matriz, True
            if c.id not in intocables:
                if cambio:
                    self._candidatos.guardar(c)
            elif sin_pdf and c.url_pdf:  # lo único que la web le añade a uno del equipo: sin ello no se vería
                self._candidatos.anotar_pdf(c.id, c.url_pdf)
            por_clave.setdefault(c.clave, c.id)
            return c, False
        c = Candidato.desde(proyecto_id, r)
        c.en_matriz = esta_en_matriz(c.titulo, planos, titulos_matriz)
        self._candidatos.guardar(c)
        por_clave[c.clave] = c.id
        indice.append((c.id, c.clave, c.titulo, c.anio))
        return c, True


@dataclass(frozen=True)
class ListadoDeCandidatos:
    candidatos: list[Candidato]
    total: int
    contadores: dict[str, int]


class ConsultasDeDescubrimiento:
    def __init__(self, busquedas: RepositorioDeBusquedas, candidatos: RepositorioDeCandidatos,
                 fuentes: Mapping[str, FuenteDeLiteratura], sitios: CatalogoDeSitios,
                 sesiones: EstadoDeSesiones, salud: SaludDeFuentes | None = None,
                 no_disponibles: tuple[FuenteNoDisponible, ...] = ()) -> None:
        self._busquedas, self._candidatos, self._fuentes = busquedas, candidatos, fuentes
        self._sitios, self._sesiones, self._salud, self._no_disponibles = sitios, sesiones, salud, no_disponibles

    def fuentes(self) -> list[FuenteDisponible]:
        return [FuenteDisponible(f.nombre, f.etiqueta, f.sitio_id,
                                 self._sesiones.estado(f.sitio_id) if f.sitio_id else None,
                                 self._salud.desactivada(f.nombre) if self._salud else None)
                for f in self._fuentes.values()]

    def no_disponibles(self) -> tuple[FuenteNoDisponible, ...]:
        return self._no_disponibles

    def reactivar_fuente(self, nombre: str) -> None:
        if nombre not in self._fuentes:
            raise ErrorDeDominio(f"Fuente desconocida: {nombre}")
        if self._salud:
            self._salud.reactivar(nombre)

    def sitios(self) -> list[tuple[SitioConCredenciales, EstadoDeSesion]]:
        return [(s, self._sesiones.estado(s.id)) for s in self._sitios.todos()]

    def consulta_inicial(self) -> ConsultaDeBusqueda:
        return consulta_inicial()

    def busquedas(self, proyecto_id: uuid.UUID) -> list[Busqueda]:
        return self._busquedas.listar(proyecto_id)

    def busqueda(self, proyecto_id: uuid.UUID, busqueda_id: uuid.UUID) -> Busqueda:
        return self._busquedas.obtener(proyecto_id, busqueda_id)

    def candidatos(self, proyecto_id: uuid.UUID, *, estado: EstadoCandidato | None = None,
                   busqueda_id: uuid.UUID | None = None, texto: str | None = None, en_matriz: bool | None = None,
                   desde: int = 0, cuantos: int = 100) -> ListadoDeCandidatos:
        if desde < 0 or not 1 <= cuantos <= 500:
            raise ErrorDeDominio("Página o tamaño fuera de rango")
        lista, total = self._candidatos.listar(proyecto_id, estado=estado, busqueda_id=busqueda_id, texto=texto,
                                               en_matriz=en_matriz, desde=desde, cuantos=cuantos)
        return ListadoDeCandidatos(lista, total, self._candidatos.contadores(proyecto_id))


@dataclass(frozen=True)
class ResultadoDeDecision:
    cambiados: list[Candidato]
    rechazados: dict[uuid.UUID, str]  # id → por qué no se pudo


class DecidirSobreCandidatos:
    """Priorizar, descartar (con motivo) o reactivar, sobre una selección. Cada candidato se valida por separado."""

    def __init__(self, candidatos: RepositorioDeCandidatos) -> None:
        self._candidatos = candidatos

    def ejecutar(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID], accion: str,
                 motivo: str | None = None) -> ResultadoDeDecision:
        if accion not in ("priorizar", "descartar", "reactivar"):
            raise ErrorDeDominio(f"Acción desconocida: {accion}")
        if accion == "descartar" and not (motivo and motivo.strip()):
            raise ErrorDeDominio("Descartar exige motivo")
        if not ids:
            raise ErrorDeDominio("No hay candidatos seleccionados")
        cambiados: list[Candidato] = []
        rechazados: dict[uuid.UUID, str] = {}
        encontrados = {c.id: c for c in self._candidatos.por_ids(proyecto_id, ids)}
        for cid in ids:
            c = encontrados.get(cid)
            if c is None:
                rechazados[cid] = "No existe en este proyecto"
                continue
            try:
                if accion == "priorizar":
                    c.priorizar()
                elif accion == "descartar":
                    c.descartar(motivo or "")
                else:
                    c.reactivar()
            except ErrorDeDominio as e:
                rechazados[cid] = str(e)
                continue
            self._candidatos.guardar(c)
            cambiados.append(c)
        return ResultadoDeDecision(cambiados, rechazados)


@dataclass
class CasosDeDescubrimiento:
    buscar: EjecutarBusqueda
    consultas: ConsultasDeDescubrimiento
    decidir: DecidirSobreCandidatos
    perfiles: GestionarPerfiles
    evaluar: EvaluarCandidatos
    importar: ImportarCandidatos
    analizar: AnalizarTextoCompleto
    # Aviso de que algo cambió (lo conecta `app/composicion.py` con el agente de sincronización).
    al_cambiar: Callable[[uuid.UUID], None] = lambda _pid: None

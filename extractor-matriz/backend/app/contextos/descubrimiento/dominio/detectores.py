"""Detectores de la etapa A (metadatos + título, resumen y palabras clave). Deterministas: sin IA, sin red.

Dado un candidato y una columna del libro de códigos, dicen si el candidato **parece** traer ese dato y con qué frase. Es un
indicio, no un dato (regla de ubicación comprobable): nada de esto entra a la matriz; solo ordena y filtra candidatos.

Las reglas de cada columna vienen de `recursos/detectores_columnas.json` y la clasificación M/R/T/X de
`recursos/detectabilidad_columnas.json`; este módulo no sabe qué columnas existen.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Any

from app.contextos.descubrimiento.dominio.busqueda import plano
from app.contextos.descubrimiento.dominio.candidato import Candidato


class Nivel(StrEnum):
    M = "M"  # metadato de la fuente
    R = "R"  # título, resumen o palabras clave
    T = "T"  # solo el texto completo
    X = "X"  # interna: la asigna el equipo o la deriva el programa


class EstadoCelda(StrEnum):
    METADATO = "METADATO"
    INDICIO = "INDICIO"
    PENDIENTE = "PENDIENTE"  # solo el PDF lo puede decir: NO cuenta como ausente
    AUSENTE = "AUSENTE"  # la fuente no lo trae y debería (solo columnas M)
    NO_APLICA = "NO_APLICA"  # columna interna


@dataclass(frozen=True)
class CeldaPrevia:
    columna: str
    estado: EstadoCelda
    valor: str | None = None
    origen: str = ""
    frase: str | None = None

    @property
    def cubierta(self) -> bool:
        return self.estado in (EstadoCelda.METADATO, EstadoCelda.INDICIO)

    def a_dict(self) -> dict[str, Any]:
        return {"columna": self.columna, "estado": self.estado.value, "valor": self.valor, "origen": self.origen,
                "frase": self.frase}


@dataclass(frozen=True)
class ConfigDeDetectores:
    niveles: dict[str, Nivel]
    grupos: dict[str, str]
    si_falta: dict[str, str]  # columna → «pendiente» (por defecto, una columna M ausente es AUSENTE)
    detectores: dict[str, dict[str, Any]]
    terminos_felicidad: tuple[str, ...] = ()
    terminos_desempeno: tuple[str, ...] = ()
    paises: dict[str, str] = field(default_factory=dict)


def _patron(texto: str, *, escapar: bool) -> re.Pattern[str]:
    """Palabra completa (con plural opcional). Un `*` al final deja la palabra abierta: «universit*»."""
    p = plano(texto)
    abierto = p.endswith("*")
    p = p.rstrip("*")
    cuerpo = re.escape(p) if escapar else p
    return re.compile(r"(?<!\w)" + cuerpo + (r"\w*" if abierto else r"(?:s|es)?(?!\w)"))


_ORACIONES = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9¿¡\"'(])")
_NUM_MUESTRA = (
    re.compile(r"(?<![a-z])n\s*=\s*(\d[\d,]*)"),
    re.compile(r"(?:sample|total|data|respondents|participants|sample size)\s+(?:of|was|comprised|consisted of|included)"
               r"\s+(?:n\s*=\s*)?(\d[\d,]*)"),
    re.compile(r"(\d[\d,]*)\s+(?:[a-z\-]+\s+){0,2}(?:employees|workers|participants|respondents|nurses|teachers|"
               r"managers|students|individuals|people|professionals|staff|subjects|observations|empleados|"
               r"trabajadores|docentes|participantes|encuestados)"),
)
_FIABILIDAD = re.compile(r"cronbach|alpha|\bα|omega|\bω|reliabilit|fiabilidad|confiabilidad")
_VALOR_ALFA = re.compile(r"(?:α|alpha|omega|ω)\D{0,60}?(0?[\.,]\d{2,3})")


def oraciones(texto: str) -> list[str]:
    return [o.strip() for o in _ORACIONES.split(texto.strip()) if o.strip()]


def _corta(frase: str, n: int = 320) -> str:
    return frase if len(frase) <= n else frase[: n - 1].rstrip() + "…"


def _a_muestra(token: str) -> int | None:
    limpio = token.replace(",", "")
    if not limpio.isdigit():
        return None
    n = int(limpio)
    return n if 10 <= n <= 1_000_000 else None


def formatear_cita(apellidos: list[str], anio: int | None) -> str | None:
    """Regla del responsable (plan, sección 11): 1 → «A (año)»; 2 → «A y B (año)»; 3 o más → «A et al. (año)»."""
    nombres = [a for a in apellidos if a]
    if not nombres or anio is None:
        return None
    if len(nombres) == 1:
        return f"{nombres[0]} ({anio})"
    if len(nombres) == 2:
        return f"{nombres[0]} y {nombres[1]} ({anio})"
    return f"{nombres[0]} et al. ({anio})"


@lru_cache(maxsize=4_000)
def _segmentos_de(titulo: str, resumen: str, palabras_clave: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Título, cada oración del resumen y las palabras clave, con su procedencia. Se guarda: se pide una vez por columna."""
    segs = [("título", titulo)]
    segs += [("resumen", o) for o in oraciones(resumen)] if resumen else []
    if palabras_clave:
        segs.append(("palabras clave", "; ".join(palabras_clave)))
    return tuple(segs)


# ---- etapa B: texto completo --------------------------------------------------------------------------------------------
TEXTO_SUFICIENTE = 4_000  # menos caracteres que esto: probablemente un PDF escaneado; no se puede afirmar que algo falte
MAX_PAGINAS = 80
_ENCABEZADO_REFERENCIAS = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(?:references|bibliography|referencias|bibliograf[ií]a|literature cited)\s*$")
_SOLO_FUTURO = re.compile(
    r"future (?:research|studies|work)|further (?:research|studies)|should be (?:replicated|examined|explored)|"
    r"limitations? of (?:this|the) (?:study|research)|investigaciones futuras|estudios futuros")


@dataclass(frozen=True)
class ResultadoDeTexto:
    """Lo que dio leer el texto completo de un PDF: solo los indicios hallados y qué columnas se intentaron."""

    celdas: dict[str, CeldaPrevia]
    intentadas: tuple[str, ...]
    paginas: int
    caracteres: int

    @property
    def suficiente(self) -> bool:
        return self.caracteres >= TEXTO_SUFICIENTE


def _sin_referencias(paginas: list[str]) -> list[str]:
    """Corta desde el encabezado «References» (si está en la segunda mitad del documento): las citas dan falsos indicios."""
    for i, texto in enumerate(paginas):
        m = _ENCABEZADO_REFERENCIAS.search(texto)
        if m and i >= len(paginas) // 2:
            return [*paginas[:i], texto[: m.start()]]
    return paginas


_SECCIONES: dict[str, re.Pattern[str]] = {
    "método": re.compile(
        r"^(?:(?:\d+|[ivxl]+)(?:\.\d+)*[.)]?\s*)?(?:materials? and methods?|methods?|methodology|research design|data and methods?|"
        r"method and materials?|participants?(?: and procedures?)?|procedures?|sample(?: and procedures?)?|measures?|"
        r"instruments?|metodo|metodologia|muestra|participantes|instrumentos?)$"),
    "resultados": re.compile(
        r"^(?:(?:\d+|[ivxl]+)(?:\.\d+)*[.)]?\s*)?(?:results?(?: and discussion)?|findings(?: and results)?|analysis and results|resultados|"
        r"hypothes[ei]s testing)$"),
    "discusión": re.compile(
        r"^(?:(?:\d+|[ivxl]+)(?:\.\d+)*[.)]?\s*)?(?:discussion|general discussion|conclusions?|limitations?|implications?|"
        r"discusion|conclusiones)$"),
    "introducción": re.compile(
        r"^(?:(?:\d+|[ivxl]+)(?:\.\d+)*[.)]?\s*)?(?:introduction|literature review|theoretical (?:background|framework)|"
        r"(?:hypothesis|hypotheses) development|background|theory and hypotheses|introduccion|marco teorico)$"),
}


def _seccion_de(linea: str) -> str | None:
    t = plano(linea).strip(" .:")
    if not t or len(t) > 60:
        return None
    return next((nombre for nombre, rx in _SECCIONES.items() if rx.match(t)), None)


def segmentos_de_texto(c: Candidato, paginas: list[str]) -> list[tuple[str, str]]:
    """Título, resumen y palabras clave primero (como en la etapa A); luego cada oración del cuerpo con su página y su
    sección («p. 5 · método»). Las secciones se reconocen por sus encabezados; sin ellos, «texto»."""
    segs = list(_segmentos_de(c.titulo, c.resumen, tuple(c.palabras_clave)))
    seccion = "texto"
    for n, texto in enumerate(_sin_referencias(paginas[:MAX_PAGINAS]), 1):
        tramos: list[tuple[str, list[str]]] = [(seccion, [])]
        for linea in texto.split("\n"):
            nueva = _seccion_de(linea)
            if nueva is not None:
                seccion = nueva
                tramos.append((seccion, []))
            else:
                tramos[-1][1].append(linea)
        for sec, lineas in tramos:
            limpio = re.sub(r"\s+", " ", re.sub(r"-\n(?=[a-z])", "", "\n".join(lineas)))
            for o in oraciones(limpio):
                if len(o.split()) >= 4 and len(o) <= 700 and not _SOLO_FUTURO.search(plano(o)):
                    segs.append((f"p. {n} · {sec}", o))
    return segs


def _en_secciones(origen: str, permitidas: list[str]) -> bool:
    """El título, el resumen y las palabras clave valen siempre; el cuerpo, solo en las secciones indicadas."""
    if not origen.startswith("p. "):
        return True
    return origen.rsplit(" · ", 1)[-1] in permitidas


class MotorDeDetectores:
    def __init__(self, cfg: ConfigDeDetectores) -> None:
        self._cfg = cfg
        self._compilados: dict[tuple[str, str], list[tuple[str, re.Pattern[str]]]] = {}

    # ---- consulta de la clasificación ---------------------------------------------------------------------------
    def nivel(self, clave: str) -> Nivel:
        return self._cfg.niveles.get(clave, Nivel.T)  # una columna nueva del libro se trata como «solo PDF»

    def grupo(self, clave: str) -> str:
        return self._cfg.grupos.get(clave, "Otras")

    def tiene_detector(self, clave: str) -> bool:
        return clave in self._cfg.detectores or self.nivel(clave) == Nivel.M

    # ---- evaluación ---------------------------------------------------------------------------------------------
    def evaluar(self, clave: str, c: Candidato) -> CeldaPrevia:
        nivel = self.nivel(clave)
        if nivel == Nivel.X:
            return CeldaPrevia(clave, EstadoCelda.NO_APLICA, origen="la asigna el equipo o la deriva el programa")
        if nivel == Nivel.M:
            return self._metadato(clave, c)
        cfg = self._cfg.detectores.get(clave)
        if cfg is None:
            return CeldaPrevia(clave, EstadoCelda.PENDIENTE, origen="solo el texto completo")
        if cfg.get("solo_texto_completo"):
            return CeldaPrevia(clave, EstadoCelda.PENDIENTE, origen="solo el texto completo")
        encontrado = self._detectar(clave, cfg, self._segmentos(c))
        return encontrado or CeldaPrevia(clave, EstadoCelda.PENDIENTE,
                                         origen="sin indicio en el resumen" if nivel == Nivel.R else "solo el texto completo")

    # ---- metadatos ----------------------------------------------------------------------------------------------
    def _metadato(self, clave: str, c: Candidato) -> CeldaPrevia:
        origen = "metadato (" + ", ".join(c.fuentes) + ")"
        valor: str | None = None
        if clave == "Title":
            valor = c.titulo
        elif clave == "Año":
            valor = str(c.anio) if c.anio is not None else None
        elif clave == "Author":
            valor = "; ".join(a.nombre for a in c.autores) or None
        elif clave == "Cita":
            valor = formatear_cita([a.apellido for a in c.autores], c.anio)
        elif clave == "Pais":
            valor = self._pais(c)
            origen = "afiliaciones de los autores (ADR 0010)"
        if valor:
            return CeldaPrevia(clave, EstadoCelda.METADATO, valor, origen)
        pendiente = self._cfg.si_falta.get(clave) == "pendiente"
        return CeldaPrevia(clave, EstadoCelda.PENDIENTE if pendiente else EstadoCelda.AUSENTE,
                           origen="la fuente no lo trae")

    def _pais(self, c: Candidato) -> str | None:
        """País más frecuente entre las afiliaciones de los autores; si empatan, el del primer autor."""
        cuenta: Counter[str] = Counter()
        for a in c.autores:
            cuenta.update(set(a.paises))
        if not cuenta:
            return None
        mayor = max(cuenta.values())
        empatados = {p for p, n in cuenta.items() if n == mayor}
        elegido = next((p for a in c.autores for p in a.paises if p in empatados), next(iter(empatados)))
        return self._cfg.paises.get(elegido, elegido)

    # ---- segmentos de texto con su procedencia ------------------------------------------------------------------
    @staticmethod
    def _segmentos(c: Candidato) -> list[tuple[str, str]]:
        return list(_segmentos_de(c.titulo, c.resumen, tuple(c.palabras_clave)))

    def _patrones(self, clave: str, tipo: str, nombres: list[str], *, escapar: bool) -> list[tuple[str, re.Pattern[str]]]:
        llave = (clave, tipo)
        if llave not in self._compilados:
            self._compilados[llave] = [(n, _patron(n, escapar=escapar)) for n in nombres]
        return self._compilados[llave]

    # ---- etapa B -----------------------------------------------------------------------------------------------
    def analizar_texto(self, c: Candidato, paginas: list[str]) -> ResultadoDeTexto:
        """Corre todos los detectores sobre el texto completo. Devuelve solo lo hallado; lo demás lo decide la evaluación."""
        segs = segmentos_de_texto(c, paginas)
        celdas: dict[str, CeldaPrevia] = {}
        intentadas: list[str] = []
        for clave, cfg in self._cfg.detectores.items():
            if self.nivel(clave) in (Nivel.M, Nivel.X):
                continue
            intentadas.append(clave)
            hallada = self._detectar(clave, cfg, segs)
            if hallada is not None:
                celdas[clave] = hallada
        return ResultadoDeTexto(celdas, tuple(intentadas), len(paginas), sum(len(p) for p in paginas))

    # ---- estrategias --------------------------------------------------------------------------------------------
    def _terminos(self, construccion: str | None) -> tuple[str, ...]:
        if construccion == "felicidad":
            return self._cfg.terminos_felicidad
        if construccion == "desempeno":
            return self._cfg.terminos_desempeno
        return ()

    def _detectar(self, clave: str, cfg: dict[str, Any], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        tipo = cfg["tipo"]
        if "secciones" in cfg:  # p. ej. el sector o el diseño se leen en el método, no en lo que se cita en la discusión
            segs = [(o, t) for o, t in segs if _en_secciones(o, cfg["secciones"])]
        if tipo == "numero_muestra":
            return self._muestra(clave, segs)
        if tipo == "regex":
            return self._regex(clave, cfg, segs)
        if tipo == "fiabilidad":
            return self._fiabilidad(clave, cfg["construccion"], segs)
        if tipo == "lista":
            return self._lista(clave, cfg, segs)
        if tipo == "vocabulario":
            return self._vocabulario(clave, cfg["valores"], segs)
        if tipo == "oracion":
            return self._oracion(clave, cfg, segs)
        if tipo == "fechas":
            return self._fechas(clave, cfg, segs)
        return None

    @staticmethod
    def _celda(clave: str, valor: str, origen: str, frase: str) -> CeldaPrevia:
        return CeldaPrevia(clave, EstadoCelda.INDICIO, valor, origen, _corta(frase))

    def _muestra(self, clave: str, segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        for origen, texto in segs:
            p = plano(texto)
            for rx in _NUM_MUESTRA:
                for m in rx.finditer(p):
                    n = _a_muestra(m.group(1))
                    if n is not None:
                        return self._celda(clave, str(n), origen, texto)
        return None

    def _regex(self, clave: str, cfg: dict[str, Any], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        compilados = [re.compile(p, re.I) for p in cfg["patrones"]]
        terminos = self._terminos(cfg.get("construccion"))
        grupo = int(cfg.get("grupo", 0))
        for origen, texto in segs:
            p = plano(texto)
            if terminos and not any(t in p for t in terminos):
                continue
            # «ambas»: la oración debe nombrar la felicidad Y el desempeño (la correlación que importa es la que los une)
            if cfg.get("ambas") and not (any(t in p for t in self._cfg.terminos_felicidad)
                                         and any(t in p for t in self._cfg.terminos_desempeno)):
                continue
            for rx in compilados:
                m = rx.search(p)
                if m:
                    return self._celda(clave, re.sub(r"\s+", " ", m.group(grupo)).strip(), origen, texto)
        return None

    def _fiabilidad(self, clave: str, construccion: str, segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        terminos = self._terminos(construccion)
        for origen, texto in segs:
            p = plano(texto)
            if _FIABILIDAD.search(p) and any(t in p for t in terminos):
                m = _VALOR_ALFA.search(p)
                return self._celda(clave, m.group(1).replace(",", ".") if m else "se reporta", origen, texto)
        return None

    def _lista(self, clave: str, cfg: dict[str, Any], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        pats = self._patrones(clave, "lista", cfg["nombres"], escapar=True)
        # Con «omitir_primeros» (aunque sea 0) la columna guarda UN elemento: la 1.ª, 2.ª o 3.ª teoría del texto.
        un_solo = "omitir_primeros" in cfg
        omitir = int(cfg.get("omitir_primeros", 0))
        hallados: list[tuple[int, int, str]] = []
        frase: dict[str, tuple[str, str]] = {}
        for i, (origen, texto) in enumerate(segs):
            p = plano(texto)
            for nombre, rx in pats:
                m = rx.search(p)
                if m and nombre not in frase:
                    hallados.append((i, m.start(), nombre))
                    frase[nombre] = (origen, texto)
        # en el orden en que aparecen; los sinónimos («broaden-and-build» y «broaden and build») cuentan una vez
        unicos: list[str] = []
        for _i, _pos, n in sorted(hallados):
            if not any(plano(n).replace("-", " ") == plano(u).replace("-", " ") for u in unicos):
                unicos.append(n)
        elegidos = unicos[omitir: omitir + 1] if un_solo else unicos[:4]
        if not elegidos:
            return None
        origen, texto = frase[elegidos[0]]
        return self._celda(clave, ", ".join(elegidos), origen, texto)

    def _vocabulario(self, clave: str, valores: dict[str, list[str]], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        for valor, palabras in valores.items():
            for _nombre, rx in self._patrones(f"{clave}|{valor}", "vocab", palabras, escapar=False):
                for origen, texto in segs:
                    if rx.search(plano(texto)):
                        return self._celda(clave, valor, origen, texto)
        return None

    def _oracion(self, clave: str, cfg: dict[str, Any], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        pats = self._patrones(clave, "oracion", cfg["pistas"], escapar=True)
        terminos = self._terminos(cfg.get("construccion"))
        # Ni el título ni las palabras clave son oraciones de objetivo, conclusión ni método.
        candidatas = [(o, t) for o, t in segs
                      if o not in ("título", "palabras clave") and any(rx.search(plano(t)) for _n, rx in pats)
                      and (not terminos or any(x in plano(t) for x in terminos))]
        if not candidatas:
            return None
        origen, texto = candidatas[0] if cfg.get("posicion") != "ultima" else candidatas[-1]
        return self._celda(clave, _corta(texto, 300), origen, texto)

    def _fechas(self, clave: str, cfg: dict[str, Any], segs: list[tuple[str, str]]) -> CeldaPrevia | None:
        """Fechas de recolección: «collected between March 2011 and June 2012» → inicio «march 2011», cierre «june 2012»."""
        meses = cfg["meses"]
        fecha = rf"(?:(?:{meses})\s+(?:of\s+)?)?(?:19|20)\d{{2}}"
        cue = re.compile(r"collect|survey was|surveys were|questionnaires? (?:was|were)|administered|fieldwork|"
                         r"recolecci|trabajo de campo|se aplic", re.I)
        rx = re.compile(fecha, re.I)
        for origen, texto in segs:
            if origen in ("título", "palabras clave"):
                continue
            p = plano(texto)
            if not cue.search(p):
                continue
            fechas = [m.group(0).strip() for m in rx.finditer(p)]
            if len(fechas) > int(cfg["cual"]):
                return self._celda(clave, fechas[int(cfg["cual"])], origen, texto)
        return None

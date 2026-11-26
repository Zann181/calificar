"""Cliente HTTP cortés: la única puerta de salida de Descubrimiento hacia internet (ADR 0011).

Qué garantiza, para cualquier fuente:
- una petición a la vez por servidor y una pausa mínima entre ellas (más larga en los sitios con credenciales);
- reintentos con espera creciente que respetan `Retry-After` (con tope);
- un interruptor de circuito por servidor: tras varios fallos seguidos deja de insistir un rato y lo dice;
- caché en disco con vigencia, para no repetir lo que ya se pidió;
- un presupuesto de bytes por ventana para los sitios con credenciales, siempre por debajo del límite que publican;
- para comprobar un PDF pide solo sus primeros bytes, respeta `robots.txt` y deja de insistir en quien lo rechaza;
- registro de errores sin secretos: solo servidor y ruta, nunca parámetros (llaves, correo) ni cookies.

No hace nada para esquivar defensas de los sitios: sin rotación de IP, sin suplantar el navegador, sin resolver CAPTCHA.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.contextos.descubrimiento.adaptadores.robots import ReglasDeRobots
from app.contextos.descubrimiento.dominio.errores import ErrorDeFuente
from app.contextos.descubrimiento.dominio.sitios import SitioConCredenciales

log = logging.getLogger("descubrimiento")

NOMBRE_DEL_CLIENTE = "ExtractorMatriz/0.1"
PARAMETROS_SECRETOS = frozenset({"api_key", "mailto", "key", "token", "email"})


@dataclass(frozen=True)
class Descarga:
    datos: bytes
    tipo: str  # content-type sin parámetros, en minúsculas
    url_final: str  # tras las redirecciones


class ClienteCortes:
    def __init__(self, *, contacto: str = "", sitios: list[SitioConCredenciales] | None = None,
                 transporte: httpx.BaseTransport | None = None, cache_dir: Path | None = None,
                 cache_vigencia_s: float = 24 * 3600, pausa_min_s: float = 1.0, max_reintentos: int = 3,
                 fallos_para_abrir: int = 3, abierto_s: float = 300.0, espera_max_s: float = 60.0,
                 tiempo_max_s: float = 30.0, tiempo_comprobacion_s: float = 10.0, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], None] = time.sleep, ahora_epoch: Callable[[], float] = time.time) -> None:
        self._contacto = contacto.strip()
        self._sitios = list(sitios or [])
        self._http = httpx.Client(transport=transporte, timeout=tiempo_max_s, follow_redirects=True)
        self._cache_dir, self._cache_vigencia_s = cache_dir, cache_vigencia_s
        self._pausa_min_s, self._max_reintentos = pausa_min_s, max_reintentos
        self._fallos_para_abrir, self._abierto_s, self._espera_max_s = fallos_para_abrir, abierto_s, espera_max_s
        self._reloj, self._dormir, self._ahora = reloj, dormir, ahora_epoch
        self._cerrojos: dict[str, threading.Lock] = {}
        self._ultimo: dict[str, float] = {}
        self._fallos: dict[str, int] = {}
        self._abierto_hasta: dict[str, float] = {}
        self._consumo: dict[str, deque[tuple[float, int]]] = {}
        self._global = threading.Lock()
        self._robots: dict[str, tuple[float, ReglasDeRobots]] = {}
        self._tiempo_comprobacion_s = tiempo_comprobacion_s
        # Aparte del circuito de las API: que un sitio niegue sus PDF no debe apagar su buscador.
        self._rechazos: dict[str, int] = {}
        self._rechaza_hasta: dict[str, float] = {}

    # ---- utilidades ------------------------------------------------------------------------------------------
    def _sitio_de(self, host: str) -> SitioConCredenciales | None:
        return next((s for s in self._sitios if s.es_de_este_sitio(host)), None)

    def _cerrojo(self, host: str) -> threading.Lock:
        with self._global:
            return self._cerrojos.setdefault(host, threading.Lock())

    def _cabeceras(self, sitio: SitioConCredenciales | None, accept: str = "application/json") -> dict[str, str]:
        # El correo de contacto solo viaja a fuentes abiertas que lo piden, nunca a un sitio con credenciales.
        ua = NOMBRE_DEL_CLIENTE if (sitio is not None or not self._contacto) else f"{NOMBRE_DEL_CLIENTE} (mailto:{self._contacto})"
        return {"User-Agent": ua, "Accept": accept}

    @staticmethod
    def _llave_de_cache(url: str, params: Mapping[str, Any]) -> str:
        visibles = sorted((k, str(v)) for k, v in params.items() if k not in PARAMETROS_SECRETOS and v is not None)
        return hashlib.sha256(json.dumps([url, visibles], ensure_ascii=False).encode()).hexdigest()

    def _leer_cache(self, llave: str) -> Any | None:
        if self._cache_dir is None:
            return None
        ruta = self._cache_dir / llave[:2] / f"{llave}.json"
        try:
            contenido = json.loads(ruta.read_text(encoding="utf-8"))
            if self._ahora() - float(contenido["t"]) <= self._cache_vigencia_s:
                return contenido["datos"]
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _guardar_cache(self, llave: str, datos: Any) -> None:
        if self._cache_dir is None:
            return
        try:
            ruta = self._cache_dir / llave[:2] / f"{llave}.json"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps({"t": self._ahora(), "datos": datos}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("No se pudo escribir la caché de búsqueda en disco")  # la caché es opcional

    def _presupuesto_agotado(self, sitio: SitioConCredenciales) -> float | None:
        """Segundos hasta que el sitio vuelva a tener presupuesto, o None si todavía queda."""
        ventana = self._consumo.setdefault(sitio.id, deque())
        ahora = self._reloj()
        while ventana and ahora - ventana[0][0] > sitio.limite.ventana_s:
            ventana.popleft()
        if sum(b for _t, b in ventana) >= sitio.limite.bytes_por_ventana:
            return max(0.0, ventana[0][0] + sitio.limite.ventana_s - ahora)
        return None

    def _contar(self, sitio: SitioConCredenciales, n: int) -> None:
        self._consumo.setdefault(sitio.id, deque()).append((self._reloj(), n))

    def bytes_en_ventana(self, sitio_id: str) -> int:
        sitio = next((s for s in self._sitios if s.id == sitio_id), None)
        if sitio is None:
            return 0
        self._presupuesto_agotado(sitio)  # poda lo vencido
        return sum(b for _t, b in self._consumo.get(sitio_id, ()))

    def _fallo(self, host: str) -> None:
        self._fallos[host] = self._fallos.get(host, 0) + 1
        if self._fallos[host] >= self._fallos_para_abrir:
            self._abierto_hasta[host] = self._reloj() + self._abierto_s

    # ---- la petición -----------------------------------------------------------------------------------------
    def _reglas_de(self, url: str) -> ReglasDeRobots | str:
        """Las reglas de `robots.txt` del sitio (RFC 9309), o por qué no se pudieron leer."""
        partes = urlsplit(url)
        host = partes.netloc.lower()
        with self._cerrojo(host):
            guardado = self._robots.get(host)
            if guardado is not None and self._reloj() - guardado[0] <= 24 * 3600:
                return guardado[1]
            self._esperar_turno(host, self._pausa_min_s)
            try:
                r = self._http.get(f"{partes.scheme}://{host}/robots.txt", headers=self._cabeceras(None, "text/plain"),
                                   timeout=self._tiempo_comprobacion_s)
            except httpx.HTTPError as e:
                return f"no se pudo leer robots.txt de {host} ({type(e).__name__}): se detiene por precaución"
            self._ultimo[host] = self._reloj()
            if r.status_code == 200:
                reglas = ReglasDeRobots(r.text)
            elif 400 <= r.status_code < 500:  # sin robots.txt (404…): sin restricciones, según el estándar
                reglas = ReglasDeRobots("")
            else:
                return f"robots.txt de {host} no está disponible (HTTP {r.status_code}): se detiene"
            self._robots[host] = (self._reloj(), reglas)
            return reglas

    def _exigir_robots(self, fuente: str, url: str) -> None:
        """Lo que el sitio prohíbe, no se lee. Sin poder leer sus reglas, se detiene por precaución."""
        partes = urlsplit(url)
        host = partes.netloc.lower()
        reglas = self._reglas_de(url)
        if isinstance(reglas, str):
            log.error("%s: %s", fuente, reglas)
            raise ErrorDeFuente(fuente, reglas)
        if not reglas.permite(url):
            log.error("%s: el robots.txt de %s no permite leer %s: no se lee", fuente, host, partes.path)
            raise ErrorDeFuente(fuente, f"el robots.txt de {host} no permite leer esa ruta: no se lee")

    def _esperar_turno(self, host: str, pausa: float) -> None:
        por_esperar = self._ultimo.get(host, -1e18) + pausa - self._reloj()
        if por_esperar > 0:
            self._dormir(por_esperar)

    def _permitido(self, url: str) -> bool:
        reglas = self._reglas_de(url)
        return not isinstance(reglas, str) and reglas.permite(url)

    def primeros_bytes(self, url: str, n: int = 8) -> bytes | None:
        """El comienzo de lo que entrega una dirección, sin bajar el resto. None si no se debe o no se puede.

        Nunca con sitios de credenciales. Un fallo aquí no es un error de la búsqueda: ese resultado, sencillamente, no
        entrega un PDF. Tras varios rechazos seguidos de un servidor (401, 403, 429) se le deja de preguntar un rato.
        """
        partes = urlsplit(url)
        host = partes.netloc.lower()
        if partes.scheme not in ("http", "https") or not host or self._sitio_de(host) is not None:
            return None
        if not self._permitido(url):
            return None
        cabeceras = {**self._cabeceras(None, "application/pdf"), "Range": f"bytes=0-{n - 1}"}
        with self._cerrojo(host):
            if self._rechaza_hasta.get(host, 0) > self._reloj():  # se mira con el turno en la mano
                return None
            self._esperar_turno(host, self._pausa_min_s)
            try:
                with self._http.stream("GET", url, headers=cabeceras, timeout=self._tiempo_comprobacion_s) as r:
                    if r.status_code in (401, 403, 429):
                        self._rechazos[host] = self._rechazos.get(host, 0) + 1
                        if self._rechazos[host] >= self._fallos_para_abrir:
                            self._rechaza_hasta[host] = self._reloj() + self._abierto_s
                            log.info("%s no entrega sus PDF a programas (HTTP %d): se deja de preguntar un rato", host,
                                     r.status_code)
                        return None
                    if r.status_code not in (200, 206):
                        return None
                    self._rechazos[host] = 0
                    final = str(r.url)
                    inicio = next(r.iter_bytes(n), b"")[:n]
            except (httpx.HTTPError, httpx.InvalidURL):
                return None
            finally:
                self._ultimo[host] = self._reloj()
        if urlsplit(final).netloc.lower() != host and not self._permitido(final):
            return None  # redirigió a un sitio que no deja leer esa ruta
        return inicio

    def get_json(self, fuente: str, url: str, params: Mapping[str, Any] | None = None, *, robots: bool = False,
                 accept: str = "application/json") -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if robots:
            self._exigir_robots(fuente, url)
        llave = self._llave_de_cache(url, params)
        if (en_cache := self._leer_cache(llave)) is not None:
            return en_cache
        r = self._solicitar(fuente, url, params, accept)
        partes = urlsplit(url)
        try:
            datos = r.json()
        except ValueError as e:
            self._fallo(partes.netloc.lower())
            log.error("%s: respuesta de %s%s no es JSON; el sitio pudo haber cambiado", fuente, partes.netloc.lower(),
                      partes.path)
            raise ErrorDeFuente(fuente, "la respuesta no es JSON (el sitio cambió o pidió verificación)",
                                estado_http=200) from e
        self._guardar_cache(llave, datos)
        return datos

    def get_bytes(self, fuente: str, url: str, *, max_bytes: int = 60_000_000) -> Descarga:
        """Baja un archivo (un PDF) con el mismo ritmo, reintentos, circuito y presupuesto que el JSON. Sin caché."""
        r = self._solicitar(fuente, url, {}, "application/pdf,text/html;q=0.8,*/*;q=0.5")
        if len(r.content) > max_bytes:
            raise ErrorDeFuente(fuente, f"el archivo pesa más de {max_bytes // 1_000_000} MB: no se descarga")
        return Descarga(r.content, r.headers.get("content-type", "").split(";")[0].strip().lower(), str(r.url))

    def _solicitar(self, fuente: str, url: str, params: Mapping[str, Any], accept: str) -> httpx.Response:
        """La petición cortés: circuito, presupuesto, ritmo, reintentos. Devuelve la respuesta 200."""
        partes = urlsplit(url)
        host, ruta = partes.netloc.lower(), partes.path
        sitio = self._sitio_de(host)

        if self._abierto_hasta.get(host, 0) > self._reloj():
            falta = int(self._abierto_hasta[host] - self._reloj())
            raise ErrorDeFuente(fuente, f"circuito abierto en {host}: demasiados fallos seguidos, reintente en {falta} s")

        ultimo_error = "sin respuesta"
        estado_http: int | None = None
        with self._cerrojo(host):
            for intento in range(self._max_reintentos + 1):
                if sitio is not None and (espera := self._presupuesto_agotado(sitio)) is not None:
                    log.error("%s: tope de descarga alcanzado (%d MB en %d min); se detiene para no bloquear la cuenta",
                              sitio.nombre, sitio.limite.bytes_por_ventana // 1_000_000, sitio.limite.ventana_s // 60)
                    raise ErrorDeFuente(fuente, f"tope de descarga alcanzado en {sitio.nombre}; vuelva a intentar en "
                                                f"{int(espera) + 1} s")
                pausa = sitio.limite.pausa_min_s if sitio is not None else self._pausa_min_s
                por_esperar = self._ultimo.get(host, -1e18) + pausa - self._reloj()
                if por_esperar > 0:
                    self._dormir(por_esperar)
                espera_reintento: float | None = None
                try:
                    r = self._http.get(url, params=dict(params), headers=self._cabeceras(sitio, accept))
                except httpx.TransportError as e:
                    self._ultimo[host] = self._reloj()
                    ultimo_error, estado_http = f"sin conexión ({type(e).__name__})", None
                    espera_reintento = float(2 ** intento)
                else:
                    self._ultimo[host] = self._reloj()
                    if sitio is not None:
                        self._contar(sitio, len(r.content))
                    estado_http = r.status_code
                    if r.status_code == 200:
                        self._fallos[host] = 0
                        return r
                    if r.status_code == 429 or r.status_code >= 500:
                        ultimo_error = ("límite de uso de la API (HTTP 429)" if r.status_code == 429
                                        else f"el servidor falló (HTTP {r.status_code})")
                        try:
                            espera_reintento = min(float(r.headers.get("Retry-After", "")), self._espera_max_s)
                        except ValueError:
                            espera_reintento = float(2 ** intento)
                    else:
                        self._fallo(host)
                        causa = {401: "no autorizado (HTTP 401)", 403: "acceso denegado (HTTP 403)",
                                 404: "no encontrado (HTTP 404)"}.get(r.status_code, f"HTTP {r.status_code}")
                        log.error("%s: %s en %s%s", fuente, causa, host, ruta)
                        raise ErrorDeFuente(fuente, causa, estado_http=r.status_code)
                if intento < self._max_reintentos and espera_reintento is not None:
                    log.warning("%s: %s en %s%s; reintento %d de %d en %.0f s", fuente, ultimo_error, host, ruta,
                                intento + 1, self._max_reintentos, min(espera_reintento, self._espera_max_s))
                    self._dormir(min(espera_reintento, self._espera_max_s))
        self._fallo(host)
        log.error("%s: %s en %s%s tras %d intentos", fuente, ultimo_error, host, ruta, self._max_reintentos + 1)
        raise ErrorDeFuente(fuente, ultimo_error, estado_http=estado_http)

    def cerrar(self) -> None:
        self._http.close()

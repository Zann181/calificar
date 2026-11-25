"""Cliente HTTP de la nube (lado del agente local) y almacén del token (ADR 0009, secciones 7 y 8)."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from app.compartido.sobre import ESQUEMA, Sobre
from app.contextos.sincronizacion.dominio.plan import ErrorDeSincronizacion, Manifiesto
from app.contextos.sincronizacion.puertos import Destino, DestinoRemoto, ResultadoLote

log = logging.getLogger("sincronizacion")
LOCALES = {"localhost", "127.0.0.1", "::1"}


def validar_url(url: str) -> str:
    """Solo HTTPS (salvo localhost): el token y los PDF no viajan en claro."""
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ErrorDeSincronizacion("La URL de la nube no es válida: debe verse como https://su-nube.onrender.com")
    if u.scheme == "http" and u.hostname not in LOCALES:
        raise ErrorDeSincronizacion("La URL de la nube debe empezar por https:// (solo localhost admite http://)")
    return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}"


class ClienteHttp:
    """Implementa DestinoRemoto. Acepta un `httpx.Client` ya armado (las pruebas pasan el TestClient de la nube)."""

    def __init__(self, url: str, token: str, instalacion: str, *, cliente: httpx.Client | None = None,
                 tiempo: float = 120.0) -> None:
        self._base = validar_url(url)
        self._cabeceras = {"Authorization": f"Bearer {token}", "X-Instalacion": instalacion}
        # Una nube de Render dormida tarda ~1 min en despertar: el tiempo de espera es holgado.
        self._http = cliente or httpx.Client(timeout=tiempo)

    def _pedir(self, metodo: str, ruta: str, **kw: Any) -> httpx.Response:
        cabeceras = {**self._cabeceras, **kw.pop("headers", {})}
        try:
            r = self._http.request(metodo, f"{self._base}/api/v1/sync{ruta}", headers=cabeceras, **kw)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise ErrorDeSincronizacion(f"No se pudo hablar con la nube ({type(e).__name__}): {e}",
                                        reintentable=True) from e
        if r.is_success:
            return r
        detalle = _detalle(r)
        if r.status_code == 401:
            raise ErrorDeSincronizacion("La nube rechazó el token de sincronización", codigo=401)
        if r.status_code == 409:
            raise ErrorDeSincronizacion(detalle, codigo=409)
        if r.status_code == 426:
            raise ErrorDeSincronizacion(f"La nube es más antigua que este equipo: {detalle}", codigo=426)
        if r.status_code in (502, 503, 504, 429):
            raise ErrorDeSincronizacion(f"La nube no está disponible ({r.status_code}): {detalle}",
                                        codigo=r.status_code, reintentable=True)
        raise ErrorDeSincronizacion(f"La nube respondió {r.status_code}: {detalle}", codigo=r.status_code)

    def salud(self) -> dict[str, Any]:
        resultado: dict[str, Any] = self._pedir("GET", "/salud").json()
        return resultado

    def manifiesto(self, proyecto_id: uuid.UUID) -> Manifiesto:
        d = self._pedir("GET", "/manifiesto", params={"proyecto": str(proyecto_id)}).json()
        return Manifiesto(revision=d["revision"], items=d["items"], archivos=d["archivos"])

    def subir_archivo(self, clave: str, sha256: str, datos: bytes) -> None:
        self._pedir("PUT", "/archivos", params={"clave": clave}, content=datos,
                    headers={"X-Sha256": sha256, "Content-Type": "application/octet-stream"})

    def enviar_lote(self, sobres: list[Sobre], clave_idempotencia: str, *, tomar_control: bool) -> ResultadoLote:
        cuerpo = {"esquema": ESQUEMA, "sobres": [s.a_json() for s in sobres]}
        cab = {"Idempotency-Key": clave_idempotencia}
        if tomar_control:
            cab["X-Tomar-Control"] = "1"
        d = self._pedir("PUT", "/lote", json=cuerpo, headers=cab).json()
        return ResultadoLote(revision=d["revision"], aplicados=d["aplicados"], iguales=d["iguales"])


def _detalle(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail", r.text)
        return d if isinstance(d, str) else str(d)
    except Exception:
        return r.text[:300] or r.reason_phrase


def fabrica_http(destino: Destino, token: str) -> DestinoRemoto:
    return ClienteHttp(destino.url, token, destino.instalacion_id)


class CredencialesEnMemoria:
    """Para pruebas, y de respaldo cuando el equipo no tiene Administrador de credenciales (el token no sobrevive)."""

    def __init__(self) -> None:
        self._tokens: dict[uuid.UUID, str] = {}

    def token(self, proyecto_id: uuid.UUID) -> str | None:
        return self._tokens.get(proyecto_id)

    def guardar(self, proyecto_id: uuid.UUID, token: str) -> None:
        self._tokens[proyecto_id] = token

    def borrar(self, proyecto_id: uuid.UUID) -> None:
        self._tokens.pop(proyecto_id, None)


class CredencialesKeyring:
    """Administrador de credenciales de Windows (vía `keyring`), una clave por proyecto."""

    SERVICIO = "extractor-matriz-nube"

    def __init__(self) -> None:
        self._respaldo = CredencialesEnMemoria()

    def token(self, proyecto_id: uuid.UUID) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.SERVICIO, str(proyecto_id)) or self._respaldo.token(proyecto_id)
        except Exception:
            log.warning("No se pudo leer el Administrador de credenciales", exc_info=True)
            return self._respaldo.token(proyecto_id)

    def guardar(self, proyecto_id: uuid.UUID, token: str) -> None:
        try:
            import keyring

            keyring.set_password(self.SERVICIO, str(proyecto_id), token)
        except Exception:
            log.warning("No se pudo escribir en el Administrador de credenciales: el token vale hasta cerrar la "
                        "aplicación", exc_info=True)
            self._respaldo.guardar(proyecto_id, token)

    def borrar(self, proyecto_id: uuid.UUID) -> None:
        self._respaldo.borrar(proyecto_id)
        try:
            import keyring

            keyring.delete_password(self.SERVICIO, str(proyecto_id))
        except Exception:
            pass

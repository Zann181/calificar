"""Puertos de Sincronización. Los contextos de datos aportan sus `FuenteDeReplica`; `app/composicion.py` los conecta."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.compartido.sobre import Sobre
from app.contextos.sincronizacion.dominio.plan import Manifiesto, Opciones


class FuenteDeReplica(Protocol):
    """Lo que cada contexto sabe de sus propios agregados replicables."""

    @property
    def tipos(self) -> tuple[str, ...]: ...

    def sobres(self, proyecto_id: uuid.UUID) -> Iterable[Sobre]: ...

    def aplicar(self, sesion: Any, sobre: Sobre) -> bool:
        """Aplica el sobre dentro de la transacción `sesion`. False si ya estaba idéntico."""


class AlmacenDeArchivos(Protocol):
    def leer(self, clave: str) -> bytes: ...
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...
    def existe(self, clave: str) -> bool: ...


@dataclass(frozen=True)
class ResultadoLote:
    revision: int
    aplicados: int  # sobres que cambiaron algo en la nube
    iguales: int


class DestinoRemoto(Protocol):
    """La nube vista desde el agente local (HTTP)."""

    def salud(self) -> dict[str, Any]: ...
    def manifiesto(self, proyecto_id: uuid.UUID) -> Manifiesto: ...
    def subir_archivo(self, clave: str, sha256: str, datos: bytes) -> None: ...
    def enviar_lote(self, sobres: list[Sobre], clave_idempotencia: str, *, tomar_control: bool) -> ResultadoLote: ...


@dataclass
class Destino:
    """Ajustes de sincronización de un proyecto (tabla `sync_destinos`). El token no está aquí: va a las credenciales."""

    proyecto_id: uuid.UUID
    url: str = ""
    automatico: bool = True
    pausado: bool = False
    agrupar_s: int = 5
    reconciliar_s: int = 600
    opciones: Opciones = field(default_factory=Opciones)
    instalacion_id: str = ""
    sede: str = "local"  # Fase 4: solo «local» está permitido


@dataclass
class Corrida:
    id: uuid.UUID
    proyecto_id: uuid.UUID
    iniciada_en: datetime
    terminada_en: datetime | None = None
    motivo: str = ""
    estado: str = "en_curso"  # en_curso | ok | error | sin_conexion
    sobres: int = 0
    eliminados: int = 0
    archivos: int = 0
    bytes_enviados: int = 0
    revision: int | None = None
    detalle: str = ""


class RepositorioDeDestinos(Protocol):
    def obtener(self, proyecto_id: uuid.UUID) -> Destino | None: ...
    def guardar(self, destino: Destino) -> None: ...
    def activos(self) -> list[Destino]: ...
    def registrar(self, corrida: Corrida) -> None: ...
    def ultimas(self, proyecto_id: uuid.UUID, cuantas: int = 20) -> list[Corrida]: ...


class Credenciales(Protocol):
    """Token de sincronización por proyecto: Administrador de credenciales de Windows; nunca se devuelve por la API."""

    def token(self, proyecto_id: uuid.UUID) -> str | None: ...
    def guardar(self, proyecto_id: uuid.UUID, token: str) -> None: ...
    def borrar(self, proyecto_id: uuid.UUID) -> None: ...


FabricaDeDestino = Callable[[Destino, str], DestinoRemoto]


class EstadoDeNube(Protocol):
    """Lo que la nube guarda de sí misma: contador de revisión e instalación que la sincroniza."""

    def revision(self) -> int: ...

    def transaccion(self, trabajo: Callable[[Any], bool], *, instalacion: str | None, tomar_control: bool) -> int:
        """Corre `trabajo(sesion)` en una transacción. Si devuelve True sube la revisión. Devuelve la revisión.
        Lanza `ConflictoDeInstalacion` si otra instalación ya sincroniza esta nube y no se pidió tomar el control."""

"""Puertos del contexto Extracción."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.compartido.unidad_de_trabajo import UnidadDeTrabajo
from app.contextos.extraccion.dominio.extraccion import Extraccion

ROLES = ("extractor", "auditor", "ciego", "conciliador")


class LimiteDeUsoAgotado(RuntimeError):
    """El modelo rechazó la llamada porque se acabó el cupo de la cuenta (créditos o ventana de uso).

    No es un fallo de la extracción: se pausa y se reanuda sola. `restablece` es cuándo vuelve el cupo, si se sabe.
    """

    def __init__(self, mensaje: str, restablece: datetime | None = None) -> None:
        super().__init__(mensaje)
        self.restablece = restablece


@dataclass(frozen=True)
class RespuestaModelo:
    texto: str
    # entrada, cache_escritura, cache_lectura, salida, costo_usd, segundos, modelo
    uso: dict[str, Any] = field(default_factory=dict)


class ModeloDeLenguaje(Protocol):
    """ADR 0002: un mensaje de sistema (el libro) y un mensaje de usuario por llamada.

    `imagenes` son las páginas renderizadas (nombre de archivo → PNG); el modelo las abre con la
    herramienta Read. `nivel` lo decide el portero (ADR 0005): "especializado" o "ligero"; el adaptador
    lo traduce al modelo configurado.
    """

    def completar(self, *, rol: str, sistema: str, mensaje: str, imagenes: dict[str, bytes] | None = None,
                  nivel: str = "especializado") -> RespuestaModelo: ...


@dataclass(frozen=True)
class ResultadoValidacion:
    errores: list[str]
    avisos: list[str]


class ValidadorDeExtraccion(Protocol):
    def comprobar(self) -> None:
        """Lanza una excepción si al validador le falta algo para correr. Se llama antes de pagar al modelo."""
        ...

    def validar(self, salida: list[dict[str, Any]], libro: dict[str, Any], texto: str | None) -> ResultadoValidacion:
        """`texto`: el texto del artículo contra el que V23 busca cada cita (el mismo del anclaje, H7).
        None: sin V23."""
        ...


class LectorPdf(Protocol):
    def textos_en_rect(self, pdf: bytes, rects: dict[str, tuple[int, tuple[float, float, float, float]]]) -> dict[str, str]:
        """Texto de la capa del PDF dentro de cada rectángulo: {id: (página base 1, rect)} → {id: texto}."""
        ...

    def renderizar(self, pdf: bytes, paginas: list[int], ppp: int = 110) -> dict[int, bytes]: ...


@dataclass(frozen=True)
class ArticuloParaExtraer:
    articulo_id: uuid.UUID
    nombre_archivo: str
    pdf: bytes
    documento: dict[str, Any]  # DocumentoEstructurado.a_dict() con filas_grilla en cada tabla


class FuenteDeArticulos(Protocol):
    """Lo implementa la composición con los casos de uso de Biblioteca."""

    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> ArticuloParaExtraer: ...
    def iniciar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, *, confirmar_reextraccion: bool,
                motivo: str | None) -> None: ...
    def pasar_a_auditoria(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> None: ...
    def fallar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, paso: str, mensaje: str) -> None: ...


@dataclass(frozen=True)
class LibroVigente:
    id: uuid.UUID
    contenido: dict[str, Any]


class FuenteDeNormas(Protocol):
    def libro_activo(self, proyecto_id: uuid.UUID) -> LibroVigente: ...


class NumeracionDeEstudios(Protocol):
    """Siguiente número de Estudio libre del proyecto (la reserva atómica con varios trabajadores es F3)."""

    def siguiente(self, proyecto_id: uuid.UUID) -> int: ...


class RepositorioDeExtracciones(Protocol):
    def agregar(self, extraccion: Extraccion) -> None: ...
    def obtener(self, proyecto_id: uuid.UUID, extraccion_id: uuid.UUID) -> Extraccion: ...
    def de_articulo(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> list[Extraccion]: ...
    def recientes(self, proyecto_id: uuid.UUID, desde: datetime) -> list[Extraccion]: ...
    def en_curso(self) -> list[Extraccion]:
        """Las no terminadas de todos los proyectos."""
        ...


class UnidadDeTrabajoExtraccion(UnidadDeTrabajo, Protocol):
    @property
    def extracciones(self) -> RepositorioDeExtracciones: ...


@dataclass(frozen=True)
class PedidoGuardado:
    """Pedido de extracción que espera o corre en el ejecutor; `opciones` son las de OpcionesDeExtraccion."""

    proyecto_id: uuid.UUID
    articulo_id: uuid.UUID
    nombre: str
    opciones: dict[str, Any]


class ColaDeExtracciones(Protocol):
    """Cola del ejecutor guardada en la base: lo que quedó al cerrar la aplicación se retoma al abrirla."""

    def guardar(self, pedido: PedidoGuardado) -> None: ...
    def quitar(self, articulo_id: uuid.UUID) -> None: ...
    def pendientes(self) -> list[PedidoGuardado]:
        """En orden de llegada."""
        ...

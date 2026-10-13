"""Usuario local y proyecto válido.

Sin login: la aplicación es de uso local y la API entra sola como el usuario local (ADMIN_CORREO), que firma las
revisiones de celdas. La tabla `usuarios` se conserva solo para eso; no hay contraseñas ni sesiones.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.db import RegistroProyecto, RegistroUsuario

ROLES = ("extractor", "revisor", "administrador")


@dataclass(frozen=True)
class Usuario:
    id: uuid.UUID
    correo: str
    nombre: str
    rol: str


def crear_usuario(sesion: Session, *, correo: str, nombre: str, rol: str) -> Usuario:
    """Crea el usuario si no existe (por correo). No lleva contraseña: `hash_clave` queda vacío."""
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    existente = sesion.scalar(select(RegistroUsuario).where(RegistroUsuario.correo == correo.lower()))
    if existente is not None:
        return Usuario(existente.id, existente.correo, existente.nombre, existente.rol)
    r = RegistroUsuario(id=uuid.uuid4(), correo=correo.lower(), nombre=nombre, rol=rol, hash_clave="")
    sesion.add(r)
    sesion.commit()
    return Usuario(r.id, r.correo, r.nombre, r.rol)


def _fabrica(request: Request) -> Callable[[], Session]:
    fabrica: Callable[[], Session] = request.app.state.contenedor.fabrica
    return fabrica


def usuario_actual(request: Request) -> Usuario:
    """El usuario local (se crea la primera vez si falta)."""
    ajustes = request.app.state.contenedor.ajustes
    with _fabrica(request)() as s:
        return crear_usuario(s, correo=ajustes.admin_correo, nombre=ajustes.admin_nombre, rol="administrador")


def proyecto_valido(proyecto_id: uuid.UUID, request: Request) -> uuid.UUID:
    with _fabrica(request)() as s:
        if s.get(RegistroProyecto, proyecto_id) is None:
            raise HTTPException(status_code=404, detail="Proyecto inexistente")
    return proyecto_id


enrutador = APIRouter(prefix="/api/v1", tags=["proyectos"])


@enrutador.get("/proyectos")
def proyectos(request: Request) -> list[dict[str, Any]]:
    with _fabrica(request)() as s:
        return [{"id": str(p.id), "nombre": p.nombre}
                for p in s.scalars(select(RegistroProyecto).order_by(RegistroProyecto.nombre))]

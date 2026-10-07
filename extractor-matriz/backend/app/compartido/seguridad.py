"""Usuarios, contraseñas y sesión con cookie firmada.

Roles: extractor, revisor, administrador. Desde la F1 existe el administrador semilla; la
restricción por rol en revisión llega en la F5 (solo revisor y administrador aprueban).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compartido.db import RegistroProyecto, RegistroUsuario

ROLES = ("extractor", "revisor", "administrador")
_N, _R, _P = 2**14, 8, 1


def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calc = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Usuario:
    id: uuid.UUID
    correo: str
    nombre: str
    rol: str


def crear_usuario(sesion: Session, *, correo: str, nombre: str, rol: str, clave: str) -> Usuario:
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    if len(clave) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    existente = sesion.scalar(select(RegistroUsuario).where(RegistroUsuario.correo == correo.lower()))
    if existente is not None:
        return Usuario(existente.id, existente.correo, existente.nombre, existente.rol)
    r = RegistroUsuario(id=uuid.uuid4(), correo=correo.lower(), nombre=nombre, rol=rol, hash_clave=hash_clave(clave))
    sesion.add(r)
    sesion.commit()
    return Usuario(r.id, r.correo, r.nombre, r.rol)


def _fabrica(request: Request) -> Callable[[], Session]:
    fabrica: Callable[[], Session] = request.app.state.contenedor.fabrica
    return fabrica


def usuario_actual(request: Request) -> Usuario:
    uid = request.session.get("usuario_id")
    if not uid:
        correo = getattr(request.app.state, "usuario_sin_login", None)
        if correo:
            with _fabrica(request)() as s:
                r = s.scalar(select(RegistroUsuario).where(RegistroUsuario.correo == correo))
            if r is not None and r.activo:
                return Usuario(r.id, r.correo, r.nombre, r.rol)
        raise HTTPException(status_code=401, detail="Inicie sesión")
    with _fabrica(request)() as s:
        r = s.get(RegistroUsuario, uuid.UUID(uid))
    if r is None or not r.activo:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sesión inválida")
    return Usuario(r.id, r.correo, r.nombre, r.rol)


def proyecto_valido(proyecto_id: uuid.UUID, request: Request, _: Usuario = Depends(usuario_actual)) -> uuid.UUID:
    with _fabrica(request)() as s:
        if s.get(RegistroProyecto, proyecto_id) is None:
            raise HTTPException(status_code=404, detail="Proyecto inexistente")
    return proyecto_id


class Credenciales(BaseModel):
    correo: str
    clave: str


enrutador = APIRouter(prefix="/api/v1", tags=["sesión"])


def _usuario_json(u: Usuario) -> dict[str, Any]:
    return {"id": str(u.id), "correo": u.correo, "nombre": u.nombre, "rol": u.rol}


@enrutador.post("/sesion")
def entrar(datos: Credenciales, request: Request) -> dict[str, Any]:
    with _fabrica(request)() as s:
        r = s.scalar(select(RegistroUsuario).where(RegistroUsuario.correo == datos.correo.lower()))
    if r is None or not r.activo or not verificar_clave(datos.clave, r.hash_clave):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    request.session.clear()
    request.session["usuario_id"] = str(r.id)
    return _usuario_json(Usuario(r.id, r.correo, r.nombre, r.rol))


@enrutador.delete("/sesion")
def salir(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@enrutador.get("/sesion")
def quien(u: Usuario = Depends(usuario_actual)) -> dict[str, Any]:
    return _usuario_json(u)


@enrutador.get("/proyectos")
def proyectos(request: Request, _: Usuario = Depends(usuario_actual)) -> list[dict[str, str]]:
    with _fabrica(request)() as s:
        return [{"id": str(p.id), "nombre": p.nombre}
                for p in s.scalars(select(RegistroProyecto).order_by(RegistroProyecto.nombre))]

"""Comandos de administración.

    python -m app.cli semilla                    proyecto, administrador y libro de códigos
    python -m app.cli importar-matriz <xlsx> [--reemplazar]
    python -m app.cli cargar-carpeta <carpeta>   carga todos los PDF (rechaza duplicados)
    python -m app.cli convertir-pendientes       convierte los artículos NUEVO (sin despachador)
    python -m app.cli extraer <articulo_id> --documento <n> [--estudio <n>] [--covidence <n>] [--via <texto>]
                      [--reextraer [--motivo <texto>]]   cuatro roles con Claude Code CLI (ADR 0002)
    python -m app.cli despachar                  corre el despachador de la outbox
    python -m app.cli exportar <salida.xlsx>
    python -m app.cli crear-usuario <correo> <nombre> <rol>   (pide la contraseña)
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.compartido.db import RegistroProyecto
from app.compartido.seguridad import crear_usuario
from app.composicion import Contenedor, construir
from app.config import settings
from app.contextos.biblioteca.dominio.articulo import EstadoArticulo
from app.contextos.extraccion.aplicacion.casos_de_uso import OpcionesDeExtraccion


def _proyecto(c: Contenedor, crear: bool = False) -> uuid.UUID:
    nombre = c.ajustes.proyecto_nombre
    with c.fabrica() as s:
        p = s.scalar(select(RegistroProyecto).where(RegistroProyecto.nombre == nombre))
        if p is None:
            if not crear:
                sys.exit(f"No existe el proyecto '{nombre}'. Ejecute: python -m app.cli semilla")
            p = RegistroProyecto(id=uuid.uuid4(), nombre=nombre)
            s.add(p)
            s.commit()
        return p.id


def semilla(c: Contenedor, _: argparse.Namespace) -> None:
    pid = _proyecto(c, crear=True)
    if not c.ajustes.admin_clave:
        sys.exit("Defina ADMIN_CLAVE en .env (mínimo 10 caracteres) antes de la semilla")
    with c.fabrica() as s:
        u = crear_usuario(s, correo=c.ajustes.admin_correo, nombre=c.ajustes.admin_nombre, rol="administrador",
                          clave=c.ajustes.admin_clave)
    libro = json.loads(c.ajustes.libro_de_codigos.read_text(encoding="utf-8"))
    v = c.normas.publicar.ejecutar(pid, libro)
    c.despachador.despachar_pendientes()
    print(f"Proyecto {pid} · administrador {u.correo} · libro {v.version} ({v.hash[:12]})")


def importar_matriz(c: Contenedor, a: argparse.Namespace) -> None:
    pid = _proyecto(c)
    ruta = Path(a.xlsx)
    r = c.matriz.importar.ejecutar(pid, ruta.read_bytes(), ruta.name, a.reemplazar)
    print(f"{r.filas} filas · {r.documentos} documentos · {r.notas_heredadas} notas heredadas · "
          f"{len(r.fuera_de_vocabulario)} celdas fuera del vocabulario del libro · {r.reemplazadas} reemplazadas")


def cargar_carpeta(c: Contenedor, a: argparse.Namespace) -> None:
    pid = _proyecto(c)
    nuevos = duplicados = errores = 0
    for ruta in sorted(Path(a.carpeta).glob("*.pdf")):
        r = c.biblioteca.cargar.ejecutar(pid, ruta.name, ruta.read_bytes())
        if r.error:
            errores += 1
            print(f"ERROR     {ruta.name}: {r.error}")
        elif r.duplicado:
            duplicados += 1
            print(f"DUPLICADO {ruta.name} = {r.duplicado_de}")
        else:
            nuevos += 1
            print(f"CARGADO   {ruta.name}")
    print(f"\n{nuevos} cargados · {duplicados} duplicados rechazados · {errores} con error")


def convertir_pendientes(c: Contenedor, a: argparse.Namespace) -> None:
    pid = _proyecto(c)
    pendientes = c.biblioteca.consultas.listar(pid, EstadoArticulo.NUEVO).articulos[: a.limite or None]
    for i, art in enumerate(pendientes, 1):
        print(f"[{i}/{len(pendientes)}] {art.nombre_archivo} ...", flush=True)
        estado = c.biblioteca.convertir.ejecutar(pid, art.id)
        print(f"    {estado}")


def extraer(c: Contenedor, a: argparse.Namespace) -> None:
    pid = _proyecto(c)
    opciones = OpcionesDeExtraccion(documento=a.documento, estudio_inicial=a.estudio, covidence=a.covidence,
                                    via=a.via, confirmar_reextraccion=a.reextraer, motivo=a.motivo)
    print(f"Extrayendo {a.articulo_id} (unos 4 minutos y 2,6 USD equivalentes por artículo, según F0) ...", flush=True)
    r = c.extraccion.extraer.ejecutar(pid, uuid.UUID(a.articulo_id), opciones)
    while c.despachador.despachar_pendientes():  # ExtraccionCompletada → filas en Matriz
        pass
    print(f"Extracción {r.extraccion_id}: {r.estado}")
    if r.estado == "COMPLETADA":
        print(f"  Estudios {r.estudios} · acuerdo con el codificador ciego {r.acuerdo} · anclas {r.anclas}")
        print(f"  {r.hallazgos_pendientes} hallazgos pendientes · {r.costo_usd} USD equivalentes")
    else:
        for e in r.errores[:20]:
            print(f"  {e}")
        sys.exit(1)


def despachar(c: Contenedor, _: argparse.Namespace) -> None:
    c.despachador.correr()


def exportar(c: Contenedor, a: argparse.Namespace) -> None:
    pid = _proyecto(c)
    e = c.exportar.ejecutar(pid)
    Path(a.salida).write_bytes(c.exportar.leer(pid, e.id))
    print(f"{e.filas_heredadas} filas heredadas y {e.filas_extraidas} extraídas en {a.salida}")


def usuario(c: Contenedor, a: argparse.Namespace) -> None:
    clave = getpass.getpass("Contraseña: ")
    with c.fabrica() as s:
        u = crear_usuario(s, correo=a.correo, nombre=a.nombre, rol=a.rol, clave=clave)
    print(f"Usuario {u.correo} ({u.rol})")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("semilla").set_defaults(f=semilla)
    x = sub.add_parser("importar-matriz")
    x.add_argument("xlsx")
    x.add_argument("--reemplazar", action="store_true")
    x.set_defaults(f=importar_matriz)
    x = sub.add_parser("cargar-carpeta")
    x.add_argument("carpeta")
    x.set_defaults(f=cargar_carpeta)
    x = sub.add_parser("convertir-pendientes")
    x.add_argument("--limite", type=int, default=0)
    x.set_defaults(f=convertir_pendientes)
    x = sub.add_parser("extraer")
    x.add_argument("articulo_id")
    x.add_argument("--documento", type=int, required=True, help="número del artículo en la matriz (columna A)")
    x.add_argument("--estudio", type=int, default=None, help="Estudio inicial; por defecto, el siguiente libre")
    x.add_argument("--covidence", type=int, default=None)
    x.add_argument("--via", default="Covidence", help="vía de identificación")
    x.add_argument("--reextraer", action="store_true", help="confirma la reextracción de un artículo ya extraído")
    x.add_argument("--motivo", default=None, help="obligatorio para reextraer un artículo aprobado")
    x.set_defaults(f=extraer)
    sub.add_parser("despachar").set_defaults(f=despachar)
    x = sub.add_parser("exportar")
    x.add_argument("salida")
    x.set_defaults(f=exportar)
    x = sub.add_parser("crear-usuario")
    x.add_argument("correo")
    x.add_argument("nombre")
    x.add_argument("rol", choices=["extractor", "revisor", "administrador"])
    x.set_defaults(f=usuario)
    a = p.parse_args(argv)
    a.f(construir(settings()), a)


if __name__ == "__main__":
    main()

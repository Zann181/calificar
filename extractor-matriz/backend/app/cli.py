"""Comandos de administración.

    python -m app.cli semilla                    proyecto, administrador y libro de códigos
    python -m app.cli importar-matriz <xlsx> [--reemplazar]
    python -m app.cli cargar-carpeta <carpeta>   carga todos los PDF (rechaza duplicados)
    python -m app.cli convertir-pendientes       convierte los artículos NUEVO (sin despachador)
    python -m app.cli extraer <articulo_id> --documento <n> [--estudio <n>] [--covidence <n>] [--via <texto>]
                      [--reextraer [--motivo <texto>]]   cuatro roles con Claude Code CLI (ADR 0002)
    python -m app.cli despachar                  corre el despachador de la outbox
    python -m app.cli exportar <salida.xlsx>
    python -m app.cli restaurar-nube --url <https://…> [--proyecto <id>] [--reemplazar]
                                                 baja el proyecto desde la nube (token en SYNC_TOKEN o se pide)
    python -m app.cli token-sync                 token de servicio del agente (ADR 0009) y su hash para la nube
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.compartido import registro
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
    with c.fabrica() as s:
        u = crear_usuario(s, correo=c.ajustes.admin_correo, nombre=c.ajustes.admin_nombre, rol="administrador")
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


def migrar_libro(c: Contenedor, _: argparse.Namespace) -> None:
    """Agrega a las filas guardadas las columnas del libro activo que no tienen (libro v2.3). No usa el modelo."""
    pid = _proyecto(c)
    r = c.matriz.agregar_columnas.ejecutar(pid)
    print(f"{r.filas} filas actualizadas · {r.celdas_agregadas} celdas agregadas · {r.calculadas} calculadas sin leer PDF")


def reasignar_documento(c: Contenedor, a: argparse.Namespace) -> None:
    """Cambia el Documento de un artículo y su ID muestra. Rechaza un número que ya usa otro artículo."""
    pid = _proyecto(c)
    n = c.matriz.reasignar_documento.ejecutar(pid, uuid.UUID(a.articulo_id), a.documento,
                                              autor=c.ajustes.admin_correo, motivo=a.motivo)
    print(f"{n} filas actualizadas al Documento {a.documento}")


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


def restaurar_nube(c: Contenedor, a: argparse.Namespace) -> None:
    """Restaura este equipo desde la nube (ADR 0009, Fase 2). Sirve sobre una base vacía (sin correr «semilla») o
    sobre el mismo proyecto; nunca borra lo local."""
    import getpass
    import os

    from app.contextos.sincronizacion.adaptadores.cliente_http import ClienteHttp
    from app.contextos.sincronizacion.dominio.plan import ErrorDeSincronizacion

    token = os.environ.get("SYNC_TOKEN") or getpass.getpass("Token de sincronización: ")
    nube = ClienteHttp(a.url, token, uuid.uuid4().hex)
    try:
        proyectos = nube.proyectos()
        if a.proyecto:
            pid = uuid.UUID(a.proyecto)
        elif len(proyectos) == 1:
            pid = uuid.UUID(proyectos[0]["id"])
        else:
            sys.exit("La nube tiene " + (str(len(proyectos)) + " proyectos: indique --proyecto <id>. "
                     + ", ".join(f"{p['id']} ({p['nombre']})" for p in proyectos)))
        manifiesto = nube.manifiesto(pid)
        plan = c.restaurador.planear(nube, pid, manifiesto)
        print(f"Faltan {len(plan.faltan)} agregados y {len(plan.archivos_faltan)} archivos; difieren "
              f"{len(plan.distintos)} agregados y {len(plan.archivos_distintos)} archivos; "
              f"{len(plan.solo_locales)} existen solo aquí (no se tocan).")
        r = c.restaurador.ejecutar(nube, pid, manifiesto, reemplazar=a.reemplazar)
    except ErrorDeSincronizacion as e:
        sys.exit(str(e))
    except Exception as e:
        if type(e).__name__ == "RestauracionRechazada":
            sys.exit(str(e))
        raise
    print(f"Restaurado: {r.agregados} agregados, {r.archivos} archivos ({r.bytes_bajados / 1e6:.1f} MB).")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("semilla").set_defaults(f=semilla)
    x = sub.add_parser("importar-matriz")
    x.add_argument("xlsx")
    x.add_argument("--reemplazar", action="store_true")
    x.set_defaults(f=importar_matriz)
    sub.add_parser("migrar-libro").set_defaults(f=migrar_libro)
    x = sub.add_parser("reasignar-documento")
    x.add_argument("articulo_id")
    x.add_argument("documento", type=int)
    x.add_argument("--motivo", required=True)
    x.set_defaults(f=reasignar_documento)
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
    sub.add_parser("token-sync")
    x = sub.add_parser("restaurar-nube")
    x.add_argument("--url", required=True)
    x.add_argument("--proyecto", default=None)
    x.add_argument("--reemplazar", action="store_true", help="en lo que difiera, queda la versión de la nube")
    x.set_defaults(f=restaurar_nube)
    a = p.parse_args(argv)
    if a.comando == "token-sync":
        import secrets

        from app.contextos.sincronizacion.api import hash_de_token

        token = secrets.token_urlsafe(32)
        print("Token (péguelo en «Configuración › Nube»; no se vuelve a mostrar):")
        print("  " + token)
        print("Hash (variable SYNC_TOKEN_HASH de la nube):")
        print("  " + hash_de_token(token))
        return
    registro.instalar(settings().registro_ruta)
    a.f(construir(settings()), a)


if __name__ == "__main__":
    main()

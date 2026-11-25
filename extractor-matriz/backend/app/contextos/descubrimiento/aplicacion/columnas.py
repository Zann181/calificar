"""Casos de uso de la Fase 2: perfiles de columnas, evaluación de candidatos, vista previa y exportación.

La evaluación es en vivo (no se guarda): cambiar el perfil recalcula todo sin volver a consultar las fuentes. Nada de
esto escribe en la matriz ni llama a un modelo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.compartido.dominio import ErrorDeDominio
from app.contextos.descubrimiento.dominio.candidato import Candidato, EstadoCandidato
from app.contextos.descubrimiento.dominio.completitud import (
    ColumnaElegida,
    DetalleDeColumna,
    Evaluacion,
    Exigir,
    PerfilDeColumnas,
    Prioridad,
    evaluar,
    ordenar_por_puntaje,
    pasa_exigencia,
    perfil_inicial,
)
from app.contextos.descubrimiento.dominio.detectores import MotorDeDetectores, Nivel
from app.contextos.descubrimiento.dominio.exportar import a_csv, a_ris
from app.contextos.descubrimiento.puertos import (
    CatalogoDeColumnas,
    RepositorioDeAnalisis,
    RepositorioDeCandidatos,
    RepositorioDePerfiles,
)

TODOS = 100_000


class GestionarPerfiles:
    def __init__(self, repo: RepositorioDePerfiles, columnas: CatalogoDeColumnas, motor: MotorDeDetectores) -> None:
        self._repo, self._columnas, self._motor = repo, columnas, motor

    def catalogo(self, proyecto_id: uuid.UUID) -> list[DetalleDeColumna]:
        """Todas las columnas del libro, con su detectabilidad. Las internas (X) se listan pero no se pueden elegir."""
        return [DetalleDeColumna(clave=c.clave, encabezado=c.encabezado, grupo=self._motor.grupo(c.clave),
                                 nivel=self._motor.nivel(c.clave), vocabulario=len(c.valores_permitidos),
                                 derivada=c.derivada, elegible=self._motor.nivel(c.clave) != Nivel.X)
                for c in self._columnas.columnas(proyecto_id)]

    def listar(self, proyecto_id: uuid.UUID) -> list[PerfilDeColumnas]:
        return self._repo.listar(proyecto_id)

    def inicial(self, proyecto_id: uuid.UUID) -> PerfilDeColumnas:
        return perfil_inicial(proyecto_id, {c.clave for c in self._columnas.columnas(proyecto_id)})

    def activo(self, proyecto_id: uuid.UUID) -> PerfilDeColumnas:
        """El perfil predeterminado; si nunca se guardó uno, la propuesta inicial."""
        return self._repo.predeterminado(proyecto_id) or self.inicial(proyecto_id)

    def obtener(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> PerfilDeColumnas:
        return self._repo.obtener(proyecto_id, perfil_id)

    def guardar(self, proyecto_id: uuid.UUID, nombre: str, columnas: list[tuple[str, str]],
                predeterminado: bool = False) -> PerfilDeColumnas:
        existentes = {c.clave for c in self._columnas.columnas(proyecto_id)}
        elegidas: list[ColumnaElegida] = []
        for clave, prioridad in columnas:
            if clave not in existentes:
                raise ErrorDeDominio(f"La columna «{clave}» no está en el libro de códigos vigente")
            if self._motor.nivel(clave) == Nivel.X:
                raise ErrorDeDominio(f"La columna «{clave}» es interna (la asigna el equipo o el programa): no se elige")
            try:
                elegidas.append(ColumnaElegida(clave, Prioridad(prioridad)))
            except ValueError as e:
                raise ErrorDeDominio(f"Prioridad desconocida: {prioridad}") from e
        return self._repo.guardar(PerfilDeColumnas(proyecto_id=proyecto_id, nombre=nombre, columnas=tuple(elegidas),
                                                   predeterminado=predeterminado))

    def borrar(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID) -> None:
        self._repo.borrar(proyecto_id, perfil_id)


@dataclass(frozen=True)
class ListadoEvaluado:
    filas: list[tuple[Candidato, Evaluacion]]
    total: int
    contadores: dict[str, int]
    perfil: PerfilDeColumnas


class EvaluarCandidatos:
    def __init__(self, candidatos: RepositorioDeCandidatos, perfiles: GestionarPerfiles, motor: MotorDeDetectores,
                 analisis: RepositorioDeAnalisis) -> None:
        self._candidatos, self._perfiles, self._motor, self._analisis = candidatos, perfiles, motor, analisis

    def _perfil(self, proyecto_id: uuid.UUID, perfil_id: uuid.UUID | None) -> PerfilDeColumnas:
        return self._perfiles.obtener(proyecto_id, perfil_id) if perfil_id else self._perfiles.activo(proyecto_id)

    def listar(self, proyecto_id: uuid.UUID, *, perfil_id: uuid.UUID | None = None,
               estado: EstadoCandidato | None = None, busqueda_id: uuid.UUID | None = None, texto: str | None = None,
               en_matriz: bool | None = None, orden: str = "reciente", exigir: Exigir = Exigir.NADA, desde: int = 0,
               cuantos: int = 100) -> ListadoEvaluado:
        if desde < 0 or not 1 <= cuantos <= 500:
            raise ErrorDeDominio("Página o tamaño fuera de rango")
        if orden not in ("reciente", "puntaje"):
            raise ErrorDeDominio("Orden desconocido")
        perfil = self._perfil(proyecto_id, perfil_id)
        contadores = self._candidatos.contadores(proyecto_id)
        directo = orden == "reciente" and exigir == Exigir.NADA
        lista, total = self._candidatos.listar(
            proyecto_id, estado=estado, busqueda_id=busqueda_id, texto=texto, en_matriz=en_matriz,
            desde=desde if directo else 0, cuantos=cuantos if directo else TODOS)
        leidos = self._analisis.por_candidatos([c.id for c in lista])
        pares = [(c, evaluar(self._motor, c, perfil, leidos.get(c.id))) for c in lista]
        if directo:
            return ListadoEvaluado(pares, total, contadores, perfil)
        pares = [p for p in pares if pasa_exigencia(p[1], exigir)]
        if orden == "puntaje":
            pares = ordenar_por_puntaje(pares)
        return ListadoEvaluado(pares[desde: desde + cuantos], len(pares), contadores, perfil)

    def vista_previa(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID],
                     perfil_id: uuid.UUID | None = None) -> tuple[PerfilDeColumnas, list[tuple[Candidato, Evaluacion]]]:
        if not ids:
            raise ErrorDeDominio("No hay candidatos seleccionados")
        perfil = self._perfil(proyecto_id, perfil_id)
        por_id = {c.id: c for c in self._candidatos.por_ids(proyecto_id, ids)}
        leidos = self._analisis.por_candidatos(list(por_id))
        return perfil, [(por_id[i], evaluar(self._motor, por_id[i], perfil, leidos.get(i))) for i in ids if i in por_id]

    def exportar(self, proyecto_id: uuid.UUID, ids: list[uuid.UUID], formato: str,
                 perfil_id: uuid.UUID | None = None) -> tuple[str, str, str]:
        """(nombre del archivo, contenido, tipo MIME)."""
        if formato not in ("csv", "ris"):
            raise ErrorDeDominio("Formato desconocido: use csv o ris")
        perfil, pares = self.vista_previa(proyecto_id, ids, perfil_id)
        if formato == "ris":
            return "candidatos.ris", a_ris([c for c, _e in pares]), "application/x-research-info-systems"
        return "candidatos.csv", a_csv(list(pares), [c.clave for c in perfil.columnas]), "text/csv; charset=utf-8"

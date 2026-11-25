// Cobertura de un candidato frente a las columnas elegidas (plan «Buscar», sección 5.3). Solo presentación:
// el cálculo del puntaje lo hace el servidor; esto reparte la barra apilada con los mismos pesos.
import type { CeldaPrevia, EstadoCelda, EtiquetaCandidato, Evaluacion, Nivel, Prioridad } from "./tipos";

export const PESOS: Record<Prioridad, number> = { IMPRESCINDIBLE: 5, IMPORTANTE: 3, DESEABLE: 1 };

export const PRIORIDADES: [Prioridad, string][] = [
  ["IMPRESCINDIBLE", "Imprescindible"],
  ["IMPORTANTE", "Importante"],
  ["DESEABLE", "Deseable"],
];

export const ETIQUETAS: Record<EtiquetaCandidato, string> = {
  PROBABLE: "Probable",
  DUDOSO: "Dudoso",
  SIN_DATOS: "Sin datos suficientes",
  INCOMPLETO: "Incompleto",
  NO_APLICA: "No aplica",
};

export const ESTADOS_CELDA: Record<EstadoCelda, string> = {
  METADATO: "Metadato",
  INDICIO: "Indicio",
  PENDIENTE: "Pendiente de PDF",
  AUSENTE: "Ausente",
  NO_APLICA: "Interna",
};

export const NIVELES: Record<Nivel, string> = {
  M: "Metadato de la fuente",
  R: "Título, resumen o palabras clave",
  T: "Solo el texto completo (PDF)",
  X: "Interna: la asigna el equipo o el programa",
};

export type Segmentos = { cubierto: number; pendiente: number; ausente: number };

/** Fracciones (0–1) del peso total: verde = metadato o indicio, rayado = pendiente de PDF, vacío/rojo = ausente. */
export function segmentos(celdas: CeldaPrevia[]): Segmentos {
  const contables = celdas.filter((c) => c.estado !== "NO_APLICA");
  const total = contables.reduce((s, c) => s + PESOS[c.prioridad], 0);
  if (!total) return { cubierto: 0, pendiente: 0, ausente: 0 };
  const suma = (f: (c: CeldaPrevia) => boolean) =>
    contables.filter(f).reduce((s, c) => s + PESOS[c.prioridad], 0) / total;
  return {
    cubierto: suma((c) => c.estado === "METADATO" || c.estado === "INDICIO"),
    pendiente: suma((c) => c.estado === "PENDIENTE"),
    ausente: suma((c) => c.estado === "AUSENTE"),
  };
}

export const porcentaje = (x: number) => `${Math.round(x * 100)}%`;

/** «62 % (máx. 100 %)»: lo que ya muestra y lo más que podría llegar a mostrar si lo pendiente apareciera en el PDF. */
export function textoPuntaje(ev: Evaluacion): string {
  return `${porcentaje(ev.puntaje)} (máx. ${porcentaje(ev.maximo)})`;
}

/** Mueve un elemento de una lista una posición (−1 arriba, +1 abajo) sin salirse de los bordes. */
export function mover<T>(lista: T[], indice: number, delta: -1 | 1): T[] {
  const destino = indice + delta;
  if (indice < 0 || indice >= lista.length || destino < 0 || destino >= lista.length) return lista;
  const copia = [...lista];
  [copia[indice], copia[destino]] = [copia[destino], copia[indice]];
  return copia;
}

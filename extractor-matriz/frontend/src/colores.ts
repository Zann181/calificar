// Colores de celda de la sección 9.3, por estado de revisión y nivel de ancla.
import type { CeldaResumen } from "./tipos";

export type Color = "verde" | "rojo" | "naranja" | "amarillo-borde" | "amarillo" | "gris" | "ninguno";

export function colorDe(c: CeldaResumen | undefined): Color {
  if (!c) return "ninguno";
  if (c.estado_revision === "APROBADA" || c.estado_revision === "CORREGIDA") return "verde";
  if (c.estado_revision === "RECHAZADA" || c.estado_revision === "NO_VERIFICABLE" || c.hallazgo) return "rojo";
  if (c.discrepancia) return "naranja";
  if (c.estado_revision === "POR_CONFIRMAR") return "amarillo-borde";
  if (c.tipo_valor === "INFERIDO") return "amarillo";
  if (c.estado_revision === "SIN_EVIDENCIA") return "gris";
  return "ninguno";
}

export const LEYENDA: [Color, string][] = [
  ["gris", "Heredada, sin evidencia"],
  ["ninguno", "Pendiente, citas verificadas"],
  ["amarillo", "Inferida"],
  ["amarillo-borde", "Por confirmar"],
  ["naranja", "Discrepancia del artículo"],
  ["rojo", "No verificable o hallazgo"],
  ["verde", "Aprobada o corregida"],
];

const PRIORIDAD: Record<Color, number> = {
  rojo: 0,
  naranja: 1,
  "amarillo-borde": 2,
  amarillo: 3,
  ninguno: 4,
  gris: 5,
  verde: 6,
};

export const prioridad = (c: Color) => PRIORIDAD[c];

export function revisada(c: CeldaResumen): boolean {
  return c.estado_revision === "APROBADA" || c.estado_revision === "CORREGIDA";
}

// Aprobar exige motivo en estos estados (invariante 1 del agregado FilaDeEfecto).
export function aprobarExigeMotivo(c: CeldaResumen): boolean {
  return ["SIN_EVIDENCIA", "POR_CONFIRMAR", "NO_VERIFICABLE"].includes(c.estado_revision);
}

export function mostrarValor(valor: unknown, estadoDato: string | null): string {
  if (valor === null || valor === undefined) return estadoDato ?? "";
  if (typeof valor === "object" && valor && "$fecha" in valor) return String((valor as { $fecha: string }).$fecha).slice(0, 10);
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}

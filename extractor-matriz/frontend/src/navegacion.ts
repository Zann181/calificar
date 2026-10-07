// Navegación con retorno (sección 9.5): pila en Zustand, sincronizada con el historial del navegador
// para que el botón Atrás (y Atrás del teléfono) también vuelva.
import { create } from "zustand";

export type VistaVisor = {
  articuloId: string;
  pagina: number;
  zoom: number;
  rect?: [number, number, number, number] | null;
  cita?: string;
  etiqueta?: string;
};

export type Vista = {
  articuloId?: string;
  estudio?: number;
  columna?: string;
  visor?: VistaVisor;
};

const MAXIMO = 50;

type Navegacion = {
  pila: Vista[];
  actual: Vista;
  ir: (v: Vista) => void;
  volver: () => void;
  irA: (indice: number) => void;
  _desdeHistorial: (v: Vista, pila: Vista[]) => void;
};

export const useNavegacion = create<Navegacion>((set, get) => ({
  pila: [],
  actual: {},
  ir: (v) => {
    const { actual, pila } = get();
    const nuevaPila = [...pila, actual].slice(-MAXIMO);
    set({ pila: nuevaPila, actual: v });
    window.history.pushState({ vista: v, pila: nuevaPila }, "");
  },
  volver: () => {
    if (get().pila.length) window.history.back();
  },
  irA: (indice) => {
    // Saltar a una entrada de la pila equivale a volver varias veces.
    const pasos = get().pila.length - indice;
    if (pasos > 0) window.history.go(-pasos);
  },
  _desdeHistorial: (v, pila) => set({ actual: v, pila }),
}));

window.addEventListener("popstate", (e) => {
  const estado = e.state as { vista?: Vista; pila?: Vista[] } | null;
  useNavegacion.getState()._desdeHistorial(estado?.vista ?? {}, estado?.pila ?? []);
});
window.history.replaceState({ vista: {}, pila: [] }, "");

window.addEventListener("keydown", (e) => {
  if (e.altKey && e.key === "ArrowLeft") {
    e.preventDefault();
    useNavegacion.getState().volver();
  }
});

export function describir(v: Vista): string {
  const partes = ["Matriz"];
  if (v.estudio) partes.push(`Estudio ${v.estudio}`);
  if (v.columna) partes.push(v.columna);
  if (v.visor) partes.push(`p. ${v.visor.pagina}`);
  return partes.join(" › ");
}

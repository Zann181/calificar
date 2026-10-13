// Vista actual (estudio, columna, visor) en Zustand. Sin historial: no hay botón de retroceso.
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

type Navegacion = {
  actual: Vista;
  ir: (v: Vista) => void;
};

export const useNavegacion = create<Navegacion>((set) => ({
  actual: {},
  ir: (v) => set({ actual: v }),
}));

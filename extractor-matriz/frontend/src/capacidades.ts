// Qué puede hacer esta copia de la aplicación (ADR 0009): en el equipo local todo; en la nube, solo leer.
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

export function useCapacidades() {
  return useQuery({ queryKey: ["capacidades"], queryFn: api.capacidades, staleTime: Infinity, retry: false });
}

/** False solo en la nube. Si la consulta falla (servidor antiguo) se asume el equipo local. */
export function useEscritura(): boolean {
  return useCapacidades().data?.escritura ?? true;
}

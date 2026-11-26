// Qué puede hacer esta copia de la aplicación (ADR 0009): en el equipo local todo; en la nube, solo leer.
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

export function useCapacidades() {
  return useQuery({ queryKey: ["capacidades"], queryFn: api.capacidades, staleTime: Infinity, retry: false });
}

/** True donde se puede lanzar búsquedas: en el equipo y, desde el ADR 0012, también en la web. */
export function usePuedeBuscar(): boolean {
  const c = useCapacidades().data;
  return c?.puede_buscar ?? c?.escritura ?? true;
}

/** False solo en la nube. Si la consulta falla (servidor antiguo) se asume el equipo local. */
export function useEscritura(): boolean {
  return useCapacidades().data?.escritura ?? true;
}

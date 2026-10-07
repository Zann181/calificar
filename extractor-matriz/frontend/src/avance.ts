// Avance de las extracciones: consulta al servidor y anima el porcentaje entre hitos.
//
// El servidor guarda un porcentaje oficial que sube cuando el motor termina un paso (extractor, validador,
// anclaje, auditoría, conciliación). Algunos pasos duran minutos (el extractor, unos 5), así que entre hito e hito
// la barra avanza con el tiempo típico medido, sin pasar nunca del tope del paso (95 % del recorrido): al llegar
// el hito real, salta al valor oficial. Lo animado es una estimación; el oficial es el del servidor.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import type { AvanceExtraccion, AvanceRespuesta } from "./tipos";

const RAPIDO_MS = 1500; // hay algo corriendo
const LENTO_MS = 6000; // nada en curso: solo se vigila que alguien lance una

// Pasos que ve la persona en el detalle del monitor (mismos hitos que PASOS del motor).
export const PASOS_VISIBLES = [
  { clave: "preparando", texto: "Preparar el artículo (texto e imágenes)", desde: 2, hasta: 8 },
  { clave: "extrayendo", texto: "Extractor: llena las 54 columnas", desde: 8, hasta: 45 },
  { clave: "corrigiendo", texto: "Corregir lo que rechace el validador", desde: 45, hasta: 58 },
  { clave: "anclando", texto: "Anclar cada cita al PDF", desde: 58, hasta: 62 },
  { clave: "auditando", texto: "Auditor y codificador ciego", desde: 62, hasta: 85 },
  { clave: "conciliando", texto: "Conciliar diferencias", desde: 85, hasta: 99 },
] as const;

// Tras lanzar una extracción hay un instante en que el servidor aún no la registró: se consulta seguido unos segundos.
let rapidoHasta = 0;
export const acelerarAvance = (segundos = 25) => {
  rapidoHasta = Date.now() + segundos * 1000;
};

export const enCurso = (a: AvanceExtraccion) => !a.terminada_en && !a.fallida;

/** Porcentaje a mostrar ahora: el oficial más lo que se estima del paso actual. */
export function porcentajeVisible(a: AvanceExtraccion, ahoraMs: number): number {
  if (a.terminada_en || a.fallida) return a.progreso;
  const transcurrido = Math.max(0, (ahoraMs - Date.parse(a.paso_desde)) / 1000);
  const fraccion = a.segundos_tipicos > 0 ? Math.min(0.95, transcurrido / a.segundos_tipicos) : 0;
  return Math.min(a.hasta - 1, Math.floor(a.progreso + (a.hasta - a.progreso) * fraccion));
}

export function formatoTiempo(segundos: number): string {
  const s = Math.max(0, Math.round(segundos));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function useAvance(pid: string) {
  const qc = useQueryClient();
  const consulta = useQuery({
    queryKey: ["avance", pid],
    queryFn: () => api.avance(pid),
    enabled: !!pid,
    refetchInterval: (q) => {
      const d = q.state.data as AvanceRespuesta | undefined;
      if (Date.now() < rapidoHasta) return RAPIDO_MS;
      return d && (d.en_cola.length > 0 || d.extracciones.some(enCurso)) ? RAPIDO_MS : LENTO_MS;
    },
    refetchIntervalInBackground: false,
  });
  const datos = consulta.data;
  const activo = !!datos && (datos.en_cola.length > 0 || datos.extracciones.some(enCurso));

  // Reloj para animar la barra: solo corre mientras hay algo en curso.
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    if (!activo) return;
    setAhora(Date.now());
    const t = setInterval(() => setAhora(Date.now()), 500);
    return () => clearInterval(t);
  }, [activo]);

  // Cuando una extracción cambia de estado o termina, se refrescan la lista de artículos y la matriz.
  const firma = useRef<string>("");
  useEffect(() => {
    if (!datos) return;
    const f = datos.extracciones
      .map((e) => `${e.extraccion_id}:${e.estado}`)
      .sort()
      .join("|");
    if (firma.current && f !== firma.current) {
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
      qc.invalidateQueries({ queryKey: ["filas", pid] });
    }
    firma.current = f;
  }, [datos, qc, pid]);

  const porArticulo = new Map((datos?.extracciones ?? []).map((e) => [e.articulo_id, e]));
  const enCola = new Map((datos?.en_cola ?? []).map((c) => [c.articulo_id, c]));
  return { porArticulo, enCola, ahora, activo, error: consulta.error as Error | null };
}

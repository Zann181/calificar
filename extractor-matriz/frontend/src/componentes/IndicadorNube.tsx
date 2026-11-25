// Indicadores de la nube (ADR 0009, secciones 6.6 y 7):
//   - IndicadorVisor (en la nube): sondea /revision cada 15 s y recarga los datos cuando sube; avisa si no llega nada.
//   - IndicadorSync (en el equipo local): estado del agente de sincronización; al pulsarlo abre «Configuración › Nube».
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api";
import { useCapacidades } from "../capacidades";
import type { EstadoSync } from "../tipos";
import { PanelNube } from "./PanelNube";

const SONDEO_MS = 15_000;
const SIN_NOVEDADES_MS = 15 * 60_000;

function hace(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h`;
}

/** Reloj que obliga a repintar cada segundo (para «hace 12 s»). */
function useReloj(cada = 1000) {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setT(Date.now()), cada);
    return () => clearInterval(id);
  }, [cada]);
  return t;
}

export function IndicadorVisor() {
  const qc = useQueryClient();
  const cap = useCapacidades();
  const [revision, setRevision] = useState<number | null>(null);
  const [cambioEn, setCambioEn] = useState(() => Date.now());
  const [fallo, setFallo] = useState(false);
  const ahora = useReloj();

  useEffect(() => {
    let vivo = true;
    let ultima: number | null = null;
    let enVivo = false; // true mientras la conexión de eventos del servidor (SSE) está abierta
    const recibir = (nueva: number) => {
      setFallo(false);
      if (ultima !== null && nueva !== ultima) {
        setCambioEn(Date.now());
        // Todo lo que se muestra se vuelve a pedir, salvo las capacidades.
        qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "capacidades" });
      }
      ultima = nueva;
      setRevision(nueva);
    };
    // Respaldo: sondeo de /revision cada 15 s. Solo corre cuando no hay conexión de eventos abierta.
    const sondear = async () => {
      if (enVivo) return;
      try {
        // El servidor responde con ETag y `no-cache`: el navegador pregunta de forma condicional (304) por su cuenta.
        const r = await fetch("/api/v1/revision", { credentials: "same-origin" });
        if (!vivo) return;
        if (r.status === 401) {
          qc.invalidateQueries({ queryKey: ["proyectos"] });
          return;
        }
        if (!r.ok) throw new Error(String(r.status));
        recibir(((await r.json()) as { revision: number }).revision);
      } catch {
        if (vivo) setFallo(true);
      }
    };
    // Principal: eventos del servidor; la revisión llega al instante, sin consultar la base en cada vuelta.
    let fuente: EventSource | null = null;
    if (typeof EventSource !== "undefined") {
      fuente = new EventSource("/api/v1/eventos", { withCredentials: true });
      fuente.addEventListener("revision", (ev) => {
        enVivo = true;
        recibir((JSON.parse((ev as MessageEvent).data) as { revision: number }).revision);
      });
      fuente.onerror = () => {
        enVivo = false; // el navegador reintenta solo; mientras, manda el sondeo
        sondear();
      };
    }
    sondear();
    const id = setInterval(sondear, SONDEO_MS);
    return () => {
      vivo = false;
      fuente?.close();
      clearInterval(id);
    };
  }, [qc]);

  const quieto = ahora - cambioEn > SIN_NOVEDADES_MS;
  return (
    <div className={`indicador-nube ${fallo ? "mal" : quieto ? "aviso" : "ok"}`} role="status">
      <span className="punto" />
      <span>
        {fallo
          ? "Sin conexión con la nube"
          : `Copia de solo lectura · actualizado hace ${hace(ahora - cambioEn)}${revision !== null ? ` · revisión ${revision}` : ""}`}
      </span>
      {quieto && !fallo && <span className="tenue"> · sin novedades: el equipo local puede estar apagado</span>}
      {cap.data?.lector && (
        <>
          <span className="tenue"> · {cap.data.lector}</span>
          <button
            className="sin-borde"
            onClick={async () => {
              await api.salir();
              window.location.reload();
            }}
          >
            Salir
          </button>
        </>
      )}
    </div>
  );
}

function textoDe(e: EstadoSync | undefined): { clase: string; texto: string; titulo: string } {
  if (!e) return { clase: "aviso", texto: "Nube…", titulo: "" };
  switch (e.estado) {
    case "sin_configurar":
      return { clase: "tenue", texto: "Nube: sin configurar", titulo: e.detalle };
    case "pausado":
      return { clase: "aviso", texto: "⏸ Nube en pausa", titulo: e.detalle };
    case "sincronizado":
      return {
        clase: "ok",
        texto: `✔ Sincronizado${e.hace_s !== null ? ` hace ${hace(e.hace_s * 1000)}` : ""}`,
        titulo: e.revision ? `Revisión ${e.revision} en la nube` : "",
      };
    case "subiendo":
      return {
        clase: "trabajando",
        texto: e.total ? `↻ Subiendo ${Math.min(e.hechos + 1, e.total)} de ${e.total}` : "↻ Sincronizando…",
        titulo: e.fase === "archivos" ? "Subiendo archivos" : "Subiendo cambios",
      };
    case "sin_conexion":
      return {
        clase: "aviso",
        texto: `⚠ Sin conexión${e.cambios_pendientes ? ` · ${e.cambios_pendientes} pendientes` : ""}`,
        titulo: e.detalle,
      };
    default:
      return { clase: "mal", texto: `✖ Error: ${e.detalle.slice(0, 60)}`, titulo: e.detalle };
  }
}

export function IndicadorSync({ pid }: { pid: string }) {
  const [abierto, setAbierto] = useState(false);
  const estado = useQuery({
    queryKey: ["sync-estado", pid],
    queryFn: () => api.nube.estado(pid),
    enabled: !!pid,
    refetchInterval: (q) => (q.state.data?.estado === "subiendo" ? 1500 : 5000),
    retry: false,
  });
  // Un instante de cortesía para que «hace 8 s» avance entre sondeos.
  useReloj(5000);
  const t = textoDe(estado.data);
  return (
    <>
      <button className={`indicador-sync ${t.clase}`} onClick={() => setAbierto(true)} title={t.titulo || "Configuración › Nube"}>
        {t.texto}
      </button>
      {abierto && <PanelNube pid={pid} onCerrar={() => setAbierto(false)} />}
    </>
  );
}

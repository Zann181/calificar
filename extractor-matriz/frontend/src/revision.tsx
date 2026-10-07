// Aprobar, corregir y rechazar (sección 5.4): un solo diálogo para pedir el motivo y, al corregir, el valor.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { create } from "zustand";

import { api } from "./api";
import { aprobarExigeMotivo, mostrarValor } from "./colores";
import type { CeldaResumen, Columna } from "./tipos";

export type Accion = "aprobar" | "corregir" | "rechazar";

type Pedido = { accion: Accion; estudio: number; columna: Columna; celda: CeldaResumen };

const FALTANTES = ["No indica", "No indica (no significativo)", "No aplica"];

export const useDialogo = create<{ pedido: Pedido | null; abrir: (p: Pedido) => void; cerrar: () => void }>(
  (set) => ({ pedido: null, abrir: (pedido) => set({ pedido }), cerrar: () => set({ pedido: null }) }),
);

export function useRevisar(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (a: { accion: Accion; estudio: number; clave: string; motivo?: string; valor?: unknown; estadoDato?: string }) => {
      if (a.accion === "aprobar") return api.aprobar(pid, a.estudio, a.clave, a.motivo);
      if (a.accion === "rechazar") return api.rechazar(pid, a.estudio, a.clave, a.motivo ?? "");
      return api.corregir(pid, a.estudio, a.clave, a.valor, a.motivo ?? "", a.estadoDato);
    },
    onSuccess: (_, a) => {
      qc.invalidateQueries({ queryKey: ["filas", pid] });
      qc.invalidateQueries({ queryKey: ["celda", pid, a.estudio, a.clave] });
    },
  });
}

/** Aprobar directo cuando la celda no exige motivo; si lo exige, abre el diálogo. */
export function usePedirRevision(pid: string) {
  const revisar = useRevisar(pid);
  const abrir = useDialogo((s) => s.abrir);
  return (accion: Accion, estudio: number, columna: Columna, celda: CeldaResumen) => {
    if (accion === "aprobar" && !aprobarExigeMotivo(celda)) {
      revisar.mutate({ accion, estudio, clave: columna.clave });
      return;
    }
    abrir({ accion, estudio, columna, celda });
  };
}

const TITULOS: Record<Accion, string> = { aprobar: "Aprobar", corregir: "Corregir", rechazar: "Rechazar" };

function aValor(texto: string, columna: Columna): unknown {
  if (texto.trim() === "") return null;
  if (columna.es_numerica) {
    const n = Number(texto.replace(",", "."));
    return Number.isNaN(n) ? texto : n;
  }
  return texto;
}

export function DialogoRevision({ pid }: { pid: string }) {
  const { pedido, cerrar } = useDialogo();
  const revisar = useRevisar(pid);
  const [motivo, setMotivo] = useState("");
  const [valor, setValor] = useState("");
  const [estadoDato, setEstadoDato] = useState("");
  const primero = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!pedido) return;
    setMotivo("");
    setValor(mostrarValor(pedido.celda.valor, null));
    setEstadoDato(pedido.celda.estado_dato ?? "");
    revisar.reset();
    setTimeout(() => primero.current?.focus(), 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pedido]);

  if (!pedido) return null;
  const { accion, estudio, columna, celda } = pedido;
  const motivoObligatorio = accion !== "aprobar" || aprobarExigeMotivo(celda);
  const permitidos = columna.valores_permitidos;
  const listo = !motivoObligatorio || motivo.trim().length > 0;

  const enviar = () => {
    if (!listo) return;
    revisar.mutate(
      { accion, estudio, clave: columna.clave, motivo: motivo.trim() || undefined, valor: aValor(valor, columna), estadoDato: estadoDato || undefined },
      { onSuccess: cerrar },
    );
  };

  return (
    <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && cerrar()}>
      <div className="dialogo" role="dialog" aria-label={TITULOS[accion]} onKeyDown={(e) => e.key === "Escape" && cerrar()}>
        <h3>
          {TITULOS[accion]} · Estudio {estudio} · {columna.clave}
        </h3>
        <p className="tenue">
          Valor actual: <strong>{mostrarValor(celda.valor, celda.estado_dato) || "vacío"}</strong>
        </p>
        {accion === "corregir" && (
          <>
            <label>Valor nuevo</label>
            {permitidos ? (
              <select value={valor} onChange={(e) => setValor(e.target.value)}>
                <option value="">(vacío)</option>
                {permitidos.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            ) : (
              <input value={valor} onChange={(e) => setValor(e.target.value)} />
            )}
            {valor.trim() === "" && (
              <>
                <label>Código de faltante</label>
                <select value={estadoDato} onChange={(e) => setEstadoDato(e.target.value)}>
                  <option value="">(ninguno)</option>
                  {FALTANTES.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </>
            )}
          </>
        )}
        <label>Motivo{motivoObligatorio ? " (obligatorio)" : " (opcional)"}</label>
        <textarea
          ref={primero}
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.ctrlKey || e.metaKey) && enviar()}
          placeholder={accion === "aprobar" ? "Por qué se acepta aunque la cita no quedó verificada" : "Página y cita que lo justifican"}
        />
        {revisar.error && <p className="error">{(revisar.error as Error).message}</p>}
        <div className="botones">
          <button onClick={cerrar}>Cancelar</button>
          <button className={`primario ${accion}`} disabled={!listo || revisar.isPending} onClick={enviar}>
            {TITULOS[accion]}
          </button>
        </div>
      </div>
    </div>
  );
}

// «Configuración › Nube» (ADR 0009, sección 7): destino, qué se sube, cuándo y estado de la sincronización.
// El token solo se escribe: el servidor nunca lo devuelve (va al Administrador de credenciales de Windows).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../api";
import type { AjustesNube, OpcionesNube, ResultadoProbar } from "../tipos";

const QUE_SE_SUBE: [keyof OpcionesNube, string][] = [
  ["pdf", "PDF de los artículos"],
  ["documento", "Documento estructurado"],
  ["matriz", "Matriz y evidencias"],
  ["historial", "Historial de revisiones"],
  ["extraccion", "Extracción completa"],
  ["crudo", "Crudo de MinerU"],
  ["excel", "Excel base"],
];

const MOTIVO: Record<string, string> = {
  arranque: "arranque",
  evento: "cambio",
  temporizador: "reconciliación",
  manual: "manual",
  reintento: "reintento",
};

function bytes(n: number): string {
  return n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : n > 1000 ? `${Math.round(n / 1000)} kB` : `${n} B`;
}

export function PanelNube({ pid, onCerrar }: { pid: string; onCerrar: () => void }) {
  const qc = useQueryClient();
  const ajustes = useQuery({ queryKey: ["sync-ajustes", pid], queryFn: () => api.nube.ajustes(pid) });
  const estado = useQuery({ queryKey: ["sync-estado", pid], queryFn: () => api.nube.estado(pid), refetchInterval: 2000 });
  const corridas = useQuery({ queryKey: ["sync-corridas", pid], queryFn: () => api.nube.corridas(pid), refetchInterval: 4000 });

  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [opciones, setOpciones] = useState<OpcionesNube | null>(null);
  const [automatico, setAutomatico] = useState(true);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "mal"; texto: string } | null>(null);
  const [prueba, setPrueba] = useState<ResultadoProbar | null>(null);

  // Solo la primera vez: una recarga posterior no debe pisar lo que la persona ya escribió.
  const iniciado = useRef(false);
  useEffect(() => {
    if (!ajustes.data || iniciado.current) return;
    iniciado.current = true;
    setUrl(ajustes.data.url);
    setOpciones(ajustes.data.opciones);
    setAutomatico(ajustes.data.automatico);
  }, [ajustes.data]);

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ["sync-ajustes", pid] });
    qc.invalidateQueries({ queryKey: ["sync-estado", pid] });
    qc.invalidateQueries({ queryKey: ["sync-corridas", pid] });
  };
  const fallo = (e: unknown) => setAviso({ tipo: "mal", texto: (e as Error).message });

  const guardar = useMutation({
    mutationFn: (extra: Partial<AjustesNube> = {}) =>
      api.nube.guardar(pid, { url, ...(token ? { token } : {}), automatico, opciones: opciones ?? undefined, ...extra }),
    onSuccess: () => {
      setToken("");
      iniciado.current = false;
      setAviso({ tipo: "ok", texto: "Ajustes guardados" });
      refrescar();
    },
    onError: fallo,
  });
  const probar = useMutation({
    mutationFn: async () => {
      await api.nube.guardar(pid, { url, ...(token ? { token } : {}) });
      setToken("");
      return api.nube.probar(pid);
    },
    onSuccess: (r) => {
      setPrueba(r);
      refrescar();
    },
    onError: fallo,
  });
  const ahora = useMutation({ mutationFn: () => api.nube.ahora(pid), onSuccess: refrescar, onError: fallo });
  const reenviar = useMutation({
    mutationFn: () => api.nube.reenviar(pid),
    onSuccess: () => {
      setAviso({ tipo: "ok", texto: "Reenviando todo: tomará unos minutos" });
      refrescar();
    },
    onError: fallo,
  });
  const verificar = useMutation({
    mutationFn: () => api.nube.verificar(pid),
    onSuccess: (r) => setAviso({ tipo: r.ok ? "ok" : "mal", texto: r.detalle }),
    onError: fallo,
  });

  const e = estado.data;
  const pausado = ajustes.data?.pausado ?? false;
  const dirty = !!ajustes.data && (url !== ajustes.data.url || !!token);

  return createPortal(
    <div className="velo" onMouseDown={(ev) => ev.target === ev.currentTarget && onCerrar()}>
      <div className="dialogo panel-nube" role="dialog" aria-label="Configuración de la nube">
        <div className="panel-nube-cabeza">
          <h3>Configuración › Nube</h3>
          <button className="sin-borde" onClick={onCerrar} aria-label="Cerrar">
            ✕
          </button>
        </div>

        <h4>1. Destino</h4>
        <label>
          URL de la nube
          <input value={url} onChange={(ev) => setUrl(ev.target.value)} placeholder="https://su-nube.onrender.com" spellCheck={false} />
        </label>
        <label>
          Token de sincronización
          <input
            type="password"
            value={token}
            onChange={(ev) => setToken(ev.target.value)}
            placeholder={ajustes.data?.token_guardado ? "Guardado en el Administrador de credenciales (escriba para cambiarlo)" : "Péguelo aquí"}
            autoComplete="off"
          />
        </label>
        <div className="botones fila">
          <button onClick={() => probar.mutate()} disabled={probar.isPending || !url}>
            {probar.isPending ? "Probando…" : "Probar conexión"}
          </button>
          <button onClick={() => guardar.mutate({})} disabled={guardar.isPending || !dirty}>
            Guardar
          </button>
          {ajustes.data?.url && (
            <a className="enlace" href={ajustes.data.url} target="_blank" rel="noreferrer">
              Abrir visor ↗
            </a>
          )}
        </div>
        {prueba && (
          <ul className="pasos-prueba">
            {prueba.pasos.map((p) => (
              <li key={p.nombre} className={p.ok ? "ok" : "mal"}>
                {p.ok ? "✔" : "✖"} <strong>{p.nombre}</strong>
                {p.detalle && <span className="tenue"> — {p.detalle}</span>}
              </li>
            ))}
          </ul>
        )}

        <h4>2. Qué se sube</h4>
        <div className="opciones-nube">
          {QUE_SE_SUBE.map(([k, nombre]) => (
            <label key={k} className="casilla">
              <input
                type="checkbox"
                checked={opciones?.[k] ?? true}
                onChange={(ev) => setOpciones((o) => ({ ...(o as OpcionesNube), [k]: ev.target.checked }))}
              />
              {nombre}
            </label>
          ))}
        </div>

        <h4>3. Cuándo</h4>
        <div className="botones fila">
          <label className="casilla">
            <input type="checkbox" checked={automatico} onChange={(ev) => setAutomatico(ev.target.checked)} />
            Automático (agrupa cambios {ajustes.data?.agrupar_s ?? 5} s · reconcilia cada {Math.round((ajustes.data?.reconciliar_s ?? 600) / 60)} min)
          </label>
          <button onClick={() => guardar.mutate({ pausado: !pausado })}>{pausado ? "Reanudar" : "Pausar"}</button>
          <button className="primario" onClick={() => guardar.mutate({})} disabled={guardar.isPending}>
            Guardar opciones
          </button>
        </div>

        <h4>4. Estado</h4>
        <p className={`estado-sync ${e?.estado ?? ""}`}>
          {e
            ? e.estado === "subiendo"
              ? `Subiendo ${e.hechos} de ${e.total || "…"}`
              : e.detalle || {
                  sincronizado: `Sincronizado${e.hace_s !== null ? ` hace ${e.hace_s} s` : ""}${e.revision ? ` · revisión ${e.revision}` : ""}`,
                  sin_configurar: "Sin configurar",
                  pausado: "En pausa",
                  sin_conexion: "Sin conexión",
                  error: "Error",
                  subiendo: "",
                }[e.estado]
            : "…"}
        </p>
        <div className="botones fila">
          <button className="primario" onClick={() => ahora.mutate()} disabled={ahora.isPending || e?.estado === "subiendo"}>
            Sincronizar ahora
          </button>
          <button onClick={() => verificar.mutate()} disabled={verificar.isPending}>
            Verificar integridad
          </button>
          <button
            onClick={() => {
              if (window.confirm("Reenviar todo vuelve a subir el proyecto completo y toma el control de la nube. ¿Continuar?"))
                reenviar.mutate();
            }}
            disabled={reenviar.isPending}
          >
            Reenviar todo
          </button>
        </div>
        {aviso && (
          <p className={`aviso-nube ${aviso.tipo}`} role="status" onClick={() => setAviso(null)}>
            {aviso.texto}
          </p>
        )}
        <table className="tabla-corridas">
          <thead>
            <tr>
              <th>Inicio</th>
              <th>Motivo</th>
              <th>Estado</th>
              <th>Sobres</th>
              <th>Archivos</th>
              <th>Rev.</th>
            </tr>
          </thead>
          <tbody>
            {(corridas.data ?? []).slice(0, 8).map((c) => (
              <tr key={c.id} className={c.estado} title={c.detalle}>
                <td>{new Date(c.iniciada_en).toLocaleTimeString("es")}</td>
                <td>{MOTIVO[c.motivo] ?? c.motivo}</td>
                <td>{c.estado === "ok" ? "✔ ok" : c.estado === "sin_conexion" ? "⚠ sin conexión" : c.estado === "en_curso" ? "↻" : "✖ error"}</td>
                <td>{c.sobres + c.eliminados}</td>
                <td>
                  {c.archivos ? `${c.archivos} (${bytes(c.bytes_enviados)})` : 0}
                </td>
                <td>{c.revision ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>,
    document.body,
  );
}

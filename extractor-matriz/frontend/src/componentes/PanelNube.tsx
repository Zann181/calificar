// «Configuración › Nube» (ADR 0009, sección 7): destino, qué se sube, cuándo y estado de la sincronización.
// El token solo se escribe: el servidor nunca lo devuelve (va al Administrador de credenciales de Windows).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../api";
import type { AjustesNube, OpcionesNube, PlanRestauracion, ResultadoProbar } from "../tipos";

const QUE_SE_SUBE: [keyof OpcionesNube, string][] = [
  ["pdf", "PDF de los artículos"],
  ["documento", "Documento estructurado"],
  ["matriz", "Matriz y evidencias"],
  ["historial", "Historial de revisiones"],
  ["extraccion", "Extracción completa"],
  ["crudo", "Crudo de MinerU"],
  ["excel", "Excel base"],
  ["busqueda", "Búsquedas de «Buscar» (también recibe las hechas en la web)"],
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

function SeccionRestaurar({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const [plan, setPlan] = useState<PlanRestauracion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const estado = useQuery({
    queryKey: ["sync-restaurar", pid],
    queryFn: () => api.nube.restaurarEstado(pid),
    refetchInterval: (q) => (q.state.data?.estado === "restaurando" ? 800 : false),
  });
  const ver = useMutation({
    mutationFn: () => api.nube.restaurarPlan(pid),
    onSuccess: (p) => {
      setPlan(p);
      setError(null);
    },
    onError: (e) => setError((e as Error).message),
  });
  const bajar = useMutation({
    mutationFn: (reemplazar: boolean) => api.nube.restaurar(pid, reemplazar),
    onSuccess: () => {
      setPlan(null);
      qc.invalidateQueries({ queryKey: ["sync-restaurar", pid] });
    },
    onError: (e) => setError((e as Error).message),
  });
  // Al terminar, lo que se ve en pantalla vuelve a pedirse.
  const e = estado.data;
  useEffect(() => {
    if (e?.estado === "ok") qc.invalidateQueries({ predicate: (q) => !String(q.queryKey[0]).startsWith("sync-") });
  }, [e?.estado, qc]);
  const restaurando = e?.estado === "restaurando";
  return (
    <>
      <h4>5. Restaurar desde la nube</h4>
      <p className="tenue restaurar-plan">
        Baja a este equipo lo que la nube guarda del proyecto (por ejemplo, tras cambiar de computador). Nunca borra nada de
        lo que hay aquí; si hay diferencias, primero se las muestra.
      </p>
      <div className="botones fila">
        <button onClick={() => ver.mutate()} disabled={ver.isPending || restaurando}>
          {ver.isPending ? "Comparando…" : "Descargar proyecto desde la nube…"}
        </button>
      </div>
      {error && <p className="aviso-nube mal" onClick={() => setError(null)}>{error}</p>}
      {plan && !restaurando && (
        <div className="restaurar-plan">
          {plan.vacio ? (
            <p className="aviso-nube ok">Este equipo ya tiene todo lo que hay en la nube.</p>
          ) : (
            <>
              <p>
                Faltan <strong>{plan.faltan}</strong> elementos y <strong>{plan.archivos_faltan}</strong> archivos.
                {plan.hay_conflictos && (
                  <>
                    {" "}
                    Difieren <strong>{plan.distintos}</strong> elementos y <strong>{plan.archivos_distintos}</strong> archivos
                    {plan.ejemplos_distintos.length > 0 && <span className="tenue"> (p. ej. {plan.ejemplos_distintos.slice(0, 3).join(", ")})</span>}.
                  </>
                )}
                {plan.solo_locales > 0 && <> Hay {plan.solo_locales} elementos solo aquí: no se tocan.</>}
              </p>
              <div className="botones fila">
                {plan.hay_conflictos ? (
                  <button
                    className="primario"
                    onClick={() => {
                      if (
                        window.confirm(
                          `En lo que difiere (${plan.distintos} elementos), quedará la versión de la nube y se perderá lo de este equipo. ¿Continuar?`,
                        )
                      )
                        bajar.mutate(true);
                    }}
                  >
                    Bajar y reemplazar las diferencias
                  </button>
                ) : (
                  <button className="primario" onClick={() => bajar.mutate(false)}>
                    Bajar lo que falta
                  </button>
                )}
                <button onClick={() => setPlan(null)}>Cancelar</button>
              </div>
            </>
          )}
        </div>
      )}
      {restaurando && e && (
        <div className="restaurar-plan">
          <div className="barra-restauracion">
            <div style={{ width: `${e.total ? Math.round((100 * e.hechos) / e.total) : 5}%` }} />
          </div>
          <span className="tenue">
            {e.fase === "archivos" ? "Bajando archivos" : "Aplicando"} {e.hechos} de {e.total || "…"}
          </span>
        </div>
      )}
      {e?.estado === "ok" && e.resultado && (
        <p className="aviso-nube ok">
          Restaurado: {e.resultado.agregados} elementos y {e.resultado.archivos} archivos ({bytes(e.resultado.bytes)}).
        </p>
      )}
      {e?.estado === "error" && <p className="aviso-nube mal">{e.detalle}</p>}
    </>
  );
}

function SeccionLectores({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const [correo, setCorreo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const lista = useQuery({ queryKey: ["sync-lectores", pid], queryFn: () => api.nube.lectores(pid), retry: false });
  const cambiar = {
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["sync-lectores", pid] });
    },
    onError: (e: unknown) => setError((e as Error).message),
  };
  const alta = useMutation({
    mutationFn: () => api.nube.altaLector(pid, correo),
    ...cambiar,
    onSuccess: () => {
      setCorreo("");
      cambiar.onSuccess();
    },
  });
  const baja = useMutation({ mutationFn: (c: string) => api.nube.bajaLector(pid, c), ...cambiar });
  return (
    <>
      <h4>6. Lectores del visor</h4>
      <p className="tenue restaurar-plan">Quién puede entrar con su cuenta de Google. El cambio rige de inmediato.</p>
      {lista.error && <p className="aviso-nube mal">{(lista.error as Error).message}</p>}
      <ul className="lista-lectores">
        {(lista.data?.fijos ?? []).map((c) => (
          <li key={c}>
            <span>{c}</span>
            <span className="tenue" title="Se quita en la variable LECTORES_PERMITIDOS de la nube">fijo</span>
          </li>
        ))}
        {(lista.data?.agregados ?? []).map((l) => (
          <li key={l.correo}>
            <span>{l.correo}</span>
            <button className="sin-borde" onClick={() => baja.mutate(l.correo)} disabled={baja.isPending}>
              Quitar
            </button>
          </li>
        ))}
      </ul>
      <div className="fila-alta">
        <input
          type="email"
          value={correo}
          onChange={(ev) => setCorreo(ev.target.value)}
          placeholder="correo@ejemplo.com"
          onKeyDown={(ev) => ev.key === "Enter" && correo && alta.mutate()}
        />
        <button className="primario" onClick={() => alta.mutate()} disabled={!correo || alta.isPending}>
          Agregar
        </button>
      </div>
      {error && <p className="aviso-nube mal" onClick={() => setError(null)}>{error}</p>}
    </>
  );
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
        <SeccionRestaurar pid={pid} />
        <SeccionLectores pid={pid} />
      </div>
    </div>,
    document.body,
  );
}

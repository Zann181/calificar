// Registro en vivo: lo que hace el servidor y la CLI (carga, conversión, cada paso de la extracción), en orden.
// Consulta /registro cada 1,5 s trayendo solo lo nuevo. Se puede filtrar por nivel, origen y texto, pausar,
// limpiar, copiar, plegar y cambiar de alto arrastrando el borde superior.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { EventoRegistro } from "../tipos";

const MAX_EVENTOS = 1000;
const INTERVALO_MS = 1500;
const NIVELES = [
  ["TODO", "Todo"],
  ["INFO", "Info"],
  ["WARNING", "Avisos"],
  ["ERROR", "Errores"],
] as const;
type FiltroNivel = (typeof NIVELES)[number][0];
const ORDEN: Record<string, number> = { INFO: 0, WARNING: 1, ERROR: 2, CRITICAL: 2 };

function guardado<T>(clave: string, defecto: T): T {
  try {
    const v = localStorage.getItem(`extractor.registro.${clave}`);
    return v === null ? defecto : (JSON.parse(v) as T);
  } catch {
    return defecto;
  }
}
function guardar(clave: string, valor: unknown) {
  try {
    localStorage.setItem(`extractor.registro.${clave}`, JSON.stringify(valor));
  } catch {
    /* sin almacenamiento: la preferencia vale solo esta sesión */
  }
}

const hora = (t: string) => new Date(t).toLocaleTimeString("es", { hour12: false });

export function PanelRegistro() {
  const [eventos, setEventos] = useState<EventoRegistro[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pausado, setPausado] = useState(false);
  const [plegado, setPlegado] = useState(() => guardado("plegado", false));
  const [alto, setAlto] = useState(() => guardado("alto", 220));
  const [nivel, setNivel] = useState<FiltroNivel>(() => guardado("nivel", "TODO"));
  const [origen, setOrigen] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pegado, setPegado] = useState(true); // sigue el final salvo que la persona suba
  const siguiente = useRef<number | null>(null);
  const cuerpo = useRef<HTMLDivElement>(null);

  useEffect(() => guardar("plegado", plegado), [plegado]);
  useEffect(() => guardar("nivel", nivel), [nivel]);

  // Consulta periódica: encadenada con setTimeout para no apilar peticiones si el servidor tarda.
  useEffect(() => {
    if (pausado) return;
    let vivo = true;
    let temporizador: ReturnType<typeof setTimeout>;
    const traer = async () => {
      if (document.visibilityState === "visible") {
        try {
          const r = await api.registro(siguiente.current);
          if (!vivo) return;
          siguiente.current = r.siguiente;
          setError(null);
          if (r.eventos.length) setEventos((prev) => [...prev, ...r.eventos].slice(-MAX_EVENTOS));
        } catch (e) {
          if (vivo) setError((e as Error).message || "sin conexión con el servidor");
        }
      }
      if (vivo) temporizador = setTimeout(traer, INTERVALO_MS);
    };
    void traer();
    return () => {
      vivo = false;
      clearTimeout(temporizador);
    };
  }, [pausado]);

  const origenes = useMemo(() => [...new Set(eventos.map((e) => e.origen))].sort(), [eventos]);
  const visibles = useMemo(() => {
    const min = nivel === "TODO" ? 0 : ORDEN[nivel];
    const q = buscar.trim().toLowerCase();
    return eventos.filter(
      (e) => (ORDEN[e.nivel] ?? 0) >= min && (!origen || e.origen === origen) && (!q || e.mensaje.toLowerCase().includes(q)),
    );
  }, [eventos, nivel, origen, buscar]);
  const errores = useMemo(() => eventos.filter((e) => (ORDEN[e.nivel] ?? 0) >= 2).length, [eventos]);

  useEffect(() => {
    const el = cuerpo.current;
    if (el && pegado) el.scrollTop = el.scrollHeight;
  }, [visibles, pegado, plegado]);

  const alDesplazar = () => {
    const el = cuerpo.current;
    if (el) setPegado(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  };

  const arrastrar = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      const y0 = e.clientY;
      const a0 = alto;
      let ultimo = a0;
      const mover = (m: PointerEvent) => {
        ultimo = Math.min(Math.max(a0 + (y0 - m.clientY), 90), window.innerHeight * 0.8);
        setAlto(ultimo);
      };
      const soltar = () => {
        window.removeEventListener("pointermove", mover);
        window.removeEventListener("pointerup", soltar);
        guardar("alto", Math.round(ultimo));
      };
      window.addEventListener("pointermove", mover);
      window.addEventListener("pointerup", soltar);
    },
    [alto],
  );

  const copiar = () => {
    const texto = visibles.map((e) => `${hora(e.t)} ${e.nivel} [${e.origen}] ${e.mensaje}`).join("\n");
    void navigator.clipboard?.writeText(texto);
  };

  return (
    <section className={`registro ${plegado ? "plegado" : ""}`} style={plegado ? undefined : { height: alto }} aria-label="Registro de actividad">
      {!plegado && (
        <div
          className="registro-asa"
          onPointerDown={arrastrar}
          onDoubleClick={() => setAlto(220)}
          role="separator"
          aria-orientation="horizontal"
          aria-label="Alto del registro"
          title="Arrastre para cambiar el alto; doble clic: tamaño por defecto"
        />
      )}
      <header className="registro-barra">
        <button className="registro-titulo" onClick={() => setPlegado((p) => !p)} aria-expanded={!plegado} title={plegado ? "Mostrar registro" : "Plegar registro"}>
          <i className={`registro-pulso ${error ? "caido" : pausado ? "en-pausa" : ""}`} />
          Registro
          <span className="tenue"> · {eventos.length}</span>
          {errores > 0 && <span className="registro-errores">{errores} error{errores === 1 ? "" : "es"}</span>}
        </button>
        {!plegado && (
          <>
            <div className="registro-niveles" role="group" aria-label="Nivel">
              {NIVELES.map(([v, t]) => (
                <button key={v} className={nivel === v ? "activo" : ""} onClick={() => setNivel(v)}>
                  {t}
                </button>
              ))}
            </div>
            <select value={origen} onChange={(e) => setOrigen(e.target.value)} aria-label="Origen">
              <option value="">Todos los orígenes</option>
              {origenes.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <input type="search" placeholder="Buscar en el registro" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
            <span className="registro-acciones">
              <button onClick={() => setPausado((p) => !p)}>{pausado ? "Reanudar" : "Pausar"}</button>
              <button onClick={copiar} disabled={!visibles.length}>
                Copiar
              </button>
              <button onClick={() => setEventos([])} disabled={!eventos.length}>
                Limpiar
              </button>
            </span>
          </>
        )}
      </header>
      {!plegado && (
        <div className="registro-cuerpo" ref={cuerpo} onScroll={alDesplazar} role="log" aria-live="polite">
          {error && <p className="registro-linea ERROR">No se pudo leer el registro: {error}</p>}
          {!visibles.length && !error && (
            <p className="tenue registro-vacio">
              {eventos.length ? "Ningún evento coincide con el filtro." : "Sin actividad todavía. Aquí aparecerán la carga, la conversión y cada paso de la extracción."}
            </p>
          )}
          {visibles.map((e) => (
            <p key={e.id} className={`registro-linea ${e.nivel}`}>
              <time dateTime={e.t}>{hora(e.t)}</time>
              <b className="nivel">{e.nivel === "WARNING" ? "AVISO" : e.nivel}</b>
              <button className="origen" onClick={() => setOrigen(origen === e.origen ? "" : e.origen)} title="Filtrar por este origen">
                {e.origen}
              </button>
              <span className="mensaje">{e.mensaje}</span>
            </p>
          ))}
          {!pegado && (
            <button
              className="registro-abajo"
              onClick={() => {
                setPegado(true);
              }}
            >
              ↓ Ir al final
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// Sección «Extracción» de un artículo (ADR 0009, sección 6.4): solo lectura, en el equipo local y en la nube.
// Pestañas: Salida · Codificación ciega · Anclas · Hallazgos · Validador · Uso de tokens · Datos del equipo.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";

import { api } from "../api";
import { useNavegacion } from "../navegacion";
import type { AnclaExtraccion, ExtraccionCompleta } from "../tipos";

export const useFichaExtraccion = create<{
  articulo: { id: string; nombre: string } | null;
  abrir: (id: string, nombre: string) => void;
  cerrar: () => void;
}>((set) => ({
  articulo: null,
  abrir: (id, nombre) => set({ articulo: { id, nombre } }),
  cerrar: () => set({ articulo: null }),
}));

type Pestana = "salida" | "ciega" | "anclas" | "hallazgos" | "validador" | "uso" | "equipo";
const PESTANAS: [Pestana, string][] = [
  ["salida", "Salida"],
  ["ciega", "Codificación ciega"],
  ["anclas", "Anclas"],
  ["hallazgos", "Hallazgos"],
  ["validador", "Validador"],
  ["uso", "Uso de tokens"],
  ["equipo", "Datos del equipo"],
];

function valor(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v, null, 1);
  return String(v);
}

function Pares({ datos }: { datos: Record<string, unknown> }) {
  const claves = Object.keys(datos);
  if (!claves.length) return <p className="tenue">Sin datos.</p>;
  return (
    <table className="pares">
      <tbody>
        {claves.map((k) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{valor(datos[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Salida({ e }: { e: ExtraccionCompleta }) {
  if (!e.salida.length) return <p className="tenue">La extracción no produjo salida{e.error ? `: ${e.error}` : "."}</p>;
  return (
    <>
      {e.salida.map((item, i) => (
        <details key={i} open={e.salida.length === 1} className="bloque-salida">
          <summary>Estudio {String(item.fila?.["Estudio"] ?? i + 1)}</summary>
          <Pares datos={item.fila} />
          {item.trazabilidad && (
            <details>
              <summary>Trazabilidad (evidencias, decisión de inclusión, discrepancias)</summary>
              <pre>{JSON.stringify(item.trazabilidad, null, 2)}</pre>
            </details>
          )}
        </details>
      ))}
    </>
  );
}

function Ciega({ e }: { e: ExtraccionCompleta }) {
  if (!e.codificacion_ciega.length) return <p className="tenue">No hay codificación ciega (la extracción no llegó a ese paso).</p>;
  return (
    <>
      {e.codificacion_ciega.map((item, i) => (
        <details key={i} open={e.codificacion_ciega.length === 1} className="bloque-salida">
          <summary>Codificación {i + 1}</summary>
          <Pares datos={(item.fila as Record<string, unknown>) ?? item} />
        </details>
      ))}
    </>
  );
}

function Anclas({ e, ver }: { e: ExtraccionCompleta; ver: (a: AnclaExtraccion) => void }) {
  if (!e.anclas.length) return <p className="tenue">Sin anclas.</p>;
  return (
    <table className="tabla-ficha">
      <thead>
        <tr>
          <th>Estudio</th>
          <th>Columna</th>
          <th>#</th>
          <th>Nivel</th>
          <th>Similitud</th>
          <th>Pág.</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {e.anclas.map((a, i) => (
          <tr key={i} className={`nivel-${a.nivel}`} title={a.nota || undefined}>
            <td>{a.estudio}</td>
            <td>{a.columna}</td>
            <td>{a.indice_evidencia + 1}</td>
            <td>
              <span className={`chip-nivel ${a.nivel}`}>{a.nivel.replace(/_/g, " ").toLowerCase()}</span>
              {a.leido_de_figura && <span className="tenue"> · figura</span>}
            </td>
            <td>{a.similitud}</td>
            <td>{a.pagina ?? "—"}</td>
            <td>{a.pagina ? <button className="sin-borde" onClick={() => ver(a)}>Ver en el PDF</button> : null}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Hallazgos({ e }: { e: ExtraccionCompleta }) {
  if (!e.hallazgos.length) return <p className="tenue">Sin hallazgos.</p>;
  return (
    <ul className="hallazgos">
      {e.hallazgos.map((h, i) => (
        <li key={i} className={`veredicto-${h.veredicto}`}>
          <header>
            <strong>{h.columna}</strong>
            {h.estudio !== null && <span className="tenue"> · Estudio {h.estudio}</span>}
            <span className={`chip-nivel ${h.veredicto}`}>{h.veredicto.replace(/_/g, " ").toLowerCase()}</span>
            <span className="tenue"> · {h.auditor.replace(/_/g, " ").toLowerCase()} · {h.estado.toLowerCase()}</span>
          </header>
          <p>{h.detalle}</p>
          {h.evidencia_propuesta ? <pre>{valor(h.evidencia_propuesta)}</pre> : null}
          {h.resolucion && <p className="tenue">Resolución: {h.resolucion}</p>}
        </li>
      ))}
    </ul>
  );
}

function Validador({ e }: { e: ExtraccionCompleta }) {
  return (
    <>
      <p>
        Iteraciones del validador: <strong>{e.iteraciones_validador}</strong>
      </p>
      <h5>Errores ({e.errores_validador.length})</h5>
      {e.errores_validador.length ? (
        <ul>{e.errores_validador.map((x, i) => <li key={i}>{x}</li>)}</ul>
      ) : (
        <p className="tenue">Ninguno.</p>
      )}
      <h5>Avisos ({e.avisos_validador.length})</h5>
      {e.avisos_validador.length ? (
        <ul>{e.avisos_validador.map((x, i) => <li key={i}>{x}</li>)}</ul>
      ) : (
        <p className="tenue">Ninguno.</p>
      )}
    </>
  );
}

function Uso({ e }: { e: ExtraccionCompleta }) {
  const roles = Object.entries(e.uso_tokens);
  if (!roles.length) return <p className="tenue">Sin registro de uso.</p>;
  return (
    <table className="tabla-ficha">
      <thead>
        <tr>
          <th>Rol</th>
          <th>Llamadas</th>
          <th>Entrada</th>
          <th>Caché esc.</th>
          <th>Caché lect.</th>
          <th>Salida</th>
          <th>Segundos</th>
          <th>USD</th>
          <th>Modelos</th>
        </tr>
      </thead>
      <tbody>
        {roles.map(([rol, r]) => (
          <tr key={rol}>
            <td>{rol}</td>
            <td>{r.llamadas}</td>
            <td>{r.entrada.toLocaleString("es")}</td>
            <td>{r.cache_escritura.toLocaleString("es")}</td>
            <td>{r.cache_lectura.toLocaleString("es")}</td>
            <td>{r.salida.toLocaleString("es")}</td>
            <td>{r.segundos}</td>
            <td>{r.costo_usd.toFixed(2)}</td>
            <td>{r.modelos ? Object.entries(r.modelos).map(([m, n]) => `${m} ×${n}`).join(", ") : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Cuerpo({ pid, id, nombre, cerrar }: { pid: string; id: string; nombre: string; cerrar: () => void }) {
  const { ir } = useNavegacion();
  const [pestana, setPestana] = useState<Pestana>("salida");
  const lista = useQuery({ queryKey: ["extracciones", pid, id], queryFn: () => api.extracciones(pid, id) });
  const [elegida, setElegida] = useState<string | null>(null);
  useEffect(() => {
    if (!lista.data?.length) return;
    // La última completada; si no hay, la más reciente.
    setElegida((lista.data.find((x) => x.estado === "COMPLETADA") ?? lista.data[0]).id);
  }, [lista.data]);
  const completa = useQuery({
    queryKey: ["extraccion", pid, elegida],
    queryFn: () => api.extraccion(pid, elegida!),
    enabled: !!elegida,
  });
  const e = completa.data;

  const verEnPdf = (a: AnclaExtraccion) => {
    ir({
      articuloId: id,
      visor: { articuloId: id, pagina: a.pagina ?? 1, zoom: 1, rect: a.rect, etiqueta: a.columna },
    });
    cerrar();
  };

  return (
    <>
      <div className="panel-nube-cabeza">
        <h3>Extracción · {nombre}</h3>
        <button className="sin-borde" onClick={cerrar} aria-label="Cerrar">
          ✕
        </button>
      </div>
      {lista.isLoading && <p className="tenue">Cargando…</p>}
      {lista.data && lista.data.length === 0 && <p className="tenue">Este artículo no tiene extracciones.</p>}
      {lista.data && lista.data.length > 1 && (
        <label>
          Corrida
          <select value={elegida ?? ""} onChange={(ev) => setElegida(ev.target.value)}>
            {lista.data.map((x) => (
              <option key={x.id} value={x.id}>
                {new Date(x.iniciada_en).toLocaleString("es")} · {x.estado.toLowerCase()}
              </option>
            ))}
          </select>
        </label>
      )}
      {e && (
        <>
          <p className="resumen-ext">
            <span className={`chip-nivel ${e.estado}`}>{e.estado.toLowerCase()}</span>
            <span> Estudios {e.estudios.join(", ")}</span>
            {e.acuerdo !== null && <span> · acuerdo {e.acuerdo.toFixed(2)}</span>}
            <span> · {e.anclas.length} anclas · {e.hallazgos.length} hallazgos ({e.hallazgos_pendientes} pendientes)</span>
            <span> · {e.costo_usd.toFixed(2)} USD</span>
            {e.error && <span className="error"> · {e.paso_fallido}: {e.error}</span>}
          </p>
          <nav className="pestanas-ficha" role="tablist">
            {PESTANAS.map(([k, nombre]) => (
              <button key={k} role="tab" aria-selected={pestana === k} className={pestana === k ? "activo" : ""} onClick={() => setPestana(k)}>
                {nombre}
              </button>
            ))}
          </nav>
          <div className="cuerpo-ficha">
            {pestana === "salida" && <Salida e={e} />}
            {pestana === "ciega" && <Ciega e={e} />}
            {pestana === "anclas" && <Anclas e={e} ver={verEnPdf} />}
            {pestana === "hallazgos" && <Hallazgos e={e} />}
            {pestana === "validador" && <Validador e={e} />}
            {pestana === "uso" && <Uso e={e} />}
            {pestana === "equipo" && <Pares datos={e.datos_del_equipo} />}
          </div>
        </>
      )}
    </>
  );
}

export function FichaExtraccion({ pid }: { pid: string }) {
  const { articulo, cerrar } = useFichaExtraccion();
  if (!articulo) return null;
  return createPortal(
    <div className="velo" onMouseDown={(ev) => ev.target === ev.currentTarget && cerrar()}>
      <div className="dialogo ficha-extraccion" role="dialog" aria-label="Extracción del artículo">
        <Cuerpo pid={pid} id={articulo.id} nombre={articulo.nombre} cerrar={cerrar} />
      </div>
    </div>,
    document.body,
  );
}

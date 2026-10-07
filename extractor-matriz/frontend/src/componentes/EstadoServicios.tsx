// Monitor de la cabecera: servicios (servidor, despachador, MinerU, Claude) y avance de la extracción.
// Dos modos que se recuerdan: «barra» (los cuatro indicadores y la dona) o «icono» (solo la dona). En ambos, un
// clic en la dona despliega el detalle: en qué paso va cada extracción y el estado de cada servicio.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { enCurso, formatoTiempo, PASOS_VISIBLES, porcentajeVisible, useAvance } from "../avance";
import type { AvanceExtraccion, Articulo, PendienteDeExtraccion } from "../tipos";
import { Dona } from "./Dona";

const ETIQUETA: Record<string, string> = {
  servidor: "Servidor",
  despachador: "Despachador",
  mineru: "MinerU",
  claude: "Claude",
  pdftotext: "pdftotext",
};
const ORDEN_SALUD = { ok: 0, aviso: 1, error: 2 } as const;
type Salud = keyof typeof ORDEN_SALUD;
type Modo = "barra" | "icono";

function modoGuardado(): Modo {
  try {
    return localStorage.getItem("extractor.monitor.modo") === "icono" ? "icono" : "barra";
  } catch {
    return "barra";
  }
}

function Pasos({ a, ahora }: { a: AvanceExtraccion; ahora: number }) {
  const pct = porcentajeVisible(a, ahora);
  return (
    <ol className="pasos">
      {PASOS_VISIBLES.map((p) => {
        const hecho = a.terminada_en ? !a.fallida : a.progreso >= p.hasta;
        const actual = !a.terminada_en && a.paso === p.clave;
        const clase = a.fallida && actual ? "falla" : hecho ? "hecho" : actual ? "actual" : "";
        return (
          <li key={p.clave} className={clase}>
            <span className="paso-marca">{a.fallida && actual ? "✕" : hecho ? "✓" : actual ? "●" : "○"}</span>
            <span className="paso-texto">{p.texto}</span>
            {actual && !a.fallida && <b className="paso-pct">{pct} %</b>}
          </li>
        );
      })}
    </ol>
  );
}

function Pendiente({ p, nombre, ahora }: { p: PendienteDeExtraccion; nombre: string; ahora: number }) {
  const texto =
    p.fase === "convirtiendo"
      ? `Convirtiendo con MinerU · ${formatoTiempo((ahora - Date.parse(p.desde)) / 1000)}`
      : p.fase === "esperando_mineru"
        ? "Esperando a MinerU (no responde)"
        : `En cola · puesto ${p.posicion}`;
  return (
    <div className="proceso">
      <b className="recortar" title={nombre}>
        {nombre}
      </b>
      <span className="tenue">{texto}</span>
    </div>
  );
}

export function EstadoServicios({ pid }: { pid: string }) {
  const estado = useQuery({ queryKey: ["estado"], queryFn: api.estado, refetchInterval: 10_000, retry: false });
  const articulos = useQuery({ queryKey: ["articulos", pid], queryFn: () => api.articulos(pid), enabled: !!pid });
  const { porArticulo, enCola, ahora } = useAvance(pid);
  const [modo, setModo] = useState<Modo>(modoGuardado);
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem("extractor.monitor.modo", modo);
    } catch {
      /* solo esta sesión */
    }
  }, [modo]);

  // Al lanzar una extracción desde la lista, el detalle se despliega para ver el avance.
  useEffect(() => {
    const abrir = () => setAbierto(true);
    window.addEventListener("extractor:abrir-monitor", abrir);
    return () => window.removeEventListener("extractor:abrir-monitor", abrir);
  }, []);

  // Cierra el detalle al hacer clic fuera o con Esc.
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => !caja.current?.contains(e.target as Node) && setAbierto(false);
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && setAbierto(false);
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  const nombres = new Map((articulos.data?.articulos ?? []).map((a: Articulo) => [a.id, a.nombre_archivo]));
  const nombre = (id: string) => nombres.get(id) ?? "Artículo";
  const sinConexion = estado.isError;
  const servicios = estado.data?.componentes ?? [];
  const salud: Salud = sinConexion
    ? "error"
    : servicios.reduce<Salud>((peor, c) => (ORDEN_SALUD[c.estado] > ORDEN_SALUD[peor] ? c.estado : peor), "ok");

  const activas = [...porArticulo.values()].filter(enCurso);
  const recientes = [...porArticulo.values()].filter((a) => !enCurso(a));
  const pendientes = [...enCola.values()];
  const pct = activas.length
    ? Math.round(activas.reduce((s, a) => s + porcentajeVisible(a, ahora), 0) / activas.length)
    : null;
  const trabajando = activas.length > 0 || pendientes.length > 0;
  const resumen = trabajando
    ? activas.length
      ? `Extrayendo ${activas.length} artículo(s): ${pct} %`
      : "Preparando extracciones (conversión o cola)"
    : salud === "ok"
      ? "Todo en orden, sin extracciones en curso"
      : "Hay servicios con avisos o errores";

  return (
    <div className="monitor" ref={caja}>
      {modo === "barra" && (
        <div className="servicios" role="status" aria-label="Estado de los servicios">
          {sinConexion ? (
            <span
              className="servicio error"
              title={`No se pudo consultar el estado: ${(estado.error as Error).message}`}
            >
              <i className="punto-servicio" />
              Sin conexión con el servidor
            </span>
          ) : (
            servicios.map((c) => (
              <span key={c.id} className={`servicio ${c.estado}`} title={c.detalle}>
                <i className="punto-servicio" />
                {ETIQUETA[c.id] ?? c.nombre}
                <span className="sr-solo">
                  {" "}
                  {c.estado === "ok" ? "activo" : c.estado === "aviso" ? "con aviso" : "con error"}
                </span>
              </span>
            ))
          )}
        </div>
      )}
      <button
        className={`monitor-dona ${abierto ? "abierto" : ""}`}
        onClick={() => setAbierto((a) => !a)}
        aria-expanded={abierto}
        aria-label={`Monitor: ${resumen}`}
        title={resumen}
      >
        <Dona pct={pct} trabajando={trabajando} salud={salud} />
      </button>
      {modo === "barra" && (
        <button
          className="monitor-plegar"
          onClick={() => setModo("icono")}
          title="Retraer a un ícono"
          aria-label="Retraer el monitor a un ícono"
        >
          ›
        </button>
      )}

      {abierto && (
        <div className="monitor-panel" role="dialog" aria-label="Detalle del monitor">
          <header>
            <strong>Proceso de extracción</strong>
            <span className="tenue">{resumen}</span>
          </header>
          {!trabajando && recientes.length === 0 && (
            <p className="tenue">Sin extracciones en curso. Marca artículos y pulsa «Extraer seleccionados».</p>
          )}
          {pendientes.map((p) => (
            <Pendiente key={p.articulo_id} p={p} nombre={nombre(p.articulo_id)} ahora={ahora} />
          ))}
          {[...activas, ...recientes].map((a) => (
            <div key={a.extraccion_id} className="proceso">
              <div className="proceso-cabeza">
                <b className="recortar" title={nombre(a.articulo_id)}>
                  {nombre(a.articulo_id)}
                </b>
                <span className="tenue">
                  {a.fallida
                    ? "Falló"
                    : a.terminada_en
                      ? `Completada · ${a.costo_usd.toLocaleString("es", { minimumFractionDigits: 2 })} USD`
                      : formatoTiempo((ahora - Date.parse(a.iniciada_en)) / 1000)}
                </span>
              </div>
              <Pasos a={a} ahora={ahora} />
              {a.fallida && a.error && <p className="error">{a.error}</p>}
            </div>
          ))}
          <h4>Servicios</h4>
          <ul className="servicios-detalle">
            {servicios.map((c) => (
              <li key={c.id} className={c.estado}>
                <i className="punto-servicio" />
                <b>{ETIQUETA[c.id] ?? c.nombre}</b>
                <span className="tenue">{c.detalle}</span>
              </li>
            ))}
            {sinConexion && (
              <li className="error">
                <i className="punto-servicio" />
                <b>Servidor</b>
                <span className="tenue">Sin conexión</span>
              </li>
            )}
          </ul>
          <footer>
            <button onClick={() => setModo(modo === "barra" ? "icono" : "barra")}>
              {modo === "barra" ? "Mostrar solo el ícono" : "Mostrar la barra de servicios"}
            </button>
          </footer>
        </div>
      )}
    </div>
  );
}

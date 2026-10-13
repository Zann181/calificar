// Monitor de la cabecera: servicios (servidor, despachador, MinerU, Claude), uso de la cuenta de Claude en la
// ventana de 5 horas (y cuándo se restablece) y avance de la extracción.
// Dos modos que se recuerdan: «barra» (consumo, servicios que fallan y la dona) o «icono» (consumo y la dona). La
// barra de consumo se ve siempre; los servicios en orden solo aparecen en el detalle. En ambos modos, un clic en
// la dona despliega el detalle: en qué paso va cada extracción y el estado de cada servicio.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { enCurso, formatoTiempo, PASOS_VISIBLES, porcentajeVisible, useAvance } from "../avance";
import type { AvanceExtraccion, Articulo, CuentaClaude, PendienteDeExtraccion, VentanaCuenta } from "../tipos";
import { Dona } from "./Dona";

const ETIQUETA: Record<string, string> = {
  servidor: "Servidor",
  despachador: "Despachador",
  mineru: "MinerU",
  claude: "Claude",
};
const ORDEN_SALUD = { ok: 0, aviso: 1, error: 2 } as const;
type Salud = keyof typeof ORDEN_SALUD;
type Modo = "barra" | "icono";

function modoGuardado(): Modo {
  try {
    return sessionStorage.getItem("extractor.monitor.modo") === "icono" ? "icono" : "barra";
  } catch {
    return "barra";
  }
}

/** «2 h 15 min», «8 min» o «menos de 1 min» hasta `iso`. */
function faltaPara(iso: string, ahora: number): string {
  const min = Math.ceil((Date.parse(iso) - ahora) / 60_000);
  if (min <= 0) return "ya";
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es", { hour: "numeric", minute: "2-digit" });

function nivelCuenta(v: VentanaCuenta): "ok" | "aviso" | "error" {
  return v.usado >= 90 ? "error" : v.usado >= 70 ? "aviso" : "ok";
}

function textoVentana(v: VentanaCuenta, ahora: number): string {
  const quedan = Math.max(0, Math.round(100 - v.usado));
  const reinicio = v.restablece ? ` · se restablece en ${faltaPara(v.restablece, ahora)} (${hora(v.restablece)})` : "";
  return `${Math.round(v.usado)} % usado, quedan ${quedan} %${reinicio}`;
}

/** Píldora de la cabecera: lo que queda de la ventana de 5 horas y cuándo se restablece. */
function PildoraCuenta({ cuenta, ahora }: { cuenta: CuentaClaude; ahora: number }) {
  const v = cuenta.cinco_horas;
  if (!v) return null;
  const quedan = Math.max(0, Math.round(100 - v.usado));
  const nivel = cuenta.bloqueada ? "error" : nivelCuenta(v);
  return (
    <span
      className={`servicio limite-cuenta ${nivel}`}
      title={`Cuenta de Claude, ventana de 5 horas: ${textoVentana(v, ahora)}`}
    >
      <span className="limite-pista" aria-hidden="true">
        <span className="limite-relleno" style={{ width: `${Math.min(100, v.usado)}%` }} />
      </span>
      5 h: quedan {quedan} %{v.restablece ? ` · ${faltaPara(v.restablece, ahora)}` : ""}
    </span>
  );
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
        : p.fase === "pausada"
          ? `En pausa: sin cupo de Claude · reintenta ${p.reanuda ? hora(p.reanuda) : "más tarde"}`
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
      sessionStorage.setItem("extractor.monitor.modo", modo);
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
      <div className="servicios" role="status" aria-label="Estado de los servicios">
        {estado.data?.cuenta && <PildoraCuenta cuenta={estado.data.cuenta} ahora={ahora} />}
        {modo === "barra" &&
          (sinConexion ? (
            <span
              className="servicio error"
              title={`No se pudo consultar el estado: ${(estado.error as Error).message}`}
            >
              <i className="punto-servicio" />
              Sin conexión con el servidor
            </span>
          ) : (
            servicios
              .filter((c) => c.estado !== "ok")
              .map((c) => (
                <span key={c.id} className={`servicio ${c.estado}`} title={c.detalle}>
                  <i className="punto-servicio" />
                  {ETIQUETA[c.id] ?? c.nombre}
                  <span className="sr-solo"> {c.estado === "aviso" ? "con aviso" : "con error"}</span>
                </span>
              ))
          ))}
      </div>
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
                      ? "Completada"
                      : formatoTiempo((ahora - Date.parse(a.iniciada_en)) / 1000)}
                </span>
              </div>
              <Pasos a={a} ahora={ahora} />
              {a.fallida && a.error && <p className="error">{a.error}</p>}
            </div>
          ))}
          {estado.data?.cuenta && (
            <>
              <h4>Cuenta de Claude</h4>
              <ul className="servicios-detalle">
                {estado.data.cuenta.cinco_horas && (
                  <li className={estado.data.cuenta.bloqueada ? "error" : nivelCuenta(estado.data.cuenta.cinco_horas)}>
                    <i className="punto-servicio" />
                    <b>Ventana de 5 horas</b>
                    <span className="tenue">{textoVentana(estado.data.cuenta.cinco_horas, ahora)}</span>
                  </li>
                )}
                {estado.data.cuenta.siete_dias && (
                  <li className={nivelCuenta(estado.data.cuenta.siete_dias)}>
                    <i className="punto-servicio" />
                    <b>Semana (7 días)</b>
                    <span className="tenue">{textoVentana(estado.data.cuenta.siete_dias, ahora)}</span>
                  </li>
                )}
              </ul>
              <p className="tenue">
                {estado.data.cuenta.bloqueada
                  ? "Límite alcanzado: las extracciones fallarán hasta que se restablezca."
                  : `Dato de las ${hora(estado.data.cuenta.actualizado)}; se actualiza con cada llamada al modelo.`}
              </p>
            </>
          )}
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
              {modo === "barra" ? "Ocultar los servicios con falla" : "Mostrar los servicios con falla"}
            </button>
          </footer>
        </div>
      )}
    </div>
  );
}

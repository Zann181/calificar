// Visor PDF (sección 9.4): renderiza la página, dibuja el rectángulo del ancla y resalta las palabras citadas.
import * as pdfjs from "pdfjs-dist";
import "pdfjs-dist/web/pdf_viewer.css";
import trabajador from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { Icono } from "./Icono";
import { useNavegacion, type VistaVisor } from "../navegacion";
import { norm } from "../normalizar";
import { PanelRazonamiento } from "./PanelRazonamiento";

pdfjs.GlobalWorkerOptions.workerSrc = trabajador;

const cache = new Map<string, Promise<pdfjs.PDFDocumentProxy>>();
function abrir(url: string) {
  if (!cache.has(url)) cache.set(url, pdfjs.getDocument({ url, withCredentials: true }).promise);
  return cache.get(url)!;
}

/** Marca los fragmentos de la capa de texto que cubren norm(cita). Devuelve cuántos marcó. */
function resaltar(capa: HTMLElement, cita: string): number {
  const fragmentos = Array.from(capa.querySelectorAll<HTMLElement>("span[role=presentation], span:not(:has(span))"));
  const objetivo = norm(cita);
  if (!objetivo || !fragmentos.length) return 0;
  let texto = "";
  const rangos: { inicio: number; fin: number; el: HTMLElement }[] = [];
  for (const el of fragmentos) {
    const t = norm(el.textContent ?? "");
    if (!t) continue;
    if (texto) texto += " ";
    rangos.push({ inicio: texto.length, fin: texto.length + t.length, el });
    texto += t;
  }
  let pos = texto.indexOf(objetivo);
  let fin = pos + objetivo.length;
  if (pos < 0) {
    // Palabras cortadas con guion al final de línea ("well- being"): se buscan sin el corte,
    // como hace norm() con "-\n", y se traducen los índices al texto original.
    let unido = "";
    const mapa: number[] = [];
    for (let i = 0; i < texto.length; i++) {
      if (texto[i] === "-" && texto[i + 1] === " ") {
        i++;
        continue;
      }
      unido += texto[i];
      mapa.push(i);
    }
    const p = unido.indexOf(objetivo);
    if (p < 0) return 0;
    pos = mapa[p];
    fin = mapa[p + objetivo.length - 1] + 1;
  }
  let marcados = 0;
  for (const r of rangos) {
    if (r.fin > pos && r.inicio < fin) {
      r.el.classList.add("resaltado");
      marcados++;
    }
  }
  return marcados;
}

type Props = { pid: string; visor: VistaVisor; nombre?: string; onCerrar?: () => void };

export function VisorPdf({ pid, visor, nombre, onCerrar }: Props) {
  const ir = useNavegacion((s) => s.ir);
  const actual = useNavegacion((s) => s.actual);
  const contenedor = useRef<HTMLDivElement>(null);
  const lienzo = useRef<HTMLCanvasElement>(null);
  const capa = useRef<HTMLDivElement>(null);
  const marco = useRef<HTMLDivElement>(null);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState<"cargando" | "listo" | "error">("cargando");
  const [aviso, setAviso] = useState("");
  const [rectPx, setRectPx] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const url = api.urlPdf(pid, visor.articuloId);

  useEffect(() => {
    let cancelado = false;
    let tareaRender: pdfjs.RenderTask | null = null;
    let tareaTexto: pdfjs.TextLayer | null = null;
    setEstado("cargando");
    setAviso("");
    (async () => {
      try {
        const doc = await abrir(url);
        if (cancelado) return;
        setTotal(doc.numPages);
        const pagina = await doc.getPage(Math.min(Math.max(1, visor.pagina), doc.numPages));
        const ancho = (contenedor.current?.clientWidth ?? 800) - 32;
        const base = pagina.getViewport({ scale: 1 });
        const escala = (ancho / base.width) * visor.zoom;
        const vista = pagina.getViewport({ scale: escala });
        const c = lienzo.current!;
        const ratio = window.devicePixelRatio || 1;
        c.width = Math.floor(vista.width * ratio);
        c.height = Math.floor(vista.height * ratio);
        c.style.width = `${vista.width}px`;
        c.style.height = `${vista.height}px`;
        marco.current!.style.width = `${vista.width}px`;
        marco.current!.style.height = `${vista.height}px`;
        tareaRender = pagina.render({
          canvasContext: c.getContext("2d")!,
          viewport: vista,
          transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
        });
        await tareaRender.promise;
        if (cancelado) return;

        const t = capa.current!;
        t.replaceChildren();
        t.style.setProperty("--scale-factor", String(escala));
        tareaTexto = new pdfjs.TextLayer({ textContentSource: pagina.streamTextContent(), container: t, viewport: vista });
        await tareaTexto.render();
        if (cancelado) return;

        // Rectángulo del ancla en puntos PDF, origen arriba a la izquierda (ADR 0001): x_px = x_pt × escala.
        if (visor.rect) {
          const [x0, y0, x1, y1] = visor.rect;
          const r = { left: x0 * escala, top: y0 * escala, width: (x1 - x0) * escala, height: (y1 - y0) * escala };
          setRectPx(r);
          contenedor.current?.scrollTo({ top: Math.max(0, r.top - 120), behavior: "smooth" });
        } else setRectPx(null);
        if (visor.cita && resaltar(t, visor.cita) === 0) {
          setAviso("La cita no se encontró literal en la capa de texto de esta página: revise el rectángulo.");
        }
        setEstado("listo");
      } catch (e) {
        if ((e as Error).name === "RenderingCancelledException") return;
        if (!cancelado) {
          setEstado("error");
          setAviso((e as Error).message);
        }
      }
    })();
    return () => {
      cancelado = true;
      tareaRender?.cancel();
      tareaTexto?.cancel();
    };
  }, [url, visor.pagina, visor.zoom, visor.rect, visor.cita]);

  // Ctrl + rueda sobre el PDF acerca o aleja sin zoom del navegador; doble clic en el porcentaje vuelve a «ajustar al ancho».
  const zoomActual = useRef(visor.zoom);
  zoomActual.current = visor.zoom;
  const accion = useRef({ actual, ir, visor });
  accion.current = { actual, ir, visor };
  useEffect(() => {
    const el = contenedor.current;
    if (!el) return;
    const alRueda = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const z = Math.min(4, Math.max(0.25, Math.round((zoomActual.current + (e.deltaY < 0 ? 0.1 : -0.1)) * 100) / 100));
      const { actual, ir, visor } = accion.current;
      ir({ ...actual, visor: { ...visor, zoom: z } });
    };
    el.addEventListener("wheel", alRueda, { passive: false });
    return () => el.removeEventListener("wheel", alRueda);
  }, []);

  const cambiar = (cambio: Partial<VistaVisor>) =>
    ir({ ...actual, visor: { ...visor, rect: null, cita: undefined, etiqueta: undefined, ...cambio } });

  return (
    <section className="visor">
      <div className="barra">
        <strong className="recortar" title={nombre}>
          {nombre ?? "PDF"}
        </strong>
        <button disabled={visor.pagina <= 1} onClick={() => cambiar({ pagina: visor.pagina - 1 })} aria-label="Página anterior">
          <Icono nombre="atras" tam={16} />
        </button>
        <span>
          p. {visor.pagina} / {total || "…"}
        </span>
        <button disabled={!!total && visor.pagina >= total} onClick={() => cambiar({ pagina: visor.pagina + 1 })} aria-label="Página siguiente">
          <Icono nombre="adelante" tam={16} />
        </button>
        <button onClick={() => ir({ ...actual, visor: { ...visor, zoom: Math.max(0.25, visor.zoom - 0.25) } })} aria-label="Alejar">
          <Icono nombre="menos" tam={16} />
        </button>
        <span
          onDoubleClick={() => ir({ ...actual, visor: { ...visor, zoom: 1 } })}
          title="Doble clic: ajustar al ancho"
        >
          {Math.round(visor.zoom * 100)} %
        </span>
        <button onClick={() => ir({ ...actual, visor: { ...visor, zoom: Math.min(4, visor.zoom + 0.25) } })} aria-label="Acercar">
          <Icono nombre="mas" tam={16} />
        </button>
        {onCerrar && (
          <button onClick={onCerrar} aria-label="Plegar visor">
            <Icono nombre="cerrar" tam={16} />
          </button>
        )}
      </div>
      {visor.etiqueta && <div className="franja">{visor.etiqueta}</div>}
      {aviso && <div className={`franja ${estado === "error" ? "error" : "aviso"}`}>{aviso}</div>}
      <div className="lienzo" ref={contenedor}>
        <div className="pagina" ref={marco}>
          <canvas ref={lienzo} />
          <div className="textLayer" ref={capa} />
          {rectPx && <div className="ancla" style={rectPx} />}
        </div>
        {estado === "cargando" && <div className="cargando">Cargando página…</div>}
      </div>
      <PanelRazonamiento pid={pid} />
    </section>
  );
}

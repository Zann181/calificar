// Grilla de la matriz (sección 9.3). Las columnas salen de GET /normas/columnas, nunca escritas a mano.
import { useQueryClient } from "@tanstack/react-query";
import type {
  CellClassParams,
  CellKeyDownEvent,
  CellMouseOutEvent,
  CellMouseOverEvent,
  ColDef,
  GridApi,
  IRowNode,
  ValueGetterParams,
} from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { type Color, colorDe, LEYENDA, mostrarValor, NEON, revisada } from "../colores";
import { useNavegacion } from "../navegacion";
import { usePedirRevision } from "../revision";
import type { Columna, Fila } from "../tipos";
import { etiquetaEvidencia, FichaEvidencia } from "./FichaEvidencia";

const FIJAS = new Set(["Documento", "Estudio", "Cita"]);

function useOscuro() {
  const consulta = window.matchMedia("(prefers-color-scheme: dark)");
  const [oscuro, setOscuro] = useState(consulta.matches);
  useEffect(() => {
    const f = (e: MediaQueryListEvent) => setOscuro(e.matches);
    consulta.addEventListener("change", f);
    return () => consulta.removeEventListener("change", f);
  }, [consulta]);
  return oscuro;
}
const ANCHAS: Record<string, number> = { Title: 320, Author: 220, "Aim of study": 300, Conclusion: 300 };

type Ficha = { estudio: number; clave: string; x: number; y: number; fija: boolean };

type Props = { pid: string; columnas: Columna[]; filas: Fila[]; articulosMarcados: Set<string> };

export function Grilla({ pid, columnas, filas, articulosMarcados }: Props) {
  const qc = useQueryClient();
  const { actual, ir } = useNavegacion();
  const pedir = usePedirRevision(pid);
  const [api_, setApi] = useState<GridApi<Fila> | null>(null);
  const [soloExtraidas, setSoloExtraidas] = useState(false);
  const [marcas, setMarcas] = useState<Set<Color>>(new Set()); // filtros de la leyenda: resaltan y filtran
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const oscuro = useOscuro();
  const [zoom, setZoomCrudo] = useState(() => {
    try {
      const v = Number(localStorage.getItem("extractor.zoom.tabla"));
      return v >= 0.6 && v <= 2 ? v : 1;
    } catch {
      return 1;
    }
  });
  const setZoom = useCallback((f: (z: number) => number) => {
    setZoomCrudo((z) => {
      const n = Math.round(Math.min(2, Math.max(0.6, f(z))) * 100) / 100;
      try {
        localStorage.setItem("extractor.zoom.tabla", String(n));
      } catch {
        /* solo esta sesión */
      }
      return n;
    });
  }, []);
  const temporizador = useRef<number>();
  const dentroDeFicha = useRef(false);

  const porClave = useMemo(() => new Map(columnas.map((c) => [c.clave, c])), [columnas]);
  const base = useMemo(() => filas.filter((f) => !soloExtraidas || f.origen === "EXTRAIDA"), [filas, soloExtraidas]);
  // Cuántas celdas hay de cada marca (se muestra en la leyenda).
  const conteo = useMemo(() => {
    const m = new Map<Color, number>();
    for (const f of base) for (const c of Object.values(f.celdas)) m.set(colorDe(c), (m.get(colorDe(c)) ?? 0) + 1);
    return m;
  }, [base]);
  // Con marcas activas solo quedan las filas que tienen alguna celda marcada.
  const visibles = useMemo(
    () => (marcas.size === 0 ? base : base.filter((f) => Object.values(f.celdas).some((c) => marcas.has(colorDe(c))))),
    [base, marcas],
  );
  const columnasMarcadas = useMemo(() => {
    const s = new Set<string>();
    if (marcas.size === 0) return s;
    for (const f of visibles) for (const [k, c] of Object.entries(f.celdas)) if (marcas.has(colorDe(c))) s.add(k);
    return s;
  }, [visibles, marcas]);
  const alternarMarca = (color: Color) =>
    setMarcas((m) => {
      const n = new Set(m);
      if (n.has(color)) n.delete(color);
      else n.add(color);
      return n;
    });

  const columnDefs = useMemo<ColDef<Fila>[]>(
    () =>
      columnas.map((c) => ({
        colId: c.clave,
        headerName: `${c.letra} · ${c.encabezado_excel.replace(/\s+/g, " ")}`,
        headerTooltip: c.nota_encabezado,
        pinned: FIJAS.has(c.clave) ? "left" : undefined,
        width: FIJAS.has(c.clave) ? (c.clave === "Cita" ? 170 : 92) : (ANCHAS[c.clave] ?? 150),
        valueGetter: (p: ValueGetterParams<Fila>) => {
          const celda = p.data?.celdas[c.clave];
          return celda ? mostrarValor(celda.valor, celda.estado_dato) : "";
        },
        cellClass: (p: CellClassParams<Fila>) => {
          const color = colorDe(p.data?.celdas[c.clave]);
          if (marcas.size === 0) return `celda-${color}`;
          return marcas.has(color) ? `celda-${color} neon neon-${color}` : `celda-${color} atenuada`;
        },
        headerClass: columnasMarcadas.has(c.clave) ? "cabecera-neon" : undefined,
        sortable: false,
      })),
    [columnas, marcas, columnasMarcadas],
  );

  // Las clases de celda dependen de las marcas: se vuelven a calcular al cambiarlas.
  useEffect(() => {
    api_?.refreshCells({ force: true });
    api_?.refreshHeader();
    // Al activar un filtro, la tabla se desplaza a la primera columna con celdas marcadas.
    const primera = columnas.find((c) => !FIJAS.has(c.clave) && columnasMarcadas.has(c.clave));
    if (primera) api_?.ensureColumnVisible(primera.clave, "start");
  }, [api_, marcas, columnasMarcadas, columnas]);

  // Artículos con el chulito marcado en la lista: sus filas quedan marcadas en la tabla y se desmarcan al quitarlo.
  const filasMarcadas = useMemo(
    () =>
      articulosMarcados.size === 0
        ? 0
        : visibles.filter((f) => f.articulo_id !== null && articulosMarcados.has(f.articulo_id)).length,
    [visibles, articulosMarcados],
  );
  const previos = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!api_) return;
    api_.redrawRows();
    // La tabla se desplaza a la primera fila del artículo que se acaba de marcar.
    const nuevos = [...articulosMarcados].filter((id) => !previos.current.has(id));
    previos.current = new Set(articulosMarcados);
    if (nuevos.length === 0 || actual.estudio) return; // con un Estudio elegido manda el salto a su celda
    let primera: IRowNode<Fila> | null = null;
    api_.forEachNodeAfterFilterAndSort((n) => {
      if (!primera && n.data?.articulo_id && nuevos.includes(n.data.articulo_id)) primera = n;
    });
    if (primera) api_.ensureNodeVisible(primera, "middle");
  }, [api_, articulosMarcados, visibles, actual.estudio]);

  // Al volver o saltar a un Estudio, la grilla lo muestra y enfoca la celda.
  useEffect(() => {
    if (!api_ || !actual.estudio) return;
    const nodo = api_.getRowNode(String(actual.estudio));
    if (!nodo || nodo.rowIndex === null) return;
    api_.ensureIndexVisible(nodo.rowIndex, "middle");
    if (actual.columna) {
      api_.ensureColumnVisible(actual.columna);
      api_.setFocusedCell(nodo.rowIndex, actual.columna);
    }
  }, [api_, actual.estudio, actual.columna, visibles]);

  const cerrarFicha = useCallback(() => {
    window.clearTimeout(temporizador.current);
    setFicha(null);
  }, []);

  const alPasar = (e: CellMouseOverEvent<Fila>) => {
    if (ficha?.fija || !e.data || !e.colDef.colId) return;
    const raton = e.event as MouseEvent | null;
    const { estudio } = e.data;
    const clave = e.colDef.colId;
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(
      () => setFicha({ estudio, clave, x: (raton?.clientX ?? 200) + 12, y: (raton?.clientY ?? 200) + 12, fija: false }),
      300,
    );
  };

  const alSalir = (_: CellMouseOutEvent<Fila>) => {
    window.clearTimeout(temporizador.current);
    if (ficha && !ficha.fija) temporizador.current = window.setTimeout(() => !dentroDeFicha.current && setFicha(null), 250);
  };

  // Clic en una celda con evidencia: el visor abre la página y resalta la cita (sección 1).
  const alHacerClic = async (fila: Fila, clave: string) => {
    const celda = fila.celdas[clave];
    if (!celda || celda.evidencias === 0 || !fila.articulo_id) {
      // Sin cita que mostrar: se conserva la página abierta, pero sin el resaltado de otra celda; si no había PDF,
      // se abre el artículo para que el panel «Por qué este valor» tenga dónde mostrarse junto a él.
      const visor = fila.articulo_id
        ? actual.visor?.articuloId === fila.articulo_id
          ? { ...actual.visor, rect: null, cita: undefined, etiqueta: undefined }
          : { articuloId: fila.articulo_id, pagina: 1, zoom: actual.visor?.zoom ?? 1 }
        : undefined;
      ir({ estudio: fila.estudio, columna: clave, articuloId: fila.articulo_id ?? undefined, visor });
      return;
    }
    const d = await qc.fetchQuery({ queryKey: ["celda", pid, fila.estudio, clave], queryFn: () => api.celda(pid, fila.estudio, clave) });
    const e = d.evidencias[0];
    ir({
      estudio: fila.estudio,
      columna: clave,
      articuloId: fila.articulo_id,
      visor: {
        articuloId: fila.articulo_id,
        pagina: e.ancla?.pagina ?? e.pagina_pdf,
        zoom: actual.visor?.zoom ?? 1,
        rect: e.ancla?.rect,
        cita: e.cita_textual,
        etiqueta: etiquetaEvidencia(fila.estudio, clave, e),
      },
    });
  };

  // N y P: siguiente y anterior celda pendiente (filas extraídas, sin revisar), en orden de lectura.
  const pendientes = useMemo(
    () =>
      visibles.flatMap((f, i) =>
        f.origen !== "EXTRAIDA"
          ? []
          : columnas.filter((c) => !revisada(f.celdas[c.clave]) && colorDe(f.celdas[c.clave]) !== "gris").map((c) => ({ i, clave: c.clave })),
      ),
    [visibles, columnas],
  );

  const alTeclear = (e: CellKeyDownEvent<Fila>) => {
    const tecla = (e.event as KeyboardEvent | null)?.key?.toLowerCase();
    const fila = e.data;
    const clave = e.colDef.colId;
    if (!tecla || !fila || !clave) return;
    const columna = porClave.get(clave)!;
    const celda = fila.celdas[clave];
    if (tecla === "enter") setFicha({ estudio: fila.estudio, clave, x: 0, y: 0, fija: true });
    else if (tecla === "escape") cerrarFicha();
    else if (tecla === "a" && celda) pedir("aprobar", fila.estudio, columna, celda);
    else if (tecla === "e" && celda) pedir("corregir", fila.estudio, columna, celda);
    else if (tecla === "r" && celda) pedir("rechazar", fila.estudio, columna, celda);
    else if ((tecla === "n" || tecla === "p") && pendientes.length && api_ && e.rowIndex !== null) {
      const orden = (i: number, k: string) => i * 1000 + columnas.findIndex((c) => c.clave === k);
      const aqui = orden(e.rowIndex, clave);
      const destino =
        tecla === "n"
          ? (pendientes.find((x) => orden(x.i, x.clave) > aqui) ?? pendientes[0])
          : ([...pendientes].reverse().find((x) => orden(x.i, x.clave) < aqui) ?? pendientes[pendientes.length - 1]);
      api_.ensureIndexVisible(destino.i);
      api_.ensureColumnVisible(destino.clave);
      api_.setFocusedCell(destino.i, destino.clave);
    }
  };

  // Ctrl + rueda sobre la tabla, o Ctrl + «+» / «−» / «0», agranda y achica filas y letra.
  const alRueda = (e: React.WheelEvent) => {
    if (!e.ctrlKey) return;
    setZoom((z) => z + (e.deltaY < 0 ? 0.1 : -0.1));
  };

  const filaFicha = ficha && filas.find((f) => f.estudio === ficha.estudio);
  const extraidas = filas.filter((f) => f.origen === "EXTRAIDA").length;

  return (
    <section className="grilla">
      <div className="barra">
        <label className="interruptor">
          <input type="checkbox" checked={soloExtraidas} onChange={(e) => setSoloExtraidas(e.target.checked)} />
          Solo extraídas ({extraidas})
        </label>
        <span className="tenue">
          {visibles.length} filas · {columnas.length} columnas
        </span>
        {articulosMarcados.size > 0 && (
          <span className={`articulo-abierto ${filasMarcadas ? "" : "sin-filas"}`} role="status">
            {filasMarcadas
              ? `${articulosMarcados.size} artículo${articulosMarcados.size === 1 ? "" : "s"} marcado${articulosMarcados.size === 1 ? "" : "s"} · ${filasMarcadas} fila${filasMarcadas === 1 ? "" : "s"}`
              : `${articulosMarcados.size} marcado${articulosMarcados.size === 1 ? "" : "s"}: aún sin filas extraídas`}
          </span>
        )}
        <div className="zoom-tabla" role="group" aria-label="Zoom de la tabla">
          <button onClick={() => setZoom((z) => z - 0.1)} disabled={zoom <= 0.6} aria-label="Achicar tabla" title="Achicar (Ctrl + rueda)">
            −
          </button>
          <output onDoubleClick={() => setZoom(() => 1)} title="Doble clic: 100 %">
            {Math.round(zoom * 100)} %
          </output>
          <button onClick={() => setZoom((z) => z + 0.1)} disabled={zoom >= 2} aria-label="Agrandar tabla" title="Agrandar (Ctrl + rueda)">
            +
          </button>
        </div>
        <div className="leyenda" role="group" aria-label="Filtrar y resaltar por marca">
          {LEYENDA.map(([color, texto]) => (
            <button
              key={color}
              type="button"
              className={`filtro-marca ${marcas.has(color) ? "activa" : ""}`}
              style={{ "--neon": NEON[color] } as React.CSSProperties}
              aria-pressed={marcas.has(color)}
              onClick={() => alternarMarca(color)}
              title={`${marcas.has(color) ? "Quitar" : "Resaltar y filtrar"}: ${texto}`}
            >
              <i className={`punto ${color}`} />
              {texto}
              <b className="cuenta-marca">{conteo.get(color) ?? 0}</b>
            </button>
          ))}
          {marcas.size > 0 && (
            <button type="button" className="filtro-marca limpiar" onClick={() => setMarcas(new Set())}>
              Quitar filtros
            </button>
          )}
        </div>
      </div>
      <div
        className={`${oscuro ? "ag-theme-quartz-dark" : "ag-theme-quartz"} tabla`}
        style={{ "--ag-font-size": `${12.5 * zoom}px` } as React.CSSProperties}
        onWheel={alRueda}
      >
        <AgGridReact<Fila>
          rowData={visibles}
          columnDefs={columnDefs}
          getRowId={(p) => String(p.data.estudio)}
          onGridReady={(e) => setApi(e.api)}
          onCellMouseOver={alPasar}
          onCellMouseOut={alSalir}
          onCellClicked={(e) => e.data && e.colDef.colId && alHacerClic(e.data, e.colDef.colId)}
          onCellKeyDown={alTeclear}
          rowClassRules={{
            "fila-extraida": (p) => p.data?.origen === "EXTRAIDA",
            "fila-actual": (p) => p.data?.estudio === actual.estudio,
            "fila-del-articulo": (p) => !!p.data?.articulo_id && articulosMarcados.has(p.data.articulo_id),
          }}
          tooltipShowDelay={300}
          tooltipInteraction
          headerHeight={Math.round(44 * zoom)}
          rowHeight={Math.round(32 * zoom)}
          suppressDragLeaveHidesColumns
        />
      </div>
      {ficha && filaFicha && filaFicha.celdas[ficha.clave] && (
        <FichaEvidencia
          key={`${ficha.estudio}-${ficha.clave}`}
          pid={pid}
          estudio={ficha.estudio}
          columna={porClave.get(ficha.clave)!}
          resumen={filaFicha.celdas[ficha.clave]}
          posicion={ficha.fija ? undefined : { x: ficha.x, y: ficha.y }}
          fija={ficha.fija}
          onCerrar={cerrarFicha}
          onEntrar={() => {
            dentroDeFicha.current = true;
            window.clearTimeout(temporizador.current);
          }}
          onSalir={() => {
            dentroDeFicha.current = false;
            if (!ficha.fija) setFicha(null);
          }}
        />
      )}
    </section>
  );
}

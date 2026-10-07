// Grilla de la matriz (sección 9.3). Las columnas salen de GET /normas/columnas, nunca escritas a mano.
import { useQueryClient } from "@tanstack/react-query";
import type {
  CellClassParams,
  CellKeyDownEvent,
  CellMouseOutEvent,
  CellMouseOverEvent,
  ColDef,
  GridApi,
  ValueGetterParams,
} from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { colorDe, LEYENDA, mostrarValor, revisada } from "../colores";
import { useNavegacion } from "../navegacion";
import { usePedirRevision } from "../revision";
import type { Columna, Fila } from "../tipos";
import { etiquetaEvidencia, FichaEvidencia } from "./FichaEvidencia";
import { Icono } from "./Icono";

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

type Props = { pid: string; columnas: Columna[]; filas: Fila[]; documento?: number; onQuitarFiltro: () => void };

export function Grilla({ pid, columnas, filas, documento, onQuitarFiltro }: Props) {
  const qc = useQueryClient();
  const { actual, ir } = useNavegacion();
  const pedir = usePedirRevision(pid);
  const [api_, setApi] = useState<GridApi<Fila> | null>(null);
  const [soloExtraidas, setSoloExtraidas] = useState(false);
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const oscuro = useOscuro();
  const temporizador = useRef<number>();
  const dentroDeFicha = useRef(false);

  const porClave = useMemo(() => new Map(columnas.map((c) => [c.clave, c])), [columnas]);
  const visibles = useMemo(
    () =>
      filas.filter((f) => (!soloExtraidas || f.origen === "EXTRAIDA") && (documento === undefined || f.documento === documento)),
    [filas, soloExtraidas, documento],
  );

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
        cellClass: (p: CellClassParams<Fila>) => `celda-${colorDe(p.data?.celdas[c.clave])}`,
        sortable: false,
      })),
    [columnas],
  );

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
      ir({ estudio: fila.estudio, columna: clave, articuloId: fila.articulo_id ?? undefined, visor: actual.visor });
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

  const filaFicha = ficha && filas.find((f) => f.estudio === ficha.estudio);
  const extraidas = filas.filter((f) => f.origen === "EXTRAIDA").length;

  return (
    <section className="grilla">
      <div className="barra">
        <label className="interruptor">
          <input type="checkbox" checked={soloExtraidas} onChange={(e) => setSoloExtraidas(e.target.checked)} />
          Solo extraídas ({extraidas})
        </label>
        {documento !== undefined && (
          <span className="filtro">
            Documento {documento}
            <button onClick={onQuitarFiltro} aria-label="Quitar filtro">
              <Icono nombre="cerrar" tam={12} grosor={2.4} />
            </button>
          </span>
        )}
        <span className="tenue">
          {visibles.length} filas · {columnas.length} columnas
        </span>
        <div className="leyenda">
          {LEYENDA.map(([color, texto]) => (
            <span key={color} title={texto}>
              <i className={`punto ${color}`} />
              {texto}
            </span>
          ))}
        </div>
      </div>
      <div className={`${oscuro ? "ag-theme-quartz-dark" : "ag-theme-quartz"} tabla`}>
        <AgGridReact<Fila>
          rowData={visibles}
          columnDefs={columnDefs}
          getRowId={(p) => String(p.data.estudio)}
          onGridReady={(e) => setApi(e.api)}
          onCellMouseOver={alPasar}
          onCellMouseOut={alSalir}
          onCellClicked={(e) => e.data && e.colDef.colId && alHacerClic(e.data, e.colDef.colId)}
          onCellKeyDown={alTeclear}
          rowClassRules={{ "fila-extraida": (p) => p.data?.origen === "EXTRAIDA", "fila-actual": (p) => p.data?.estudio === actual.estudio }}
          tooltipShowDelay={300}
          tooltipInteraction
          headerHeight={44}
          rowHeight={32}
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

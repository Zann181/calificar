// Panel de artículos (sección 9.2): lista con casillas, estados, contadores, filtros, carga y extracción.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { api } from "../api";
import { useNavegacion } from "../navegacion";
import { Icono } from "./Icono";
import type { Articulo, EstadoArticulo, ResultadoCarga } from "../tipos";

const EXTRAIBLES: EstadoArticulo[] = ["LISTO", "HEREDADO", "ERROR", "POR_REVISAR"];
// Promedio medido en F0 (ADR 0002) con los cuatro roles: Kumar, 552 310 tokens de entrada y 2,64 USD.
const TOKENS_POR_ARTICULO = 552_310;
const USD_POR_ARTICULO = 2.64;

const NOMBRE_ESTADO: Record<EstadoArticulo, string> = {
  HEREDADO: "Heredado",
  NUEVO: "Nuevo",
  CONVIRTIENDO: "Convirtiendo",
  LISTO: "Listo",
  EN_COLA: "En cola",
  EXTRAYENDO: "Extrayendo",
  AUDITANDO: "Auditando",
  POR_REVISAR: "Por revisar",
  APROBADO: "Aprobado",
  ERROR: "Error",
  EXCLUIDO: "Excluido",
};

type Props = {
  pid: string;
  articulos: Articulo[];
  contadores: Record<string, number>;
  documentoDe: Map<string, number>;
  conFilas: Set<string>;
  onAbrir?: () => void;
};

export function PanelArticulos({ pid, articulos, contadores, documentoDe, conFilas, onAbrir }: Props) {
  const qc = useQueryClient();
  const { actual, ir } = useNavegacion();
  const [filtro, setFiltro] = useState<EstadoArticulo | "">("");
  const [busqueda, setBusqueda] = useState("");
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [resultado, setResultado] = useState<ResultadoCarga[] | null>(null);
  const [dialogo, setDialogo] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  const visibles = useMemo(
    () =>
      articulos
        .filter((a) => (!filtro || a.estado === filtro) && a.nombre_archivo.toLowerCase().includes(busqueda.toLowerCase()))
        .sort((a, b) => a.nombre_archivo.localeCompare(b.nombre_archivo, "es", { numeric: true })),
    [articulos, filtro, busqueda],
  );

  const cargar = useMutation({
    mutationFn: (archivos: File[]) => api.cargar(pid, archivos),
    onSuccess: (r) => {
      setResultado(r);
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
    },
  });

  const seleccionados = articulos.filter((a) => marcados.has(a.id));
  const extraibles = seleccionados.filter((a) => EXTRAIBLES.includes(a.estado));
  const reextraer = extraibles.filter((a) => a.estado === "POR_REVISAR");
  const todosVisiblesMarcados = visibles.length > 0 && visibles.every((a) => marcados.has(a.id));

  const alternar = (id: string) =>
    setMarcados((m) => {
      const n = new Set(m);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const abrir = (a: Articulo) => {
    ir({
      articuloId: a.id,
      estudio: undefined,
      columna: undefined,
      visor: a.paginas ? { articuloId: a.id, pagina: 1, zoom: 1 } : undefined,
    });
    if (a.paginas) onAbrir?.();
  };

  return (
    <section
      className="articulos"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const pdfs = Array.from(e.dataTransfer.files).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
        if (pdfs.length) cargar.mutate(pdfs);
      }}
    >
      <div className="barra">
        <strong className="titulo-seccion">Artículos</strong>
        <span className="tenue">{articulos.length}</span>
        <button className="primario" onClick={() => archivo.current?.click()} disabled={cargar.isPending} title="Añadir PDF (también puede arrastrarlos aquí)">
          <Icono nombre="subir" tam={16} />
          {cargar.isPending ? "Cargando…" : "Añadir PDF"}
        </button>
        <input
          ref={archivo}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) => e.target.files && cargar.mutate(Array.from(e.target.files))}
        />
      </div>
      <label className="buscar">
        <Icono nombre="buscar" tam={16} />
        <input placeholder="Buscar" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} aria-label="Buscar por nombre" />
      </label>
      <div className="contadores">
        <button className={filtro === "" ? "activo" : ""} onClick={() => setFiltro("")}>
          Todos {articulos.length}
        </button>
        {Object.entries(contadores).filter(([, n]) => n > 0).map(([estado, n]) => (
          <button key={estado} className={`estado-${estado} ${filtro === estado ? "activo" : ""}`} onClick={() => setFiltro(estado as EstadoArticulo)}>
            {NOMBRE_ESTADO[estado as EstadoArticulo] ?? estado} {n}
          </button>
        ))}
      </div>
      {resultado && (
        <div className="aviso-carga" onClick={() => setResultado(null)}>
          {resultado.map((r) => (
            <div key={r.nombre_archivo}>
              {r.error ? "✗" : r.duplicado ? "⧉" : "✓"} {r.nombre_archivo}
              {r.duplicado && <span className="tenue"> · duplicado de {r.duplicado_de}</span>}
              {r.error && <span className="error"> · {r.error}</span>}
            </div>
          ))}
        </div>
      )}
      <div className="acciones">
        <label>
          <input
            type="checkbox"
            checked={todosVisiblesMarcados}
            onChange={() =>
              setMarcados((m) => {
                const n = new Set(m);
                visibles.forEach((a) => (todosVisiblesMarcados ? n.delete(a.id) : n.add(a.id)));
                return n;
              })
            }
          />
          Seleccionar todo
        </label>
        <button disabled={extraibles.length === 0} onClick={() => setDialogo(true)}>
          Extraer seleccionados {extraibles.length ? `(${extraibles.length})` : ""}
        </button>
      </div>
      <ul className="lista">
        {visibles.map((a) => (
          <li key={a.id} className={actual.articuloId === a.id ? "actual" : ""}>
            <input type="checkbox" checked={marcados.has(a.id)} onChange={() => alternar(a.id)} aria-label={`Seleccionar ${a.nombre_archivo}`} />
            <button className="nombre" onClick={() => abrir(a)} title={a.error?.mensaje ?? a.nombre_archivo}>
              <span className="recortar">{a.nombre_archivo}</span>
              <span className="tenue">
                {documentoDe.has(a.id) ? `Doc. ${documentoDe.get(a.id)}` : "Doc. —"}
                {a.paginas ? ` · ${a.paginas} p.` : ""}
                {conFilas.has(a.id) ? " · con filas extraídas" : ""}
              </span>
            </button>
            <span className={`estado estado-${a.estado}`}>{NOMBRE_ESTADO[a.estado]}</span>
          </li>
        ))}
      </ul>
      {dialogo && (
        <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && setDialogo(false)}>
          <div className="dialogo">
            <h3>Extraer {extraibles.length} artículo(s)</h3>
            <p>
              Estimación con el promedio medido en F0: unos {Math.round((extraibles.length * TOKENS_POR_ARTICULO) / 1000).toLocaleString("es")} mil
              tokens de entrada y {(extraibles.length * USD_POR_ARTICULO).toLocaleString("es", { maximumFractionDigits: 2 })} USD equivalentes.
            </p>
            {reextraer.length > 0 && <p className="aviso">{reextraer.length} ya tienen filas por revisar: se reemplazarán.</p>}
            {seleccionados.length > extraibles.length && (
              <p className="tenue">{seleccionados.length - extraibles.length} seleccionados no se pueden extraer todavía (deben estar convertidos).</p>
            )}
            <p className="aviso">La cola de extracción llega en F3; este diálogo muestra cómo funcionará.</p>
            <div className="botones">
              <button onClick={() => setDialogo(false)}>Cerrar</button>
              <button className="primario" disabled title="Disponible en F3">
                Encolar
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

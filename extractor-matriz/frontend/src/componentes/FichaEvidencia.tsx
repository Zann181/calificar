// Ficha de evidencia (sección 9.3): valor, tipo, citas con su ancla, inferencia, hallazgos, historial y acciones.
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { colorDe, mostrarValor } from "../colores";
import { Icono } from "./Icono";
import { useNavegacion } from "../navegacion";
import { usePedirRevision } from "../revision";
import type { CeldaDetalle, CeldaResumen, Columna, Evidencia } from "../tipos";

const NIVEL: Record<string, string> = {
  VERIFICADA: "Verificada",
  VERIFICADA_CON_CORRECCION: "Verificada en otro bloque",
  POR_CONFIRMAR: "Por confirmar",
  NO_VERIFICABLE: "No verificable",
};

const ESTADO: Record<string, string> = {
  SIN_EVIDENCIA: "Heredada, sin evidencia",
  PENDIENTE: "Pendiente de revisión",
  POR_CONFIRMAR: "Por confirmar",
  NO_VERIFICABLE: "No verificable",
  APROBADA: "Aprobada",
  CORREGIDA: "Corregida",
  RECHAZADA: "Rechazada",
};

type Props = {
  pid: string;
  estudio: number;
  columna: Columna;
  resumen: CeldaResumen;
  posicion?: { x: number; y: number };
  fija?: boolean;
  onCerrar: () => void;
  onEntrar?: () => void;
  onSalir?: () => void;
};

export function etiquetaEvidencia(estudio: number, columna: string, e: Evidencia): string {
  return `Estudio ${estudio} · ${columna} · p. ${e.ancla?.pagina ?? e.pagina_pdf} · ${e.ubicacion}`;
}

export function FichaEvidencia({ pid, estudio, columna, resumen, posicion, fija, onCerrar, onEntrar, onSalir }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["celda", pid, estudio, columna.clave],
    queryFn: () => api.celda(pid, estudio, columna.clave),
  });
  const ir = useNavegacion((s) => s.ir);
  const pedir = usePedirRevision(pid);

  const irAlPdf = (d: CeldaDetalle, e: Evidencia) => {
    if (!d.articulo_id) return;
    ir({
      estudio,
      columna: columna.clave,
      articuloId: d.articulo_id,
      visor: {
        articuloId: d.articulo_id,
        pagina: e.ancla?.pagina ?? e.pagina_pdf,
        zoom: 1,
        rect: e.ancla?.rect,
        cita: e.cita_textual,
        etiqueta: etiquetaEvidencia(estudio, columna.clave, e),
      },
    });
    if (!fija) onCerrar();
  };

  const estilo = posicion
    ? {
        left: Math.max(8, Math.min(posicion.x, window.innerWidth - 440)),
        top: Math.max(8, Math.min(posicion.y, window.innerHeight - 420)),
      }
    : undefined;

  return (
    <aside
      className={`ficha ${fija ? "fija" : "flotante"}`}
      style={estilo}
      onMouseEnter={onEntrar}
      onMouseLeave={onSalir}
      onKeyDown={(e) => e.key === "Escape" && onCerrar()}
      tabIndex={-1}
    >
      <header>
        <span className={`punto ${colorDe(resumen)}`} />
        <div>
          <div className="tenue">
            Estudio {estudio} · {columna.letra} · {columna.clave}
          </div>
          <div className="valor">{mostrarValor(resumen.valor, resumen.estado_dato) || <em>vacío</em>}</div>
        </div>
        <button className="cerrar" onClick={onCerrar} aria-label="Cerrar">
          <Icono nombre="cerrar" tam={14} grosor={2.2} />
        </button>
      </header>
      <div className="etiquetas">
        <span className="etiqueta">{ESTADO[resumen.estado_revision]}</span>
        {resumen.tipo_valor && <span className="etiqueta">{resumen.tipo_valor.toLowerCase()}</span>}
        {resumen.fuera_de_vocabulario && <span className="etiqueta aviso">fuera del vocabulario del libro</span>}
      </div>

      {isLoading && <p className="tenue">Cargando…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && (
        <div className="cuerpo">
          {data.evidencias.length === 0 && data.origen === "HEREDADA" && (
            <p className="tenue">Fila heredada de la matriz vigente: no tiene página ni cita. Se sustenta al reextraer.</p>
          )}
          {data.evidencias.map((e, i) => (
            <div key={i} className={`evidencia nivel-${e.ancla?.nivel ?? "sin"}`}>
              <div className="cabeza">
                <span>
                  p. {e.pagina_pdf} · {e.ubicacion}
                  {e.fila_tabla && ` · fila “${e.fila_tabla}”`}
                  {e.columna_tabla && ` · columna “${e.columna_tabla}”`}
                </span>
                {e.ancla && <span className="nivel">{NIVEL[e.ancla.nivel]}</span>}
              </div>
              <blockquote>
                <mark>{e.cita_textual}</mark>
              </blockquote>
              <div className="pie">
                <span className="tenue">
                  {e.bloque_id && `bloque ${e.bloque_id}`}
                  {e.ancla?.nota && ` · ${e.ancla.nota}`}
                  {e.leido_de_figura && " · leído de figura"}
                </span>
                <button onClick={() => irAlPdf(data, e)} disabled={!data.articulo_id}>
                  <Icono nombre="visor" tam={14} /> Ir al PDF
                </button>
              </div>
            </div>
          ))}
          {data.inferencia && (
            <div className="bloque amarillo">
              <strong>Inferido</strong> · {data.inferencia.regla}
              <p>{data.inferencia.razonamiento}</p>
            </div>
          )}
          {data.discrepancias.map((d, i) => (
            <div key={i} className="bloque naranja">
              <strong>Discrepancia del artículo</strong>
              <p>{d.fuente_1}</p>
              <p>{d.fuente_2}</p>
              <p>
                Adoptado: <em>{d.valor_adoptado}</em>
              </p>
            </div>
          ))}
          {data.hallazgos.map((h, i) => (
            <div key={i} className="bloque rojo">
              <strong>
                {h.auditor ?? "Auditor"} · {h.veredicto}
              </strong>
              <p>{h.hallazgo}</p>
            </div>
          ))}
          {data.nota_heredada && (
            <div className="bloque gris">
              <strong>Nota heredada{data.nota_heredada.autor ? ` (${data.nota_heredada.autor})` : ""}</strong>
              <p>{data.nota_heredada.texto}</p>
            </div>
          )}
          {data.historial.length > 0 && (
            <details>
              <summary>Historial ({data.historial.length})</summary>
              {data.historial.map((h, i) => (
                <p key={i} className="tenue">
                  {h.fecha.slice(0, 16).replace("T", " ")} · {h.autor} · {h.accion}
                  {h.accion === "CORREGIR" && ` ${mostrarValor(h.valor_anterior, null)} → ${mostrarValor(h.valor_nuevo, null)}`}
                  {h.motivo && ` · ${h.motivo}`}
                </p>
              ))}
            </details>
          )}
        </div>
      )}
      <footer className="botones">
        <button className="aprobar" onClick={() => pedir("aprobar", estudio, columna, resumen)}>
          <Icono nombre="check" tam={16} /> Aprobar <kbd>A</kbd>
        </button>
        <button className="corregir" onClick={() => pedir("corregir", estudio, columna, resumen)}>
          <Icono nombre="lapiz" tam={16} /> Corregir <kbd>E</kbd>
        </button>
        <button className="rechazar" onClick={() => pedir("rechazar", estudio, columna, resumen)}>
          <Icono nombre="rechazo" tam={16} /> Rechazar <kbd>R</kbd>
        </button>
      </footer>
    </aside>
  );
}

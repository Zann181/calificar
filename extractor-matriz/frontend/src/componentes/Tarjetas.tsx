// Revisión en teléfono (sección 9.6): una tarjeta por celda pendiente, primero rojo, luego amarillo, luego el resto.
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { colorDe, mostrarValor, prioridad, revisada } from "../colores";
import { Icono } from "./Icono";
import { useNavegacion } from "../navegacion";
import { usePedirRevision } from "../revision";
import type { Columna, Fila } from "../tipos";
import { etiquetaEvidencia } from "./FichaEvidencia";

type Props = { pid: string; columnas: Columna[]; filas: Fila[]; onVerPdf: () => void };

export function Tarjetas({ pid, columnas, filas, onVerPdf }: Props) {
  const qc = useQueryClient();
  const ir = useNavegacion((s) => s.ir);
  const pedir = usePedirRevision(pid);

  const cola = filas
    .filter((f) => f.origen === "EXTRAIDA")
    .flatMap((f) =>
      columnas
        .filter((c) => {
          const celda = f.celdas[c.clave];
          return celda && !revisada(celda) && (celda.valor !== null || celda.evidencias > 0);
        })
        .map((c) => ({ fila: f, columna: c, celda: f.celdas[c.clave], color: colorDe(f.celdas[c.clave]) })),
    )
    .sort((a, b) => prioridad(a.color) - prioridad(b.color));

  const verPdf = async (fila: Fila, columna: Columna) => {
    if (!fila.articulo_id) return;
    const d = await qc.fetchQuery({
      queryKey: ["celda", pid, fila.estudio, columna.clave],
      queryFn: () => api.celda(pid, fila.estudio, columna.clave),
    });
    const e = d.evidencias[0];
    ir({
      estudio: fila.estudio,
      columna: columna.clave,
      articuloId: fila.articulo_id,
      visor: {
        articuloId: fila.articulo_id,
        pagina: e ? (e.ancla?.pagina ?? e.pagina_pdf) : 1,
        zoom: 1,
        rect: e?.ancla?.rect,
        cita: e?.cita_textual,
        etiqueta: e ? etiquetaEvidencia(fila.estudio, columna.clave, e) : undefined,
      },
    });
    onVerPdf();
  };

  if (!cola.length) return <p className="vacio">No hay celdas pendientes de revisión.</p>;

  return (
    <section className="tarjetas">
      <p className="tenue">{cola.length} celdas pendientes</p>
      {cola.map(({ fila, columna, celda, color }) => (
        <article key={`${fila.estudio}-${columna.clave}`} className={`tarjeta borde-${color}`}>
          <div className="sobre tenue">
            Estudio {fila.estudio} · {columna.letra}
          </div>
          <h4>{columna.clave}</h4>
          <p className={`valor ${mostrarValor(celda.valor, celda.estado_dato).length > 40 ? "largo" : ""}`}>
            {mostrarValor(celda.valor, celda.estado_dato) || <em>vacío</em>}
          </p>
          <TarjetaCita pid={pid} estudio={fila.estudio} clave={columna.clave} conEvidencia={celda.evidencias > 0} />
          <div className="botones">
            <button onClick={() => verPdf(fila, columna)} disabled={celda.evidencias === 0}>
              <Icono nombre="visor" tam={18} />
              PDF
            </button>
            <button className="aprobar" onClick={() => pedir("aprobar", fila.estudio, columna, celda)}>
              <Icono nombre="check" tam={18} />
              Aprobar
            </button>
            <button className="corregir" onClick={() => pedir("corregir", fila.estudio, columna, celda)}>
              <Icono nombre="lapiz" tam={18} />
              Corregir
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}


function TarjetaCita({ pid, estudio, clave, conEvidencia }: { pid: string; estudio: number; clave: string; conEvidencia: boolean }) {
  const { data } = useQuery({
    queryKey: ["celda", pid, estudio, clave],
    queryFn: () => api.celda(pid, estudio, clave),
    enabled: conEvidencia,
  });
  const e = data?.evidencias[0];
  if (!conEvidencia) return <p className="tenue">Sin cita en el artículo.</p>;
  if (!e) return <p className="tenue">…</p>;
  return (
    <blockquote>
      <mark>{e.cita_textual}</mark>
      <footer className="tenue">p. {e.pagina_pdf}</footer>
    </blockquote>
  );
}

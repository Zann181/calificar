// Vista previa: cómo encajan los candidatos seleccionados con las columnas elegidas, según sus metadatos y su resumen
// (plan «Buscar», sección 5.4). SIEMPRE «sin verificar»: no se escribe nada en la matriz; solo el PDF, con su cita, la llena.
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { ESTADOS_CELDA, ETIQUETAS, textoPuntaje } from "../cobertura";
import type { Candidato, CeldaPrevia } from "../tipos";

function Celda({ c }: { c: CeldaPrevia }) {
  const contenido = c.valor ?? (c.estado === "PENDIENTE" ? "—" : "");
  return (
    <td className={`celda-${c.estado.toLowerCase()}`} title={[ESTADOS_CELDA[c.estado], c.origen, c.frase && `«${c.frase}»`].filter(Boolean).join(" · ")}>
      <span className="valor">{contenido.length > 90 ? contenido.slice(0, 89) + "…" : contenido}</span>
      <small className="estado">{ESTADOS_CELDA[c.estado]}</small>
    </td>
  );
}

function Detalle({ c }: { c: Candidato }) {
  const ev = c.evaluacion;
  if (!ev) return null;
  return (
    <>
      <h3>{c.titulo}</h3>
      <p>
        <span className={`buscar-etiqueta et-${ev.etiqueta}`}>{ETIQUETAS[ev.etiqueta]}</span>{" "}
        <span className="tenue">{textoPuntaje(ev)}</span>
        {ev.razon && <span className="tenue"> · {ev.razon}</span>}
      </p>
      <table className="buscar-previa">
        <thead>
          <tr>
            <th>Columna</th>
            <th>Valor propuesto</th>
            <th>Estado</th>
            <th>De dónde</th>
          </tr>
        </thead>
        <tbody>
          {ev.celdas.map((x) => (
            <tr key={x.columna} className={`celda-${x.estado.toLowerCase()}`}>
              <td>
                {x.columna} <small className="tenue">{x.prioridad.toLowerCase()}</small>
              </td>
              <td>{x.valor ?? <span className="tenue">—</span>}</td>
              <td>{ESTADOS_CELDA[x.estado]}</td>
              <td className="tenue">
                {x.origen}
                {x.frase && <q>{x.frase}</q>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

type Props = { pid: string; ids: string[]; perfilId?: string; onCerrar: () => void };

export function VistaPreviaDeFila({ pid, ids, perfilId, onCerrar }: Props) {
  const q = useQuery({
    queryKey: ["vista-previa", pid, ids, perfilId],
    queryFn: () => api.vistaPrevia(pid, ids, perfilId),
    enabled: ids.length > 0,
  });
  const candidatos = q.data?.candidatos ?? [];
  const columnas = q.data?.perfil.columnas ?? [];
  return (
    <aside className="buscar-ficha buscar-previa-caja">
      <div className="buscar-previa-cabeza">
        <h2>Vista previa · {ids.length === 1 ? "una fila" : `${ids.length} candidatos`}</h2>
        <button className="sin-borde" onClick={onCerrar} aria-label="Cerrar la vista previa">
          Cerrar
        </button>
      </div>
      <p className="buscar-aviso">
        Sin verificar: no se escribe en la matriz. Son indicios de los metadatos y del resumen; los valores reales salen
        solo del PDF, con su página y su cita.
      </p>
      {q.isLoading && <p className="tenue">Calculando…</p>}
      {q.error && <p className="error">{(q.error as Error).message}</p>}
      {candidatos.length === 1 && <Detalle c={candidatos[0]} />}
      {candidatos.length > 1 && (
        <div className="buscar-tabla-caja">
          <table className="buscar-previa comparativa">
            <thead>
              <tr>
                <th>Candidato</th>
                <th>Cobertura</th>
                {columnas.map((c) => (
                  <th key={c.clave} title={c.prioridad.toLowerCase()} className={`p-${c.prioridad}`}>
                    {c.clave}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {candidatos.map((c) => (
                <tr key={c.id}>
                  <th scope="row" className="titulo-previa">
                    {c.titulo}
                    <small className="tenue">{c.anio}</small>
                  </th>
                  <td>
                    {c.evaluacion && (
                      <>
                        <span className={`buscar-etiqueta et-${c.evaluacion.etiqueta}`}>{ETIQUETAS[c.evaluacion.etiqueta]}</span>
                        <small className="tenue">{textoPuntaje(c.evaluacion)}</small>
                      </>
                    )}
                  </td>
                  {(c.evaluacion?.celdas ?? []).map((x) => (
                    <Celda key={x.columna} c={x} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </aside>
  );
}

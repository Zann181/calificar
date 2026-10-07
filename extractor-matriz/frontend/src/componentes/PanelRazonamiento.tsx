// Panel «Por qué este valor» (bajo el PDF). Junta tres fuentes para explicar una celda:
//   1. la guía de la columna, derivada del libro de códigos (qué se busca y cómo manda llenarla);
//   2. lo que el modelo dejó para esta celda (tipo de valor, citas con su verificación, razonamiento);
//   3. el contexto de la fila (por qué existe, muestra, confianza, advertencias).
// Nada de esto se redacta aquí: son textos del libro y de la trazabilidad de la extracción.
import { useQuery } from "@tanstack/react-query";
import { Component, useState } from "react";

import { api } from "../api";
import { mostrarValor } from "../colores";
import { useNavegacion } from "../navegacion";
import type { CeldaDetalle, Columna, InferenciaFila, Protocolo } from "../tipos";

const COMO: Record<string, string> = {
  LITERAL: "Literal: el valor está copiado del artículo.",
  CODIFICADO: "Codificado: el valor es una categoría del libro asignada por el modelo; el artículo no lo dice con esas palabras.",
  INFERIDO: "Inferido: el artículo no lo dice y el modelo lo dedujo con una regla del libro.",
  FALTANTE: "Faltante: no se encontró en el artículo.",
};

const NIVEL: Record<string, string> = {
  VERIFICADA: "la cita aparece literal en el bloque indicado.",
  VERIFICADA_CON_CORRECCION: "la cita se halló, pero en otro bloque distinto al que dijo el modelo.",
  POR_CONFIRMAR: "la cita se parece al texto pero no coincide exacta: requiere confirmación humana.",
  NO_VERIFICABLE: "no se pudo ubicar la cita en el PDF: no cuenta como verificada.",
};

const CONFIANZA: Record<string, string> = {
  Alta: "todo literal o codificado sin duda",
  Media: "una o más inferencias simples",
  Baja: "discrepancias sin resolver o dudas entre categorías",
};

/** Texto legible de un valor de trazabilidad (escalar, lista de pares o lista de coeficientes). */
function texto(v: unknown): string {
  if (v === null || v === undefined || v === "") return "sin dato";
  if (typeof v === "boolean") return v ? "sí" : "no";
  if (Array.isArray(v)) return v.length ? v.map(texto).join("; ") : "ninguno";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("tipo" in o && "valor" in o) return `${texto(o.tipo)} ${texto(o.valor)}`;
    if ("descripcion" in o) return `${texto(o.descripcion)}: ${texto(o.valor)}${o.evidencia ? ` (${texto(o.evidencia)})` : ""}`;
    return Object.entries(o)
      .map(([k, x]) => `${k}: ${texto(x)}`)
      .join(", ");
  }
  return String(v);
}

/** Pinta un texto del libro sea cual sea su forma: texto, lista o diccionario (categoría → significado). */
function Rica({ v }: { v: unknown }): React.ReactElement | null {
  if (v === null || v === undefined || v === "") return null;
  if (Array.isArray(v)) {
    return (
      <ul>
        {v.map((x, i) => (
          <li key={i}>{typeof x === "object" && x !== null ? <Rica v={x} /> : String(x)}</li>
        ))}
      </ul>
    );
  }
  if (typeof v === "object") {
    return (
      <dl className="reglas">
        {Object.entries(v as Record<string, unknown>).map(([k, x]) => (
          <div key={k}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>{typeof x === "object" && x !== null ? <Rica v={x} /> : String(x)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <p>{String(v)}</p>;
}

/** Si la columna define sus categorías en el libro, devuelve el significado de la(s) elegida(s). */
function significadoDelValor(col: Columna | undefined, valor: unknown): { categoria: string; significado: string }[] {
  const reglas = col?.guia?.reglas_de_codificacion;
  if (!reglas || typeof reglas !== "object" || Array.isArray(reglas) || valor === null || valor === undefined) return [];
  const mapa = reglas as Record<string, unknown>;
  return String(valor)
    .split("; ")
    .flatMap((parte) => {
      const clave = Object.keys(mapa).find((k) => k === parte || k.toLowerCase() === parte.toLowerCase());
      return clave && typeof mapa[clave] === "string" ? [{ categoria: clave, significado: mapa[clave] as string }] : [];
    });
}

/** Un fallo al pintar el panel no debe tumbar la aplicación. */
class Contenedor extends Component<{ children: React.ReactNode }, { fallo: boolean }> {
  state = { fallo: false };
  static getDerivedStateFromError() {
    return { fallo: true };
  }
  render() {
    return this.state.fallo ? <p className="error razonamiento-error">No se pudo mostrar la explicación de esta celda.</p> : this.props.children;
  }
}

function Seccion({ titulo, abierta, children }: { titulo: string; abierta?: boolean; children: React.ReactNode }) {
  return (
    <details className="seccion" open={abierta}>
      <summary>{titulo}</summary>
      <div className="cuerpo-seccion">{children}</div>
    </details>
  );
}

function Lineas({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}

function inferenciasRelacionadas(data: CeldaDetalle, col: Columna | undefined): InferenciaFila[] {
  const todas = data.trazabilidad_fila?.inferencias ?? [];
  const campos = (col?.guia?.campos_de_trazabilidad ?? []).map((c) => c.campo);
  const propia = data.inferencia?.razonamiento;
  return todas.filter((i) => {
    const nombre = String(i.columna ?? "");
    if (i.razonamiento && i.razonamiento === propia) return false; // ya se muestra como inferencia de la celda
    return nombre.includes(data.clave) || campos.some((c) => nombre.includes(c));
  });
}

type Contexto = { data: CeldaDetalle; col: Columna | undefined; protocolo: Protocolo | undefined };

function QueSeBuscaba({ col }: Pick<Contexto, "col">) {
  const g = col?.guia;
  if (!g) return <p className="tenue">El libro de códigos no trae guía para esta columna.</p>;
  return (
    <>
      {g.para_que_sirve && <p>{g.para_que_sirve}</p>}
      {g.relacion_con_otras_columnas && <p className="tenue">{g.relacion_con_otras_columnas}</p>}
      {g.donde_buscar && (
        <p>
          <b>Dónde buscar:</b> {g.donde_buscar}
        </p>
      )}
    </>
  );
}

function ComoLoManda({ col }: Pick<Contexto, "col">) {
  const g = col?.guia;
  if (!g) return null;
  return (
    <>
      {g.como_se_extrae && g.como_se_extrae.length > 0 && (
        <>
          <b>Pasos del libro</b>
          <ol>
            {g.como_se_extrae.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ol>
        </>
      )}
      {g.regla_de_decision !== undefined && (
        <>
          <b>Regla de decisión</b>
          <Rica v={g.regla_de_decision} />
        </>
      )}
      {g.reglas_de_codificacion !== undefined && (
        <>
          <b>Reglas de codificación</b>
          <Rica v={g.reglas_de_codificacion} />
        </>
      )}
      {g.formato && (
        <p>
          <b>Formato:</b> {g.formato}
        </p>
      )}
      {col?.valores_permitidos && (
        <p>
          <b>Valores permitidos:</b> {col.valores_permitidos.join(" · ")}
        </p>
      )}
      <p className="tenue">
        {col?.obligatorio ? "Obligatoria" : "Opcional"} · nivel {col?.nivel_de_registro}
        {col?.requiere_evidencia ? " · exige página y cita del artículo" : " · no exige cita"}
      </p>
    </>
  );
}

function QueHizoElModelo({ data, col, protocolo }: Contexto) {
  const propia = data.inferencia;
  const otras = inferenciasRelacionadas(data, col);
  const campos = (col?.guia?.campos_de_trazabilidad ?? []).filter((c) => c.campo in (data.trazabilidad_fila ?? {}));
  const faltante = data.valor === null || data.valor === undefined || data.valor === "";
  return (
    <>
      <p>
        <b>Valor:</b> <mark>{mostrarValor(data.valor, data.estado_dato) || "vacío"}</mark>
        {data.tipo_valor && <> · {COMO[data.tipo_valor]}</>}
      </p>
      {significadoDelValor(col, data.valor).map((m) => (
        <p key={m.categoria}>
          <b>Qué significa «{m.categoria}» según el libro:</b> {m.significado}
        </p>
      ))}
      {faltante && (
        <p>
          <b>Por qué quedó vacío:</b>{" "}
          {data.estado_dato ? (
            <>
              código «{data.estado_dato}»{protocolo?.faltantes[data.estado_dato] && ` — ${protocolo.faltantes[data.estado_dato]}`}.
            </>
          ) : (
            "no hay código de faltante registrado."
          )}
          {col?.guia?.codigo_si_falta && <> Regla del libro: {col.guia.codigo_si_falta}.</>}
        </p>
      )}
      {data.evidencias.length > 0 && (
        <>
          <b>Dónde lo leyó</b>
          {data.evidencias.map((e, i) => (
            <blockquote key={i}>
              <span className="tenue">
                p. {e.pagina_pdf} · {e.ubicacion}
                {e.fila_tabla && ` · fila “${e.fila_tabla}”`}
                {e.columna_tabla && ` · columna “${e.columna_tabla}”`}
                {e.leido_de_figura && " · leído de figura"}
              </span>
              <q>{e.cita_textual}</q>
              {e.ancla && (
                <span className={`tenue nivel-${e.ancla.nivel}`}>
                  Verificación: {NIVEL[e.ancla.nivel]}
                  {e.ancla.nota && ` ${e.ancla.nota}`}
                </span>
              )}
            </blockquote>
          ))}
        </>
      )}
      {data.evidencias.length === 0 && !faltante && (
        <p className="tenue">
          {data.origen === "HEREDADA"
            ? "Valor heredado de la matriz vigente: no tiene página ni cita. Se sustenta al reextraer."
            : col?.requiere_evidencia === false
              ? "Esta columna no exige cita: el libro manda derivarla de otras columnas de la fila o de datos del equipo."
              : "El modelo no entregó cita para esta celda."}
        </p>
      )}
      {(propia || otras.length > 0) && (
        <>
          <b>Razonamiento del modelo</b>
          {propia && (
            <p>
              Regla «{propia.regla}»: {propia.razonamiento}
            </p>
          )}
          {otras.map((i, k) => (
            <p key={k}>
              <span className="tenue">{i.columna}</span> — regla «{i.regla_aplicada}»: {i.razonamiento}
            </p>
          ))}
        </>
      )}
      {campos.length > 0 && (
        <>
          <b>Datos de trazabilidad ligados a esta columna</b>
          <dl>
            {campos.map((c) => (
              <div key={c.campo}>
                <dt title={c.descripcion}>{c.campo.replace(/_/g, " ")}</dt>
                <dd>{texto(data.trazabilidad_fila[c.campo])}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {data.discrepancias.map((d, i) => (
        <p key={i}>
          <b>Discrepancia del artículo:</b> {d.fuente_1} / {d.fuente_2}. Se adoptó: <em>{d.valor_adoptado}</em>.
        </p>
      ))}
      {data.hallazgos.map((h, i) => (
        <p key={i}>
          <b>
            {h.auditor ?? "Auditor"} · {h.veredicto}:
          </b>{" "}
          {h.hallazgo}
        </p>
      ))}
      {!propia && otras.length === 0 && data.evidencias.length > 0 && (
        <p className="tenue">
          Para los valores literales y codificados el modelo no guarda un razonamiento aparte: el sustento es la cita leída con la regla de la columna.
        </p>
      )}
    </>
  );
}

function ContextoDeLaFila({ data }: Pick<Contexto, "data">) {
  const t = data.trazabilidad_fila ?? {};
  const advertencias = Array.isArray(t.advertencias_pendientes) ? (t.advertencias_pendientes as string[]) : [];
  const confianza = typeof t.confianza === "string" ? t.confianza : null;
  return (
    <>
      {typeof t.mapa_de_efectos === "string" && (
        <p>
          <b>Por qué existe esta fila:</b> {t.mapa_de_efectos}
        </p>
      )}
      <p className="tenue">
        Estudio {data.estudio} · Documento {data.documento}
        {typeof t.id_muestra === "string" && ` · muestra ${t.id_muestra}`}
        {typeof t.via_de_identificacion === "string" && ` · vía: ${t.via_de_identificacion}`}
      </p>
      {confianza && (
        <p>
          <b>Confianza de la fila:</b> {confianza}
          {CONFIANZA[confianza] && ` (${CONFIANZA[confianza]})`}
          {typeof t.extractor === "string" && ` · extraída por ${t.extractor}`}
          {typeof t.fecha_extraccion === "string" && ` el ${t.fecha_extraccion}`}
          {t.verificador ? ` · verificada por ${texto(t.verificador)}` : " · sin verificador todavía"}.
        </p>
      )}
      {advertencias.length > 0 && (
        <>
          <b>Advertencias pendientes del modelo</b>
          <Lineas items={advertencias} />
        </>
      )}
    </>
  );
}

function ReglasGenerales({ protocolo }: { protocolo: Protocolo | undefined }) {
  if (!protocolo) return <p className="tenue">Cargando…</p>;
  const f = protocolo.como_se_construye_cada_fila;
  return (
    <>
      <b>Principios de veracidad</b>
      <Lineas items={protocolo.principios_de_veracidad} />
      <b>Qué fuente manda dentro del artículo</b>
      <Lineas items={protocolo.precedencia_de_fuentes} />
      <b>Códigos de faltante</b>
      <Lineas items={Object.entries(protocolo.faltantes).map(([k, v]) => `${k}: ${v}`)} />
      <b>Cómo se arma cada fila</b>
      {f.unidad_de_analisis && <p>{f.unidad_de_analisis}</p>}
      {f.jerarquia && <p>{f.jerarquia}</p>}
      <Lineas items={f.regla_para_abrir_una_fila_nueva} />
    </>
  );
}

export function PanelRazonamiento({ pid }: { pid: string }) {
  return (
    <Contenedor>
      <Panel pid={pid} />
    </Contenedor>
  );
}

function Panel({ pid }: { pid: string }) {
  const { estudio, columna } = useNavegacion((s) => s.actual);
  const [abierto, setAbierto] = useState(true);
  const columnas = useQuery({ queryKey: ["columnas", pid], queryFn: () => api.columnas(pid) });
  const protocolo = useQuery({ queryKey: ["protocolo", pid], queryFn: () => api.protocolo(pid), staleTime: Infinity });
  const { data, isLoading, error } = useQuery({
    queryKey: ["celda", pid, estudio, columna],
    queryFn: () => api.celda(pid, estudio!, columna!),
    enabled: estudio !== undefined && !!columna,
  });
  if (estudio === undefined || !columna) return null;
  const col = columnas.data?.find((c) => c.clave === columna);
  const ejemplo = col?.guia?.ejemplo;

  return (
    <section className={`razonamiento ${abierto ? "abierto" : ""}`} aria-label="Por qué este valor">
      <button className="cabeza" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
        <strong>Por qué este valor</strong>
        <span className="tenue">
          Estudio {estudio} · {col ? `${col.letra} · ` : ""}
          {columna}
        </span>
        <span className="flecha">{abierto ? "▾" : "▸"}</span>
      </button>
      {abierto && (
        <div className="contenido">
          {isLoading && <p className="tenue">Cargando…</p>}
          {error && <p className="error">{(error as Error).message}</p>}
          {data && (
            <>
              <Seccion titulo="1. Qué se buscaba en esta columna" abierta>
                <QueSeBuscaba col={col} />
              </Seccion>
              <Seccion titulo="2. Qué hizo el modelo con este artículo" abierta>
                <QueHizoElModelo data={data} col={col} protocolo={protocolo.data} />
              </Seccion>
              <Seccion titulo="3. Cómo manda el libro llenarla">
                <ComoLoManda col={col} />
              </Seccion>
              <Seccion titulo="4. Contexto de la fila">
                <ContextoDeLaFila data={data} />
              </Seccion>
              {ejemplo?.explicacion && (
                <Seccion titulo="5. Ejemplo del libro">
                  <p>
                    {ejemplo.cita_en_matriz && <b>{ejemplo.cita_en_matriz}: </b>}
                    {ejemplo.valor_registrado !== undefined && <mark>{mostrarValor(ejemplo.valor_registrado, null)}</mark>}{" "}
                    {ejemplo.explicacion}
                  </p>
                </Seccion>
              )}
              <Seccion titulo="6. Reglas generales del libro">
                <ReglasGenerales protocolo={protocolo.data} />
              </Seccion>
            </>
          )}
        </div>
      )}
    </section>
  );
}

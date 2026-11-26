// Pestaña «Buscar» (ADR 0011, docs/PLAN_BUSQUEDA_ARTICULOS.md): encontrar artículos que traigan los datos de la matriz.
// Todo lo que se ve aquí son indicios de las fuentes, sin verificar: nada entra a la matriz; solo el PDF, con su cita.
// Sin modelos de lenguaje: la búsqueda y el orden son deterministas.
// En la nube (ADR 0012) se puede buscar; las decisiones, la importación, el análisis y los perfiles se hacen en el
// equipo, que recibe lo buscado en la web con la sincronización.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api";
import { useEscritura, usePuedeBuscar } from "../capacidades";
import { ESTADOS_CELDA, ETIQUETAS, segmentos, textoPuntaje } from "../cobertura";
import type {
  Busqueda,
  Candidato,
  ConceptoBusqueda,
  EstadoCandidato,
  ExigirColumnas,
  FuenteBusqueda,
  OrdenCandidatos,
  ProgresoFuente,
  SitioConCredenciales,
} from "../tipos";
import { MAX_IMPORTAR } from "../tipos";
import type { EstadoAnalisis, EstadoImportacion } from "../tipos";
import { ColumnasEnLectura, SelectorDeColumnas } from "./SelectorDeColumnas";
import { VistaPreviaDeFila } from "./VistaPreviaDeFila";

const IDIOMAS: [string, string][] = [
  ["en", "Inglés"],
  ["es", "Español"],
  ["pt", "Portugués"],
];
const LIMITES = [50, 100, 200, 500];
const ESTADOS: [EstadoCandidato | "", string][] = [
  ["", "Todos"],
  ["NUEVO", "Nuevos"],
  ["PRIORIZADO", "Priorizados"],
  ["DESCARTADO", "Descartados"],
  ["IMPORTADO", "Importados"],
];

const ETIQUETA_IMPORTACION: Record<EstadoImportacion, [string, string]> = {
  IMPORTADO: ["Importado", "lista"],
  YA_ESTABA: ["Ya estaba", "pendiente"],
  SIN_COPIA_ABIERTA: ["Sin copia abierta", "buscando"],
  RECHAZADO: ["No se importó", "buscando"],
  ERROR: ["Error", "error"],
};

const ETIQUETA_ANALISIS: Record<EstadoAnalisis, [string, string]> = {
  ANALIZADO: ["Leído", "lista"],
  TEXTO_INSUFICIENTE: ["Casi sin texto", "buscando"],
  SIN_COPIA_ABIERTA: ["Sin copia abierta", "buscando"],
  ERROR: ["Error", "error"],
};

type ConceptoEditable = { nombre: string; texto: string; obligatorio: boolean };

const aEditable = (c: ConceptoBusqueda): ConceptoEditable => ({
  nombre: c.nombre,
  texto: c.terminos.join("\n"),
  obligatorio: c.obligatorio,
});
const terminosDe = (texto: string) =>
  texto
    .split(/\n|;/)
    .map((t) => t.trim())
    .filter(Boolean);
const hora = (iso: string) => new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });

function EstadoFuente({ p }: { p: ProgresoFuente }) {
  const etiqueta = {
    PENDIENTE: "En espera",
    BUSCANDO: "Buscando…",
    LISTA: "Lista",
    ERROR: "Con error",
    OMITIDA: "Omitida",
  }[p.estado];
  return <span className={`buscar-estado ${p.estado.toLowerCase()}`}>{etiqueta}</span>;
}

function Progreso({ b, fuentes, pid }: { b: Busqueda; fuentes: FuenteBusqueda[]; pid: string }) {
  const cliente = useQueryClient();
  const escritura = useEscritura();
  const puedeBuscar = usePuedeBuscar();
  const cancelar = useMutation({
    mutationFn: () => api.cancelarBusqueda(pid, b.id),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["busquedas", pid] }),
  });
  return (
    <section className="buscar-tarjeta" aria-live="polite">
      <header>
        <strong>{b.nombre}</strong>
        <span className="tenue">
          {b.estado === "EN_CURSO" ? "En curso…" : `${b.total_unicos} candidatos únicos`}
        </span>
      </header>
      <ul className="buscar-progreso">
        {b.fuentes.map((f) => {
          const p = b.progreso[f];
          const etiqueta = fuentes.find((x) => x.id === f)?.etiqueta ?? f;
          return (
            <li key={f} className={p.errores ? "con-error" : ""}>
              <span className="nombre">{etiqueta}</span>
              <EstadoFuente p={p} />
              <span className="tenue">
                {p.encontrados} hallados · {p.nuevos} nuevos
              </span>
              {p.errores > 0 && (
                <span className="buscar-errores" title={p.ultimo_error ?? ""}>
                  {p.errores} error{p.errores === 1 ? "" : "es"}
                </span>
              )}
              {p.ultimo_error && <small className="error">{p.ultimo_error}</small>}
            </li>
          );
        })}
      </ul>
      {b.errores > 0 && (
        <p className="tenue">
          La búsqueda quedó incompleta en alguna fuente. El detalle está en el Registro{escritura ? "" : " del equipo local"}{" "}
          (origen «descubrimiento», nivel Errores).
        </p>
      )}
      {b.estado === "EN_CURSO" && puedeBuscar && (
        <button onClick={() => cancelar.mutate()} disabled={cancelar.isPending}>
          Cancelar búsqueda
        </button>
      )}
    </section>
  );
}

function SitiosConCredenciales({ sitios }: { sitios: SitioConCredenciales[] }) {
  if (!sitios.length) return null;
  return (
    <section className="buscar-tarjeta">
      <header>
        <strong>Sitios con credenciales</strong>
      </header>
      <p className="tenue">
        Las credenciales las escribe siempre usted, en su propio navegador. La aplicación no las pide ni las guarda.
      </p>
      <ul className="buscar-sitios">
        {sitios.map((s) => (
          <li key={s.id}>
            <div className="fila">
              <strong>{s.nombre}</strong>
              <span className={`buscar-estado ${s.sesion === "VIGENTE" ? "lista" : "pendiente"}`}>
                {s.sesion === "VIGENTE" ? "Conectado" : s.sesion === "VENCIDA" ? "Sesión vencida" : "No conectado"}
              </span>
            </div>
            <p className="tenue">
              Tope propio: {Math.round(s.limite.bytes_por_ventana / 1e6)} MB cada {Math.round(s.limite.ventana_s / 60)} min,
              pausa de {s.limite.pausa_min_s} s entre peticiones.
            </p>
            <details>
              <summary>{s.bases.length} bases</summary>
              <p className="tenue">{s.bases.join(" · ")}</p>
            </details>
            <button disabled title="La conexión con la sesión del usuario llega con la Fase 5 del plan">
              Conectar (próximamente)
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Barra apilada: verde = metadato o indicio, rayado = pendiente de PDF (no es «ausente»), rojo = ausente. */
function BarraCobertura({ c }: { c: Candidato }) {
  const ev = c.evaluacion;
  if (!ev) return null;
  const s = segmentos(ev.celdas);
  const pct = (x: number) => `${x * 100}%`;
  return (
    <div className="buscar-cobertura" title={`${ETIQUETAS[ev.etiqueta]} · ${textoPuntaje(ev)}${ev.razon ? ` · ${ev.razon}` : ""}`}>
      <div className="barra" role="img" aria-label={`Cobertura ${textoPuntaje(ev)}`}>
        <i className="cubierto" style={{ width: pct(s.cubierto) }} />
        <i className="pendiente" style={{ width: pct(s.pendiente) }} />
        <i className="ausente" style={{ width: pct(s.ausente) }} />
      </div>
      <span className={`buscar-etiqueta et-${ev.etiqueta}`}>{ETIQUETAS[ev.etiqueta]}</span>
      <small className="tenue">{ev.etapa === "B" ? "texto completo" : "solo resumen"}</small>
    </div>
  );
}

function Ficha({ c }: { c: Candidato | undefined }) {
  if (!c)
    return (
      <aside className="buscar-ficha vacia">
        <p className="tenue">Elija un candidato para ver su resumen y de qué fuentes salió.</p>
      </aside>
    );
  return (
    <aside className="buscar-ficha">
      <h2>{c.titulo}</h2>
      <p className="tenue">{c.autores.slice(0, 8).join("; ")}{c.autores.length > 8 ? " …" : ""}</p>
      <p>
        {[c.revista, c.anio, c.idioma.toUpperCase(), c.tipo].filter(Boolean).join(" · ")}
      </p>
      <div className="buscar-chips">
        {c.es_preprint && <span className="etiqueta aviso">preprint</span>}
        {c.tipo === "review" && <span className="etiqueta">revisión · no aplica</span>}
        {c.en_matriz && <span className="etiqueta">ya está en la matriz</span>}
        {c.paises.map((p) => (
          <span key={p} className="etiqueta">{p}</span>
        ))}
      </div>
      <p className="buscar-enlaces">
        {c.doi && (
          <a href={`https://doi.org/${c.doi}`} target="_blank" rel="noreferrer noopener">
            DOI {c.doi}
          </a>
        )}
        {c.url_oa && (
          <a href={c.url_oa} target="_blank" rel="noreferrer noopener">
            Texto abierto
          </a>
        )}
      </p>
      <h3>Resumen</h3>
      <p className="buscar-resumen">{c.resumen || "La fuente no trae resumen: hace falta el PDF."}</p>
      {c.palabras_clave.length > 0 && (
        <>
          <h3>Palabras clave</h3>
          <p>{c.palabras_clave.join(" · ")}</p>
        </>
      )}
      {c.evaluacion && (
        <>
          <h3>Encaje con sus columnas</h3>
          <p>
            <span className={`buscar-etiqueta et-${c.evaluacion.etiqueta}`}>{ETIQUETAS[c.evaluacion.etiqueta]}</span>{" "}
            <span className="tenue">{textoPuntaje(c.evaluacion)}</span>
            {c.evaluacion.razon && <span className="tenue"> · {c.evaluacion.razon}</span>}
            <span className="tenue"> · {c.evaluacion.etapa === "B" ? "con el texto completo" : "solo con metadatos y resumen"}</span>
          </p>
          <ul className="buscar-indicios">
            {c.evaluacion.celdas.map((x) => (
              <li key={x.columna} className={`celda-${x.estado.toLowerCase()}`}>
                <strong>{x.columna}</strong> <small className="tenue">{ESTADOS_CELDA[x.estado]}</small>
                {x.valor && <div>{x.valor}</div>}
                {x.frase && <q>{x.frase}</q>}
              </li>
            ))}
          </ul>
        </>
      )}
      <h3>Encontrado en</h3>
      <p>{c.fuentes.join(", ")}</p>
      {c.estado === "DESCARTADO" && c.motivo && <p className="tenue">Descartado: {c.motivo}</p>}
      <p className="buscar-aviso">
        Indicios de la fuente, sin verificar. Nada de esto entra a la matriz: los valores salen solo del PDF, con su
        página y su cita.
      </p>
    </aside>
  );
}

export function PanelBusqueda({ pid }: { pid: string }) {
  const cliente = useQueryClient();
  const escritura = useEscritura();
  const puedeBuscar = usePuedeBuscar();
  const config = useQuery({ queryKey: ["busqueda-config", pid], queryFn: () => api.busquedaConfiguracion(pid), staleTime: 60_000 });

  // Formulario (copia editable de la cadena inicial)
  const [conceptos, setConceptos] = useState<ConceptoEditable[] | null>(null);
  const [desde, setDesde] = useState(2020);
  const [hasta, setHasta] = useState("");
  const [idiomas, setIdiomas] = useState<string[]>(["en", "es", "pt"]);
  const [preprints, setPreprints] = useState(true);
  const [elegidas, setElegidas] = useState<string[] | null>(null);
  const [limite, setLimite] = useState(200);
  const [nombre, setNombre] = useState("");

  // Lista
  const [activa, setActiva] = useState<string | undefined>();
  const [estado, setEstado] = useState<EstadoCandidato | "">("");
  const [ocultarEnMatriz, setOcultarEnMatriz] = useState(false);
  const [texto, setTexto] = useState("");
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [abierto, setAbierto] = useState<string | undefined>();
  const [motivo, setMotivo] = useState("");
  const [izquierda, setIzquierda] = useState<"busqueda" | "columnas">("busqueda");
  const [orden, setOrden] = useState<OrdenCandidatos>("puntaje");
  const [exigir, setExigir] = useState<ExigirColumnas>("nada");
  const [previa, setPrevia] = useState<string[] | null>(null);
  // Solo lectura: se puede mirar con otro perfil guardado. Si la sincronización lo borró, se vuelve al predeterminado.
  const [perfilVisto, setPerfilVisto] = useState<string | undefined>();
  const perfiles = useQuery({ queryKey: ["perfiles", pid], queryFn: () => api.perfiles(pid), enabled: !escritura });
  const perfilId = !escritura && perfiles.data?.perfiles.some((p) => p.id === perfilVisto) ? perfilVisto : undefined;

  const formulario = conceptos ?? config.data?.consulta_inicial.conceptos.map(aEditable) ?? [];
  const fuentesElegidas = elegidas ?? config.data?.fuentes.filter((f) => f.utilizable).map((f) => f.id) ?? [];

  const busquedas = useQuery({
    queryKey: ["busquedas", pid],
    queryFn: () => api.busquedas(pid),
    refetchInterval: (q) => (q.state.data?.busquedas.some((b) => b.estado === "EN_CURSO") ? 2000 : false),
  });
  const lista = busquedas.data?.busquedas ?? [];
  const enCurso = lista.some((b) => b.estado === "EN_CURSO");
  const busquedaActiva = lista.find((b) => b.id === activa) ?? lista[0];

  const candidatos = useQuery({
    queryKey: ["candidatos", pid, activa, estado, ocultarEnMatriz, texto, orden, exigir, perfilId],
    queryFn: () =>
      api.candidatos(pid, {
        busqueda_id: activa,
        estado: estado || undefined,
        en_matriz: ocultarEnMatriz ? false : undefined,
        q: texto.trim() || undefined,
        orden,
        exigir,
        perfil_id: perfilId,
        cuantos: 500,
      }),
    refetchInterval: enCurso ? 3000 : false,
    placeholderData: (previo) => previo,
  });
  const filas = candidatos.data?.candidatos ?? [];
  const contadores = candidatos.data?.contadores ?? {};
  const seleccion = useMemo(() => filas.filter((c) => marcados.has(c.id)), [filas, marcados]);

  const iniciar = useMutation({
    mutationFn: () =>
      api.iniciarBusqueda(pid, {
        nombre,
        fuentes: fuentesElegidas,
        limite_por_fuente: limite,
        conceptos: formulario.map((c) => ({ nombre: c.nombre, terminos: terminosDe(c.texto), obligatorio: c.obligatorio })),
        filtros: {
          desde,
          hasta: hasta.trim() ? Number(hasta) : null,
          idiomas,
          incluir_preprints: preprints,
        },
      }),
    onSuccess: (b) => {
      setActiva(b.id);
      setMarcados(new Set());
      cliente.invalidateQueries({ queryKey: ["busquedas", pid] });
      cliente.invalidateQueries({ queryKey: ["candidatos", pid] });
    },
  });

  const reactivar = useMutation({
    mutationFn: (fuente: string) => api.reactivarFuente(pid, fuente),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["busqueda-config", pid] }),
  });

  const analizar = useMutation({
    mutationFn: () => api.analizarCandidatos(pid, seleccion.map((c) => c.id)),
    onSuccess: (r) => {
      cliente.invalidateQueries({ queryKey: ["candidatos", pid] }); // la lista se recalcula con lo hallado en el PDF
      cliente.invalidateQueries({ queryKey: ["vista-previa", pid] });
      setMarcados(new Set(r.resultados.filter((x) => x.estado === "ERROR" || x.estado === "SIN_COPIA_ABIERTA").map((x) => x.id)));
    },
  });

  const importar = useMutation({
    mutationFn: () => api.importarCandidatos(pid, seleccion.map((c) => c.id)),
    onSuccess: (r) => {
      cliente.invalidateQueries({ queryKey: ["candidatos", pid] });
      cliente.invalidateQueries({ queryKey: ["articulos", pid] }); // los PDF nuevos aparecen en «Nuevo» de Artículos
      // Quedan marcados solo los que no se pudieron importar, para reintentarlos o subirlos a mano.
      setMarcados(new Set(r.resultados.filter((x) => x.estado === "ERROR" || x.estado === "SIN_COPIA_ABIERTA").map((x) => x.id)));
    },
  });

  const decidir = useMutation({
    mutationFn: (v: { accion: "priorizar" | "descartar" | "reactivar" }) =>
      api.decidirCandidatos(pid, [...marcados], v.accion, v.accion === "descartar" ? motivo : undefined),
    onSuccess: (r) => {
      cliente.invalidateQueries({ queryKey: ["candidatos", pid] });
      setMarcados(new Set(Object.keys(r.rechazados)));
      setMotivo("");
    },
  });

  if (config.isLoading) return <p className="centro tenue">Cargando…</p>;
  if (config.error) return <p className="error centro">{(config.error as Error).message}</p>;
  const cfg = config.data!;
  const sinTerminos = formulario.some((c) => c.obligatorio && terminosDe(c.texto).length === 0);
  const todosMarcados = filas.length > 0 && filas.every((c) => marcados.has(c.id));
  const alternar = (id: string) =>
    setMarcados((m) => {
      const n = new Set(m);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const fichaCandidato = filas.find((c) => c.id === abierto);

  const exportar = async (formato: "csv" | "ris") => {
    const { blob, nombre } = await api.exportarCandidatos(pid, seleccion.map((c) => c.id), formato, perfilId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
  const perfilActivo = candidatos.data?.perfil;

  return (
    <div className="buscador">
      <div className="buscar-consulta" data-izq={izquierda}>
        <div className="segmentado" role="tablist" aria-label="Panel izquierdo">
          <button role="tab" aria-selected={izquierda === "busqueda"} className={izquierda === "busqueda" ? "activo" : ""} onClick={() => setIzquierda("busqueda")}>
            Búsqueda
          </button>
          <button role="tab" aria-selected={izquierda === "columnas"} className={izquierda === "columnas" ? "activo" : ""} onClick={() => setIzquierda("columnas")}>
            Columnas{perfilActivo ? ` (${perfilActivo.columnas.length})` : ""}
          </button>
        </div>
        {izquierda === "columnas" &&
          (escritura ? (
            <SelectorDeColumnas pid={pid} />
          ) : (
            <ColumnasEnLectura pid={pid} perfilId={perfilId} onPerfil={setPerfilVisto} />
          ))}
        {!escritura && (
          <section className="buscar-tarjeta">
            <header>
              <strong>{puedeBuscar ? "Buscar en la web" : "Copia de solo lectura"}</strong>
            </header>
            <p className="tenue">
              {puedeBuscar
                ? "Lo que busque aquí llega a su equipo con la próxima sincronización. Allí se prioriza, se descarta, se analiza y se importa."
                : "Las búsquedas, las decisiones y las importaciones se hacen en el equipo local y llegan aquí solas con la sincronización."}
            </p>
          </section>
        )}
        {puedeBuscar && (
          <>
            <section className="buscar-tarjeta">
              <header>
                <strong>Cadena de búsqueda</strong>
                <button
                  className="sin-borde"
                  onClick={() => setConceptos(cfg.consulta_inicial.conceptos.map(aEditable))}
                  title="Volver a la cadena inicial"
                >
                  Restablecer
                </button>
              </header>
              {formulario.map((c, i) => (
                <div key={c.nombre} className="buscar-concepto">
                  <label className="fila">
                    <input
                      type="checkbox"
                      checked={c.obligatorio}
                      onChange={(e) =>
                        setConceptos(formulario.map((x, j) => (j === i ? { ...x, obligatorio: e.target.checked } : x)))
                      }
                    />
                    <strong>{c.nombre}</strong>
                    <span className="tenue">{c.obligatorio ? "Y (obligatorio)" : "apagado"}</span>
                  </label>
                  <textarea
                    rows={Math.min(7, Math.max(2, terminosDe(c.texto).length))}
                    value={c.texto}
                    aria-label={`Términos de ${c.nombre}, uno por línea`}
                    onChange={(e) =>
                      setConceptos(formulario.map((x, j) => (j === i ? { ...x, texto: e.target.value } : x)))
                    }
                  />
                </div>
              ))}
              <p className="tenue">Un término por línea; los de un concepto se unen con O, y los conceptos con Y. «employee*» = prefijo.</p>
            </section>

            <section className="buscar-tarjeta">
              <header>
                <strong>Filtros</strong>
              </header>
              <div className="fila">
                <label>
                  Desde
                  <input type="number" min={1900} max={2100} value={desde} onChange={(e) => setDesde(Number(e.target.value))} />
                </label>
                <label>
                  Hasta
                  <input
                    type="number"
                    min={1900}
                    max={2100}
                    placeholder="hoy"
                    value={hasta}
                    onChange={(e) => setHasta(e.target.value)}
                  />
                </label>
              </div>
              <div className="fila">
                {IDIOMAS.map(([id, nombreIdioma]) => (
                  <label key={id} className="fila">
                    <input
                      type="checkbox"
                      checked={idiomas.includes(id)}
                      onChange={(e) => setIdiomas(e.target.checked ? [...idiomas, id] : idiomas.filter((x) => x !== id))}
                    />
                    {nombreIdioma}
                  </label>
                ))}
              </div>
              <label className="fila">
                <input type="checkbox" checked={preprints} onChange={(e) => setPreprints(e.target.checked)} />
                Incluir preprints (se marcan)
              </label>
            </section>

            <section className="buscar-tarjeta">
              <header>
                <strong>Fuentes</strong>
              </header>
              <ul className="buscar-fuentes">
                {cfg.fuentes.map((f) => {
                  const p = busquedaActiva?.progreso[f.id];
                  return (
                    <li key={f.id}>
                      <label className="fila">
                        <input
                          type="checkbox"
                          disabled={!f.utilizable}
                          checked={fuentesElegidas.includes(f.id)}
                          onChange={(e) =>
                            setElegidas(e.target.checked ? [...fuentesElegidas, f.id] : fuentesElegidas.filter((x) => x !== f.id))
                          }
                        />
                        <span className="nombre">{f.etiqueta}</span>
                        <span className="tenue">{f.sitio_id ? "requiere sesión" : "abierta"}</span>
                      </label>
                      {p && p.errores > 0 && <span className="buscar-errores">{p.errores} error{p.errores === 1 ? "" : "es"}</span>}
                      {f.desactivada && (
                        <div className="buscar-apagada" role="status">
                          <small className="error">Desactivada: {f.desactivada}</small>
                          <button className="sin-borde" onClick={() => reactivar.mutate(f.id)} disabled={reactivar.isPending}>
                            Reactivar
                          </button>
                        </div>
                      )}
                    </li>
                  );
                })}
                {cfg.no_disponibles.map((n) => (
                  <li key={n.id} className="no-disponible">
                    <label className="fila" title={n.motivo}>
                      <input type="checkbox" disabled checked={false} readOnly />
                      <span className="nombre">{n.etiqueta}</span>
                      <span className="tenue">no disponible</span>
                    </label>
                    <small className="tenue">{n.motivo}</small>
                  </li>
                ))}
              </ul>
              <div className="fila">
                <label>
                  Máx. por fuente
                  <select value={limite} onChange={(e) => setLimite(Number(e.target.value))}>
                    {LIMITES.map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="crece">
                  Nombre
                  <input value={nombre} placeholder="p. ej. Primera pasada" onChange={(e) => setNombre(e.target.value)} />
                </label>
              </div>
              <button
                className="primario"
                disabled={iniciar.isPending || enCurso || !fuentesElegidas.length || !idiomas.length || sinTerminos}
                onClick={() => iniciar.mutate()}
              >
                {enCurso ? "Buscando…" : "Buscar"}
              </button>
              {iniciar.error && <p className="error">{(iniciar.error as Error).message}</p>}
            </section>
          </>
        )}

        {busquedaActiva && <Progreso b={busquedaActiva} fuentes={cfg.fuentes} pid={pid} />}

        {!escritura && busquedaActiva && (
          <section className="buscar-tarjeta">
            <header>
              <strong>Cadena usada</strong>
              <span className="tenue">
                {busquedaActiva.consulta.filtros.desde}–{busquedaActiva.consulta.filtros.hasta ?? "hoy"}
              </span>
            </header>
            <p className="tenue">{busquedaActiva.cadena}</p>
          </section>
        )}

        {lista.length > 0 && (
          <section className="buscar-tarjeta">
            <header>
              <strong>Historial</strong>
              <button className="sin-borde" onClick={() => setActiva(undefined)} disabled={!activa}>
                Ver todos
              </button>
            </header>
            <ul className="buscar-historial">
              {lista.map((b) => (
                <li key={b.id}>
                  <button className={b.id === activa ? "activo" : ""} onClick={() => setActiva(b.id)}>
                    <span className="nombre">{b.nombre}</span>
                    <span className="tenue">
                      {hora(b.creada_en)} · {b.total_unicos} únicos
                    </span>
                    {b.origen === "nube" && <span className="tenue">en la web · aún no llega al equipo</span>}
                    {b.errores > 0 && <span className="buscar-errores">{b.errores}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {escritura && <SitiosConCredenciales sitios={cfg.sitios} />}
      </div>

      <section className="buscar-lista" aria-label="Candidatos">
        <div className="buscar-barra">
          <input
            type="search"
            placeholder="Buscar en título, resumen o DOI"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoCandidato | "")} aria-label="Estado">
            {ESTADOS.map(([v, t]) => (
              <option key={v} value={v}>
                {t}
                {v ? ` (${contadores[v] ?? 0})` : ""}
              </option>
            ))}
          </select>
          <select value={orden} onChange={(e) => setOrden(e.target.value as OrdenCandidatos)} aria-label="Orden">
            <option value="puntaje">Mejor encaje primero</option>
            <option value="reciente">Más recientes primero</option>
          </select>
          <select value={exigir} onChange={(e) => setExigir(e.target.value as ExigirColumnas)} aria-label="Exigir las imprescindibles">
            <option value="nada">Mostrar todos</option>
            <option value="sin_ausentes">Ocultar los que ya no pueden cumplirlas</option>
            <option value="confirmadas">Solo con todas las imprescindibles confirmadas</option>
          </select>
          <label className="fila">
            <input type="checkbox" checked={ocultarEnMatriz} onChange={(e) => setOcultarEnMatriz(e.target.checked)} />
            Ocultar los ya incluidos ({contadores.EN_MATRIZ ?? 0})
          </label>
          <span className="tenue">{candidatos.data?.total ?? 0} candidatos</span>
        </div>

        {seleccion.length > 0 && (
          <div className="buscar-seleccion" role="toolbar" aria-label="Acciones sobre la selección">
            <strong>{seleccion.length} seleccionados</strong>
            <button className="primario" onClick={() => setPrevia(seleccion.map((c) => c.id))}>
              Vista previa
            </button>
            <button onClick={() => exportar("csv")}>CSV</button>
            <button onClick={() => exportar("ris")}>RIS</button>
            {escritura && (
              <>
                <button
                  onClick={() => analizar.mutate()}
                  disabled={analizar.isPending || seleccion.length > MAX_IMPORTAR}
                  title={
                    seleccion.length > MAX_IMPORTAR
                      ? `Se analizan hasta ${MAX_IMPORTAR} a la vez`
                      : "Lee el texto completo del PDF abierto y busca en él los datos de las columnas. No importa el artículo: guarda solo los indicios con su página."
                  }
                >
                  {analizar.isPending ? "Leyendo…" : "Analizar texto completo"}
                </button>
                <button
                  onClick={() => importar.mutate()}
                  disabled={importar.isPending || seleccion.length > MAX_IMPORTAR}
                  title={
                    seleccion.length > MAX_IMPORTAR
                      ? `Se importan hasta ${MAX_IMPORTAR} a la vez: una descarga por decisión`
                      : "Baja el PDF de acceso abierto y lo deja en «Nuevo» en Artículos. No extrae nada."
                  }
                >
                  {importar.isPending ? "Importando…" : "Importar PDF"}
                </button>
                <button onClick={() => decidir.mutate({ accion: "priorizar" })} disabled={decidir.isPending}>
                  Priorizar
                </button>
                <input
                  placeholder="Motivo del descarte"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  aria-label="Motivo del descarte"
                />
                <button onClick={() => decidir.mutate({ accion: "descartar" })} disabled={decidir.isPending || !motivo.trim()}>
                  Descartar
                </button>
                <button onClick={() => decidir.mutate({ accion: "reactivar" })} disabled={decidir.isPending}>
                  Reactivar
                </button>
              </>
            )}
            <button className="sin-borde" onClick={() => setMarcados(new Set())}>
              Quitar selección
            </button>
            {decidir.error && <span className="error">{(decidir.error as Error).message}</span>}
            {decidir.data && Object.keys(decidir.data.rechazados).length > 0 && (
              <span className="tenue">
                {Object.keys(decidir.data.rechazados).length} no se pudieron cambiar (siguen marcados)
              </span>
            )}
          </div>
        )}

        {(analizar.data || analizar.error) && (
          <div className="buscar-importacion" role="status">
            <header>
              <strong>Texto completo</strong>
              <button className="sin-borde" onClick={() => analizar.reset()}>
                Cerrar
              </button>
            </header>
            {analizar.error && <p className="error">{(analizar.error as Error).message}</p>}
            <ul>
              {analizar.data?.resultados.map((x) => (
                <li key={x.id}>
                  <span className={`buscar-estado imp ${ETIQUETA_ANALISIS[x.estado][1]}`}>{ETIQUETA_ANALISIS[x.estado][0]}</span>
                  <span className="nombre" title={x.titulo}>{x.titulo || "—"}</span>
                  <small className="tenue">{x.mensaje}</small>
                </li>
              ))}
            </ul>
            <p className="tenue">Indicios con su página, sin verificar. No se guardó el texto ni el PDF, y no se tocó la matriz.</p>
          </div>
        )}

        {(importar.data || importar.error) && (
          <div className="buscar-importacion" role="status">
            <header>
              <strong>Importación</strong>
              <button className="sin-borde" onClick={() => importar.reset()}>
                Cerrar
              </button>
            </header>
            {importar.error && <p className="error">{(importar.error as Error).message}</p>}
            <ul>
              {importar.data?.resultados.map((x) => (
                <li key={x.id} className={`imp-${x.estado}`}>
                  <span className={`buscar-estado imp ${ETIQUETA_IMPORTACION[x.estado][1]}`}>{ETIQUETA_IMPORTACION[x.estado][0]}</span>
                  <span className="nombre" title={x.titulo}>{x.titulo || "—"}</span>
                  <small className="tenue">{x.mensaje}</small>
                </li>
              ))}
            </ul>
            <p className="tenue">Solo copias abiertas. Convertir y extraer es un paso aparte (cuesta tokens): se pide desde Artículos.</p>
          </div>
        )}

        {!filas.length ? (
          <p className="centro tenue">
            {candidatos.isLoading
              ? "Cargando…"
              : lista.length
                ? "Ningún candidato con estos filtros."
                : puedeBuscar
                  ? "Todavía no hay candidatos. Arme la cadena a la izquierda y pulse Buscar."
                  : "Todavía no hay búsquedas en la nube. Hágalas en el equipo local: llegan aquí solas."}
          </p>
        ) : (
          <div className="buscar-tabla-caja">
            <table className="buscar-tabla">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Seleccionar todos los visibles"
                      checked={todosMarcados}
                      onChange={(e) => setMarcados(e.target.checked ? new Set(filas.map((c) => c.id)) : new Set())}
                    />
                  </th>
                  <th>Título</th>
                  <th>Año</th>
                  <th>Encaje</th>
                  <th>Fuentes</th>
                  <th>Acceso</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((c) => (
                  <tr key={c.id} className={`${c.id === abierto ? "actual" : ""} ${c.estado === "DESCARTADO" ? "descartado" : ""}`}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Seleccionar «${c.titulo}»`}
                        checked={marcados.has(c.id)}
                        onChange={() => alternar(c.id)}
                      />
                    </td>
                    <td className="titulo" onClick={() => setAbierto(c.id)}>
                      <button className="sin-borde enlace" onClick={() => setAbierto(c.id)}>
                        {c.titulo}
                      </button>
                      <small className="tenue">{c.autores.slice(0, 3).join("; ")}{c.autores.length > 3 ? " et al." : ""}</small>
                      {c.en_matriz && <span className="etiqueta">ya está</span>}
                      {c.es_preprint && <span className="etiqueta aviso">preprint</span>}
                    </td>
                    <td>{c.anio ?? "—"}</td>
                    <td>
                      <BarraCobertura c={c} />
                    </td>
                    <td className="tenue">{c.fuentes.join(", ")}</td>
                    <td>{c.url_oa ? <a href={c.url_oa} target="_blank" rel="noreferrer noopener">abierto</a> : <span className="tenue">—</span>}</td>
                    <td>
                      <span className={`buscar-estado ${c.estado.toLowerCase()}`}>{c.estado.toLowerCase()}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {previa ? (
        <VistaPreviaDeFila pid={pid} ids={previa} perfilId={perfilId} onCerrar={() => setPrevia(null)} />
      ) : (
        <Ficha c={fichaCandidato} />
      )}
    </div>
  );
}

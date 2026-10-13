// Panel de artículos (sección 9.2): lista con casillas, estados, contadores, filtros, carga y extracción.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Dispatch,
  type SetStateAction,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import { api } from "../api";
import {
  acelerarAvance,
  enCurso,
  porcentajeVisible,
  useAvance,
} from "../avance";
import { useNavegacion } from "../navegacion";
import { BarraAvance } from "./BarraAvance";
import { Icono } from "./Icono";
import type {
  Articulo,
  EstadoArticulo,
  ModelosDeArticulo,
  ResultadoCarga,
  ResultadoEncolado,
} from "../tipos";

// «Extraer» acepta también un PDF Nuevo o Convirtiéndose: el servidor lo convierte primero y luego lo extrae.
const EXTRAIBLES: EstadoArticulo[] = [
  "NUEVO",
  "CONVIRTIENDO",
  "LISTO",
  "HEREDADO",
  "ERROR",
  "POR_REVISAR",
];
// Medido en una corrida real con los cuatro roles: Bibi 2022 (19 páginas) tardó 11 min; Kumar (8 páginas), 4 min.
// El gasto de la cuenta (ventana de 5 horas) se ve en la cabecera.
const MINUTOS_POR_ARTICULO = 11;

/** Número de Documento sugerido: el prefijo numérico del nombre del archivo («3. Bibi 2022.pdf» → 3). */
const documentoSugerido = (nombre: string): string =>
  /^\s*(\d+)\s*[.\-_ ]/.exec(nombre)?.[1] ?? "";

// Vía de identificación cuando no hay Covidence # (libro de códigos, trazabilidad.via_de_identificacion).
const VIAS_SIN_COVIDENCE = [
  "Otros métodos: búsqueda manual",
  "Otros métodos: bola de nieve",
  "Otros métodos: experto",
];
const ENTERO = /^[1-9]\d*$/;

// «claude-sonnet-5-5» → «Sonnet 5.5».
const nombreModelo = (id: string): string => {
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?/.exec(id);
  if (!m) return id;
  return `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}${m[3] ? `.${m[3]}` : ""}`;
};
const NOMBRE_ROL = {
  extractor: "Extractor",
  auditor: "Auditor",
  ciego: "Codificador ciego",
  conciliador: "Conciliador",
} as const;

/** Texto corto y detalle por rol de los modelos de la última extracción (portero, ADR 0005). */
const describirModelos = (
  m: ModelosDeArticulo,
): { corto: string; detalle: string } => {
  if (!m.registrado)
    return {
      corto: "modelos sin registro",
      detalle:
        "Extracción anterior al portero de modelos (ADR 0005): no guardó el modelo de cada llamada. " +
        "La configuración de entonces era Opus 5.5 en extractor, auditor y conciliador, y Sonnet 5.5 en el codificador ciego.",
    };
  const usados = new Set<string>();
  const lineas = (Object.keys(NOMBRE_ROL) as (keyof typeof NOMBRE_ROL)[]).map(
    (rol) => {
      const porModelo = Object.entries(m.roles[rol] ?? {});
      porModelo.forEach(([id]) => usados.add(nombreModelo(id)));
      const texto = porModelo.length
        ? porModelo
            .map(([id, n]) => `${nombreModelo(id)}${n > 1 ? ` ×${n}` : ""}`)
            .join(", ")
        : "sin llamadas";
      return `${NOMBRE_ROL[rol]}: ${texto}`;
    },
  );
  return { corto: [...usados].join(" · "), detalle: lineas.join("\n") };
};

const NOMBRE_ESTADO: Record<EstadoArticulo, string> = {
  HEREDADO: "Heredado",
  NUEVO: "Nuevo",
  CONVIRTIENDO: "Convirtiendo",
  LISTO: "Convertido",
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
  covidenceDe: Map<number, number>;
  conFilas: Set<string>;
  onAbrir?: () => void;
  // Artículos con el chulito: se extraen al pulsar «Extraer» y sus filas se marcan en la tabla.
  marcados: Set<string>;
  setMarcados: Dispatch<SetStateAction<Set<string>>>;
  // Si se da, la barra muestra un botón para ocultar el panel (barra lateral de PC y tableta).
  onOcultar?: () => void;
};

export function PanelArticulos({
  pid,
  articulos,
  contadores,
  documentoDe,
  covidenceDe,
  conFilas,
  onAbrir,
  marcados,
  setMarcados,
  onOcultar,
}: Props) {
  const qc = useQueryClient();
  const { actual, ir } = useNavegacion();
  const [filtro, setFiltro] = useState<EstadoArticulo | "">("");
  const [busqueda, setBusqueda] = useState("");
  const [resultado, setResultado] = useState<ResultadoCarga[] | null>(null);
  const [dialogo, setDialogo] = useState(false);
  const [documentos, setDocumentos] = useState<Record<string, string>>({});
  const [covidences, setCovidences] = useState<Record<string, string>>({});
  const [vias, setVias] = useState<Record<string, string>>({});
  const [rechazos, setRechazos] = useState<ResultadoEncolado[]>([]);
  const [fallo, setFallo] = useState<string | null>(null);
  const { porArticulo, enCola, detenidos, ahora } = useAvance(pid);
  const modelos = useQuery({
    queryKey: ["modelos", pid],
    queryFn: () => api.modelos(pid),
    refetchInterval: 20_000, // una extracción que termina aparece sin recargar
  });
  const conError = articulos.filter((a) => a.estado === "ERROR");
  // A medias sin trabajo activo (p. ej. la aplicación se cerró): «Continuar» los termina sin restablecerlos.
  const parados = articulos.filter((a) => detenidos.has(a.id));
  const continuar = useMutation({
    mutationFn: () => api.continuar(pid, parados.map((a) => a.id)),
    onSuccess: (r) => {
      setFallo(r.filter((x) => !x.encolado).map((x) => x.error).join(" · ") || null);
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
      qc.invalidateQueries({ queryKey: ["avance", pid] });
      acelerarAvance();
      window.dispatchEvent(new Event("extractor:abrir-monitor"));
    },
    onError: (e) => setFallo((e as Error).message),
  });
  const cancelar = useMutation({
    mutationFn: (articulo: string) => api.cancelar(pid, articulo),
    onSuccess: () => {
      setFallo(null);
      qc.invalidateQueries({ queryKey: ["avance", pid] });
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
    },
    onError: (e) => setFallo((e as Error).message),
  });
  const restablecer = useMutation({
    mutationFn: () => api.restablecer(pid, conError.map((a) => a.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
      qc.invalidateQueries({ queryKey: ["avance", pid] });
    },
    onError: (e) => setFallo((e as Error).message),
  });
  const archivo = useRef<HTMLInputElement>(null);

  const visibles = useMemo(
    () =>
      articulos
        .filter(
          (a) =>
            (!filtro || a.estado === filtro) &&
            a.nombre_archivo.toLowerCase().includes(busqueda.toLowerCase()),
        )
        .sort((a, b) =>
          a.nombre_archivo.localeCompare(b.nombre_archivo, "es", {
            numeric: true,
          }),
        ),
    [articulos, filtro, busqueda],
  );

  const cargar = useMutation({
    mutationFn: (archivos: File[]) => api.cargar(pid, archivos),
    onSuccess: (r) => {
      setResultado(r);
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
    },
  });

  // Clic en la etiqueta de estado de un artículo extraíble (Nuevo, Listo, Error o Heredado): empieza ya. Si está sin
  // convertir, el servidor lo convierte primero con MinerU y sigue solo; el avance sale en la cabecera y en el artículo.
  // Un artículo en Error se retoma con los datos de su último intento. Si faltan el Documento o el Covidence #
  // (ni el intento anterior ni la matriz los tienen), abre el diálogo de extracción para indicarlos.
  const extraerUno = useMutation({
    mutationFn: async (a: Articulo) => {
      if (a.estado === "ERROR") {
        const r = await api.retomar(pid, [a.id]);
        if (!r[0]?.sin_datos) return r;
      }
      const documento = documentoDeArticulo(a);
      const covidence = covidenceDe.get(Number(documento));
      if (!ENTERO.test(documento) || covidence === undefined) {
        setMarcados((m) => new Set([...m, a.id]));
        abrirDialogo([...extraibles.filter((x) => x.id !== a.id), a]);
        return null;
      }
      return api.extraer(
        pid,
        [
          {
            articulo_id: a.id,
            documento: Number(documento),
            covidence,
            via: "Covidence",
          },
        ],
        false,
      );
    },
    onSuccess: (r) => {
      if (r === null) return; // se abrió el diálogo
      setFallo(r.find((x) => !x.encolado)?.error ?? null);
      qc.invalidateQueries({ queryKey: ["avance", pid] });
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
      acelerarAvance();
      window.dispatchEvent(new Event("extractor:abrir-monitor")); // despliega el avance arriba
    },
    onError: (e) => setFallo((e as Error).message),
  });
  const DIRECTAS: EstadoArticulo[] = ["NUEVO", "LISTO", "ERROR", "HEREDADO"];

  // Etiqueta de cada artículo: mientras se procesa, en vez de su estado va el porcentaje de avance (en amarillo).
  const etiquetaDe = (
    a: Articulo,
  ): { texto: string; clase: string; titulo: string } => {
    const av = porArticulo.get(a.id);
    const pe = enCola.get(a.id);
    if (av && enCurso(av))
      return {
        texto: `${porcentajeVisible(av, ahora)} %`,
        clase: "estado-progreso",
        titulo: av.paso_texto,
      };
    if (pe) {
      const texto =
        pe.fase === "convirtiendo"
          ? "Conv. ⟳"
          : pe.fase === "esperando_mineru"
            ? "Espera"
            : pe.fase === "pausada"
              ? "Pausa"
              : `Cola ${pe.posicion}`;
      const titulo =
        pe.fase === "convirtiendo"
          ? "Convirtiendo el PDF con MinerU; la extracción sigue sola"
          : pe.fase === "esperando_mineru"
            ? "Esperando a MinerU (no responde)"
            : pe.fase === "pausada"
              ? "En pausa: se agotó el cupo de uso de Claude; se reanuda sola"
              : "En cola: empieza cuando termine la anterior";
      return { texto, clase: "estado-progreso", titulo };
    }
    if (detenidos.has(a.id))
      return {
        texto: `${NOMBRE_ESTADO[a.estado]} · detenido`,
        clase: `estado-${a.estado}`,
        titulo: "Quedó a medias sin trabajo activo: use «Continuar detenidos»",
      };
    return {
      texto: NOMBRE_ESTADO[a.estado],
      clase: `estado-${a.estado}`,
      titulo: "",
    };
  };

  const lanzar = useMutation({
    mutationFn: () =>
      api.extraer(
        pid,
        extraibles.map((a) => {
          const covidence = (covidences[a.id] ?? "").trim();
          return {
            articulo_id: a.id,
            documento: Number(documentos[a.id]),
            covidence: covidence ? Number(covidence) : null,
            via: covidence ? "Covidence" : (vias[a.id] ?? ""),
          };
        }),
        reextraer.length > 0,
      ),
    onSuccess: (r) => {
      const malos = r.filter((x) => !x.encolado);
      setRechazos(malos);
      const bien = new Set(
        r.filter((x) => x.encolado).map((x) => x.articulo_id),
      );
      setMarcados((m) => new Set([...m].filter((id) => !bien.has(id))));
      if (malos.length === 0) setDialogo(false);
      acelerarAvance();
      window.dispatchEvent(new Event("extractor:abrir-monitor"));
      qc.invalidateQueries({ queryKey: ["avance", pid] });
      qc.invalidateQueries({ queryKey: ["articulos", pid] });
    },
  });

  const seleccionados = articulos.filter((a) => marcados.has(a.id));
  const extraibles = seleccionados.filter((a) => EXTRAIBLES.includes(a.estado));
  const reextraer = extraibles.filter((a) => a.estado === "POR_REVISAR");
  const documentoDeArticulo = (a: Articulo): string =>
    documentos[a.id] ??
    (documentoDe.has(a.id)
      ? String(documentoDe.get(a.id))
      : documentoSugerido(a.nombre_archivo));
  const covidenceDeArticulo = (a: Articulo): string => {
    const c = covidenceDe.get(Number(documentoDeArticulo(a)));
    return c === undefined ? "" : String(c);
  };
  // Sin Covidence # hay que elegir otra vía: si no, el validador rechaza la fila (V06) y el modelo no puede arreglarlo.
  const identificacionValida = (a: Articulo): boolean => {
    const c = (covidences[a.id] ?? "").trim();
    return c ? ENTERO.test(c) : VIAS_SIN_COVIDENCE.includes(vias[a.id] ?? "");
  };
  const documentosValidos = extraibles.every(
    (a) => ENTERO.test(documentos[a.id] ?? "") && identificacionValida(a),
  );
  const todosVisiblesMarcados =
    visibles.length > 0 && visibles.every((a) => marcados.has(a.id));

  const abrirDialogo = (lista: Articulo[]) => {
    setRechazos([]);
    setDocumentos(
      Object.fromEntries(lista.map((a) => [a.id, documentoDeArticulo(a)])),
    );
    setCovidences(
      Object.fromEntries(lista.map((a) => [a.id, covidenceDeArticulo(a)])),
    );
    setVias({});
    setDialogo(true);
  };

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
        const pdfs = Array.from(e.dataTransfer.files).filter((f) =>
          f.name.toLowerCase().endsWith(".pdf"),
        );
        if (pdfs.length) cargar.mutate(pdfs);
      }}
    >
      <div className="barra">
        <strong className="titulo-seccion">Artículos</strong>
        <span className="tenue">{articulos.length}</span>
        {onOcultar && (
          <button
            className="sin-borde ocultar-lateral"
            onClick={onOcultar}
            title="Ocultar artículos"
            aria-label="Ocultar el panel de artículos"
          >
            ‹
          </button>
        )}
        <button
          className="primario"
          onClick={() => archivo.current?.click()}
          disabled={cargar.isPending}
          title="Añadir PDF (también puede arrastrarlos aquí)"
        >
          <Icono nombre="subir" tam={16} />
          {cargar.isPending ? "Cargando…" : "Añadir PDF"}
        </button>
        <input
          ref={archivo}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) =>
            e.target.files && cargar.mutate(Array.from(e.target.files))
          }
        />
      </div>
      <label className="buscar">
        <Icono nombre="buscar" tam={16} />
        <input
          placeholder="Buscar"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          aria-label="Buscar por nombre"
        />
      </label>
      <div className="contadores">
        <button
          className={filtro === "" ? "activo" : ""}
          onClick={() => setFiltro("")}
        >
          Todos {articulos.length}
        </button>
        {Object.entries(contadores)
          .filter(([, n]) => n > 0)
          .map(([estado, n]) => (
            <button
              key={estado}
              className={`estado-${estado} ${filtro === estado ? "activo" : ""}`}
              onClick={() => setFiltro(estado as EstadoArticulo)}
            >
              {NOMBRE_ESTADO[estado as EstadoArticulo] ?? estado} {n}
            </button>
          ))}
      </div>
      {fallo && (
        <div
          className="aviso-carga error"
          role="alert"
          onClick={() => setFallo(null)}
        >
          {fallo}
        </div>
      )}
      {resultado && (
        <div className="aviso-carga" onClick={() => setResultado(null)}>
          {resultado.map((r) => (
            <div key={r.nombre_archivo}>
              {r.error ? "✗" : r.duplicado ? "⧉" : "✓"} {r.nombre_archivo}
              {r.duplicado && (
                <span className="tenue"> · duplicado de {r.duplicado_de}</span>
              )}
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
                visibles.forEach((a) =>
                  todosVisiblesMarcados ? n.delete(a.id) : n.add(a.id),
                );
                return n;
              })
            }
          />
          Seleccionar todo
        </label>
        {parados.length > 0 && (
          <button
            className="continuar"
            disabled={continuar.isPending}
            title="Termina lo que quedó a medias: una conversión cortada se termina con MinerU; una extracción cortada se vuelve a lanzar con los datos de su último intento. No restablece nada."
            onClick={() => {
              const extraer = parados.filter((a) => a.estado !== "CONVIRTIENDO").length;
              const convertir = parados.length - extraer;
              if (
                window.confirm(
                  `Continuar ${parados.length} artículo(s) detenido(s):\n\n` +
                    (convertir ? `· ${convertir} terminan su conversión con MinerU (no gasta créditos).\n` : "") +
                    (extraer
                      ? `· ${extraer} vuelven a extraerse desde el principio con los datos de su último intento: la llamada al modelo no se puede retomar a medias. Gasta créditos de Claude (unos ${extraer * MINUTOS_POR_ARTICULO} min).\n`
                      : ""),
                )
              )
                continuar.mutate();
            }}
          >
            {continuar.isPending
              ? "Continuando…"
              : `Continuar detenidos (${parados.length})`}
          </button>
        )}
        {conError.length > 0 && (
          <button
            className="restablecer"
            disabled={restablecer.isPending}
            title="Reset: los artículos en Error vuelven a su estado anterior (Convertido, Heredado, Por revisar o Nuevo). No lanza extracciones ni gasta créditos."
            onClick={() => {
              if (
                window.confirm(
                  `Restablecer ${conError.length} artículo(s) en Error.\n\nVuelven a su estado anterior y se borra el mensaje de error; el intento fallido queda en el historial. No se lanza ninguna extracción.`,
                )
              )
                restablecer.mutate();
            }}
          >
            {restablecer.isPending
              ? "Restableciendo…"
              : `Restablecer errores (${conError.length})`}
          </button>
        )}
        <button
          disabled={extraibles.length === 0}
          onClick={() => abrirDialogo(extraibles)}
        >
          Extraer seleccionados{" "}
          {extraibles.length ? `(${extraibles.length})` : ""}
        </button>
      </div>
      <ul className="lista">
        {visibles.map((a) => (
          <li key={a.id} className={actual.articuloId === a.id ? "actual" : ""}>
            <input
              type="checkbox"
              checked={marcados.has(a.id)}
              onChange={() => alternar(a.id)}
              aria-label={`Seleccionar ${a.nombre_archivo}`}
            />
            <button
              className="nombre"
              onClick={() => abrir(a)}
              title={a.error?.mensaje ?? a.nombre_archivo}
            >
              <span className="recortar">{a.nombre_archivo}</span>
              <span className="tenue">
                {documentoDe.has(a.id)
                  ? `Doc. ${documentoDe.get(a.id)}`
                  : "Doc. —"}
                {a.paginas ? ` · ${a.paginas} p.` : ""}
                {conFilas.has(a.id) ? " · con filas extraídas" : ""}
              </span>
              {modelos.data?.[a.id] && (
                <span
                  className="tenue modelos"
                  title={describirModelos(modelos.data[a.id]).detalle}
                >
                  {describirModelos(modelos.data[a.id]).corto}
                </span>
              )}
            </button>
            {DIRECTAS.includes(a.estado) &&
            !enCola.has(a.id) &&
            !(porArticulo.has(a.id) && enCurso(porArticulo.get(a.id)!)) ? (
              <button
                type="button"
                className={`estado estado-${a.estado} accionable`}
                disabled={extraerUno.isPending}
                onClick={() => extraerUno.mutate(a)}
                title={`${a.estado === "NUEVO" ? "Clic: convertir con MinerU y extraer" : a.estado === "LISTO" ? "Convertido, falta extraer. Clic: extraer" : "Clic: extraer"} (unos ${MINUTOS_POR_ARTICULO} min)`}
              >
                {NOMBRE_ESTADO[a.estado]}
                <span className="accion-extraer"> ▶ Extraer</span>
              </button>
            ) : (
              <span
                className={`estado ${etiquetaDe(a).clase}`}
                title={etiquetaDe(a).titulo || undefined}
              >
                {etiquetaDe(a).texto}
              </span>
            )}
            <BarraAvance
              avance={porArticulo.get(a.id)}
              pendiente={enCola.get(a.id)}
              ahora={ahora}
              onCancelar={() => cancelar.mutate(a.id)}
            />
          </li>
        ))}
      </ul>
      {dialogo &&
        createPortal(
          <div
            className="velo"
            onMouseDown={(e) =>
              e.target === e.currentTarget && setDialogo(false)
            }
          >
            <div className="dialogo">
              <h3>Extraer {extraibles.length} artículo(s)</h3>
              <p>
                Estimación según una corrida real (19 páginas): unos{" "}
                {extraibles.length * MINUTOS_POR_ARTICULO} min en total. Se
                procesan de a uno, en segundo plano; el avance aparece en cada
                artículo. El gasto de la cuenta de Claude (ventana de 5 horas)
                se ve arriba, en la cabecera.
              </p>
              {extraibles.some(
                (a) => a.estado === "NUEVO" || a.estado === "CONVIRTIENDO",
              ) && (
                <p className="tenue">
                  {
                    extraibles.filter(
                      (a) =>
                        a.estado === "NUEVO" || a.estado === "CONVIRTIENDO",
                    ).length
                  }{" "}
                  sin convertir: se convierten primero con MinerU (unos 10 a 20
                  s por página) y después se extraen, sin pasos manuales.
                </p>
              )}
              <div className="dialogo-lista">
                {extraibles.map((a) => (
                  <label key={a.id} className="documento-fila">
                    <span className="recortar" title={a.nombre_archivo}>
                      {a.nombre_archivo}
                    </span>
                    <span className="documento-campo">
                      Documento
                      <input
                        type="number"
                        min={1}
                        inputMode="numeric"
                        value={documentos[a.id] ?? ""}
                        onChange={(e) =>
                          setDocumentos((d) => ({
                            ...d,
                            [a.id]: e.target.value,
                          }))
                        }
                        aria-label={`Número de Documento de ${a.nombre_archivo}`}
                      />
                    </span>
                    <span className="documento-campo">
                      Covidence #
                      <input
                        type="number"
                        min={1}
                        inputMode="numeric"
                        className={identificacionValida(a) ? "" : "invalido"}
                        value={covidences[a.id] ?? ""}
                        onChange={(e) =>
                          setCovidences((d) => ({
                            ...d,
                            [a.id]: e.target.value,
                          }))
                        }
                        aria-label={`Covidence # de ${a.nombre_archivo}`}
                      />
                    </span>
                    {!(covidences[a.id] ?? "").trim() && (
                      <select
                        className="documento-via"
                        value={vias[a.id] ?? ""}
                        onChange={(e) =>
                          setVias((v) => ({ ...v, [a.id]: e.target.value }))
                        }
                        aria-label={`Vía de identificación de ${a.nombre_archivo}`}
                      >
                        <option value="">Sin Covidence: elija la vía…</option>
                        {VIAS_SIN_COVIDENCE.map((v) => (
                          <option key={v} value={v}>
                            {v.replace("Otros métodos: ", "")}
                          </option>
                        ))}
                      </select>
                    )}
                  </label>
                ))}
              </div>
              <p className="tenue">
                Documento es el número del artículo en la columna A de la
                matriz; el Estudio se asigna solo. Covidence # es obligatorio si
                el artículo pasó por Covidence; si no, elija la vía por la que
                se identificó.
              </p>
              {reextraer.length > 0 && (
                <p className="aviso">
                  {reextraer.length} ya tienen filas por revisar: se
                  reemplazarán.
                </p>
              )}
              {seleccionados.length > extraibles.length && (
                <p className="tenue">
                  {seleccionados.length - extraibles.length} seleccionados no se
                  pueden extraer ahora (ya están en cola o extrayéndose).
                </p>
              )}
              {rechazos.map((r) => (
                <p key={r.articulo_id} className="error">
                  {r.error}
                </p>
              ))}
              {lanzar.isError && (
                <p className="error">{(lanzar.error as Error).message}</p>
              )}
              <div className="botones">
                <button onClick={() => setDialogo(false)}>Cancelar</button>
                <button
                  className="primario"
                  disabled={
                    lanzar.isPending ||
                    !documentosValidos ||
                    extraibles.length === 0
                  }
                  onClick={() => lanzar.mutate()}
                >
                  {lanzar.isPending
                    ? "Enviando…"
                    : `Extraer ${extraibles.length} artículo(s)`}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </section>
  );
}

import type {
  Articulo,
  CeldaDetalle,
  CeldaResumen,
  Columna,
  Documento,
  AvanceRespuesta,
  EstadoServicios,
  EventoRegistro,
  Fila,
  ModelosDeArticulo,
  Protocolo,
  Proyecto,
  ResultadoCarga,
  ResultadoContinuar,
  ResultadoEncolado,
  AccionCandidatos,
  AjustesNube,
  Busqueda,
  Capacidades,
  CatalogoColumnas,
  ColumnaElegida,
  ListaPerfiles,
  Perfil,
  ResultadoAnalisis,
  ResultadoImportacion,
  VistaPreviaRespuesta,
  ConfiguracionBusqueda,
  ConsultaBusqueda,
  FiltroCandidatos,
  ListadoCandidatos,
  ResultadoDecision,
  CorridaSync,
  EstadoSync,
  ExtraccionCompleta,
  ResultadoProbar,
  ResumenExtraccion,
  EstadoRestauracion,
  LectoresNube,
  PlanRestauracion,
} from "./tipos";

export class ErrorApi extends Error {
  constructor(
    public estado: number,
    mensaje: string,
  ) {
    super(mensaje);
  }
}

async function pedir<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const r = await fetch(`/api/v1${ruta}`, {
    credentials: "same-origin",
    ...opciones,
  });
  if (!r.ok) {
    let detalle = r.statusText;
    try {
      detalle = (await r.json()).detail ?? detalle;
    } catch {
      /* respuesta sin JSON */
    }
    throw new ErrorApi(
      r.status,
      typeof detalle === "string" ? detalle : JSON.stringify(detalle),
    );
  }
  return r.json() as Promise<T>;
}

const json = (cuerpo: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo),
});

const poner = (cuerpo: unknown): RequestInit => ({
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo),
});

const p = (pid: string) => `/proyectos/${pid}`;
const sync = (pid: string) => `${p(pid)}/sincronizacion`;

export const api = {
  capacidades: () => pedir<Capacidades>("/capacidades"),
  // Pestaña «Buscar» (ADR 0011): solo en el equipo local.
  busquedaConfiguracion: (pid: string) => pedir<ConfiguracionBusqueda>(`${p(pid)}/busqueda/configuracion`),
  iniciarBusqueda: (
    pid: string,
    datos: { nombre: string; fuentes: string[]; limite_por_fuente: number } & Partial<ConsultaBusqueda>,
  ) => pedir<Busqueda>(`${p(pid)}/busquedas`, json(datos)),
  busquedas: (pid: string) => pedir<{ busquedas: Busqueda[] }>(`${p(pid)}/busquedas`),
  busqueda: (pid: string, id: string) => pedir<Busqueda>(`${p(pid)}/busquedas/${id}`),
  cancelarBusqueda: (pid: string, id: string) =>
    pedir<{ cancelando: boolean }>(`${p(pid)}/busquedas/${id}/cancelar`, { method: "POST" }),
  candidatos: (pid: string, f: FiltroCandidatos = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== "") q.set(k, String(v));
    return pedir<ListadoCandidatos>(`${p(pid)}/candidatos?${q}`);
  },
  decidirCandidatos: (pid: string, ids: string[], accion: AccionCandidatos, motivo?: string) =>
    pedir<ResultadoDecision>(`${p(pid)}/candidatos/decision`, json({ ids, accion, motivo })),
  reactivarFuente: (pid: string, fuente: string) =>
    pedir<{ reactivada: boolean }>(`${p(pid)}/busqueda/fuentes/${fuente}/reactivar`, { method: "POST" }),
  analizarCandidatos: (pid: string, ids: string[]) =>
    pedir<{ resultados: ResultadoAnalisis[] }>(`${p(pid)}/candidatos/analizar`, json({ ids })),
  importarCandidatos: (pid: string, ids: string[]) =>
    pedir<{ resultados: ResultadoImportacion[] }>(`${p(pid)}/candidatos/importar`, json({ ids })),
  // Columnas a elección, perfiles guardados, vista previa y exportación de la selección.
  busquedaColumnas: (pid: string) => pedir<CatalogoColumnas>(`${p(pid)}/busqueda/columnas`),
  perfiles: (pid: string) => pedir<ListaPerfiles>(`${p(pid)}/busqueda/perfiles`),
  guardarPerfil: (pid: string, nombre: string, columnas: ColumnaElegida[], predeterminado: boolean) =>
    pedir<Perfil>(`${p(pid)}/busqueda/perfiles`, poner({ nombre, columnas, predeterminado })),
  borrarPerfil: (pid: string, id: string) =>
    pedir<{ borrado: boolean }>(`${p(pid)}/busqueda/perfiles/${id}`, { method: "DELETE" }),
  // Son lecturas (la nube las admite): sin `perfil_id` se usa el perfil predeterminado.
  vistaPrevia: (pid: string, ids: string[], perfil_id?: string) =>
    pedir<VistaPreviaRespuesta>(`${p(pid)}/candidatos/vista-previa`, json({ ids, perfil_id })),
  exportarCandidatos: async (pid: string, ids: string[], formato: "csv" | "ris", perfil_id?: string) => {
    const r = await fetch(`/api/v1${p(pid)}/candidatos/exportar`, {
      ...json({ ids, formato, perfil_id }),
      credentials: "same-origin",
    });
    if (!r.ok) throw new ErrorApi(r.status, r.statusText);
    return { blob: await r.blob(), nombre: `candidatos.${formato}` };
  },
  salir: () => pedir<{ salio: boolean }>("/auth/salir", { method: "POST" }),
  // Todas las extracciones de un artículo (más recientes primero) y una completa, con las 25 columnas.
  extracciones: (pid: string, articulo: string) =>
    pedir<ResumenExtraccion[]>(`${p(pid)}/extracciones?articulo=${articulo}`),
  extraccion: (pid: string, id: string) => pedir<ExtraccionCompleta>(`${p(pid)}/extracciones/${id}`),
  // Panel «Configuración › Nube» (solo en el equipo local).
  nube: {
    ajustes: (pid: string) => pedir<AjustesNube>(`${sync(pid)}/ajustes`),
    guardar: (pid: string, cambios: Partial<Omit<AjustesNube, "token_guardado" | "sede">> & { token?: string }) =>
      pedir<AjustesNube>(`${sync(pid)}/ajustes`, poner(cambios)),
    probar: (pid: string) => pedir<ResultadoProbar>(`${sync(pid)}/probar`, { method: "POST" }),
    ahora: (pid: string) => pedir<{ aceptado: boolean }>(`${sync(pid)}/ahora`, { method: "POST" }),
    reenviar: (pid: string) => pedir<{ aceptado: boolean }>(`${sync(pid)}/reenviar`, { method: "POST" }),
    verificar: (pid: string) =>
      pedir<{ ok: boolean; por_subir: number; por_eliminar: number; archivos: number; detalle: string }>(
        `${sync(pid)}/verificar`,
        { method: "POST" },
      ),
    estado: (pid: string) => pedir<EstadoSync>(`${sync(pid)}/estado`),
    corridas: (pid: string) => pedir<CorridaSync[]>(`${sync(pid)}/corridas`),
    // «Descargar proyecto desde la nube»: plan (sin tocar nada), arranque en segundo plano y avance.
    restaurarPlan: (pid: string) => pedir<PlanRestauracion>(`${sync(pid)}/restaurar/plan`, { method: "POST" }),
    restaurar: (pid: string, reemplazar: boolean) =>
      pedir<{ aceptado: boolean }>(`${sync(pid)}/restaurar`, json({ reemplazar })),
    restaurarEstado: (pid: string) => pedir<EstadoRestauracion>(`${sync(pid)}/restaurar/estado`),
    // Quién puede entrar al visor de la nube.
    lectores: (pid: string) => pedir<LectoresNube>(`${sync(pid)}/lectores`),
    altaLector: (pid: string, correo: string) => pedir<LectoresNube>(`${sync(pid)}/lectores`, json({ correo })),
    bajaLector: (pid: string, correo: string) =>
      pedir<LectoresNube>(`${sync(pid)}/lectores?correo=${encodeURIComponent(correo)}`, { method: "DELETE" }),
  },
  proyectos: () => pedir<Proyecto[]>("/proyectos"),
  columnas: (pid: string) => pedir<Columna[]>(`${p(pid)}/normas/columnas`),
  protocolo: (pid: string) => pedir<Protocolo>(`${p(pid)}/normas/protocolo`),
  filas: (pid: string) =>
    pedir<{ total: number; filas: Fila[] }>(
      `${p(pid)}/matriz/filas?pagina=1&tam=500`,
    ),
  celda: (pid: string, estudio: number, clave: string) =>
    pedir<CeldaDetalle>(
      `${p(pid)}/matriz/filas/${estudio}/celdas/${encodeURIComponent(clave)}`,
    ),
  aprobar: (pid: string, estudio: number, clave: string, motivo?: string) =>
    pedir<CeldaResumen>(
      `${p(pid)}/matriz/filas/${estudio}/celdas/${encodeURIComponent(clave)}/aprobar`,
      json({ motivo: motivo || null }),
    ),
  corregir: (
    pid: string,
    estudio: number,
    clave: string,
    valor: unknown,
    motivo: string,
    estado_dato?: string,
  ) =>
    pedir<CeldaResumen>(
      `${p(pid)}/matriz/filas/${estudio}/celdas/${encodeURIComponent(clave)}/corregir`,
      json({ valor, motivo, estado_dato: estado_dato || null }),
    ),
  rechazar: (pid: string, estudio: number, clave: string, motivo: string) =>
    pedir<CeldaResumen>(
      `${p(pid)}/matriz/filas/${estudio}/celdas/${encodeURIComponent(clave)}/rechazar`,
      json({ motivo }),
    ),
  articulos: (pid: string) =>
    pedir<{ articulos: Articulo[]; contadores: Record<string, number> }>(
      `${p(pid)}/articulos`,
    ),
  cargar: (pid: string, archivos: File[]) => {
    const datos = new FormData();
    archivos.forEach((a) => datos.append("archivos", a));
    return pedir<ResultadoCarga[]>(`${p(pid)}/articulos`, {
      method: "POST",
      body: datos,
    });
  },
  estado: () => pedir<EstadoServicios>("/estado"),
  avance: (pid: string) =>
    pedir<AvanceRespuesta>(`${p(pid)}/extracciones/avance`),
  extraer: (
    pid: string,
    articulos: {
      articulo_id: string;
      documento: number;
      covidence: number | null;
      via: string;
    }[],
    confirmar_reextraccion: boolean,
  ) =>
    pedir<ResultadoEncolado[]>(
      `${p(pid)}/extracciones`,
      json({ articulos, confirmar_reextraccion }),
    ),
  // «Extraer» sobre un Error: el servidor reutiliza los datos del último intento.
  retomar: (pid: string, articulos: string[]) =>
    pedir<ResultadoEncolado[]>(`${p(pid)}/extracciones/retomar`, json({ articulos })),
  // Saca de la cola un pedido que todavía no empezó a extraer (en cola, convirtiendo o esperando a MinerU).
  cancelar: (pid: string, articulo: string) =>
    pedir<{ cancelado: boolean }>(`${p(pid)}/extracciones/${articulo}/cancelar`, { method: "POST" }),
  // Qué modelo atendió cada rol en la última extracción de cada artículo.
  modelos: (pid: string) =>
    pedir<Record<string, ModelosDeArticulo>>(`${p(pid)}/extracciones/modelos`),
  // Termina lo que quedó a medias sin trabajo activo, sin restablecerlo (conversión o extracción cortadas).
  continuar: (pid: string, articulos: string[] | null = null) =>
    pedir<ResultadoContinuar[]>(`${p(pid)}/extracciones/continuar`, json({ articulos })),
  // Reset de los artículos en Error: vuelven a su estado previo; no lanza extracciones ni gasta créditos.
  restablecer: (pid: string, articulos: string[] | null = null) =>
    pedir<Articulo[]>(`${p(pid)}/articulos/restablecer`, json({ articulos })),
  registro: (desde: number | null) =>
    pedir<{ eventos: EventoRegistro[]; siguiente: number }>(
      `/registro${desde === null ? "" : `?desde=${desde}`}`,
    ),
  documento: (pid: string, articuloId: string) =>
    pedir<Documento>(`${p(pid)}/articulos/${articuloId}/documento`),
  // Genera el Excel de la matriz completa (heredadas y extraídas) y devuelve la ruta de descarga.
  exportar: (pid: string) =>
    pedir<{ id: string; filas_heredadas: number; filas_extraidas: number; descarga: string }>(
      `${p(pid)}/exportaciones`,
      { method: "POST" },
    ),
  // Excel de la matriz generado al vuelo (sirve en la nube de solo lectura, que no guarda exportaciones).
  urlExcel: (pid: string) => `/api/v1${p(pid)}/exportaciones/matriz.xlsx`,
  urlPdf: (pid: string, articuloId: string) =>
    `/api/v1${p(pid)}/articulos/${articuloId}/pdf`,
};

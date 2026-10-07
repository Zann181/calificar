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
  Protocolo,
  Proyecto,
  ResultadoCarga,
  ResultadoEncolado,
  Usuario,
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

const p = (pid: string) => `/proyectos/${pid}`;

export const api = {
  quien: () => pedir<Usuario>("/sesion"),
  entrar: (correo: string, clave: string) =>
    pedir<Usuario>("/sesion", json({ correo, clave })),
  salir: () => pedir<{ ok: boolean }>("/sesion", { method: "DELETE" }),
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
  registro: (desde: number | null) =>
    pedir<{ eventos: EventoRegistro[]; siguiente: number }>(
      `/registro${desde === null ? "" : `?desde=${desde}`}`,
    ),
  documento: (pid: string, articuloId: string) =>
    pedir<Documento>(`${p(pid)}/articulos/${articuloId}/documento`),
  urlPdf: (pid: string, articuloId: string) =>
    `/api/v1${p(pid)}/articulos/${articuloId}/pdf`,
};

// Tipos de la API (sección 10). Se reemplazarán por los generados con openapi-typescript.

export type Usuario = { id: string; correo: string; nombre: string; rol: string };
export type Proyecto = { id: string; nombre: string };

export type Columna = {
  clave: string;
  encabezado_excel: string;
  letra: string;
  posicion: number;
  tipo_de_dato: string;
  obligatorio: boolean;
  valores_permitidos: string[] | null;
  requiere_evidencia: boolean;
  nivel_de_registro: string;
  nota_encabezado: string;
  es_numerica: boolean;
};

export type EstadoRevision =
  | "SIN_EVIDENCIA"
  | "PENDIENTE"
  | "POR_CONFIRMAR"
  | "NO_VERIFICABLE"
  | "APROBADA"
  | "CORREGIDA"
  | "RECHAZADA";

export type NivelAncla = "VERIFICADA" | "VERIFICADA_CON_CORRECCION" | "POR_CONFIRMAR" | "NO_VERIFICABLE";

export type CeldaResumen = {
  valor: unknown;
  estado_dato: string | null;
  tipo_valor: "LITERAL" | "CODIFICADO" | "INFERIDO" | "FALTANTE" | null;
  estado_revision: EstadoRevision;
  nivel_ancla: NivelAncla | null;
  evidencias: number;
  discrepancia: boolean;
  hallazgo: boolean;
  nota_heredada: boolean;
  fuera_de_vocabulario: boolean;
};

export type Fila = {
  id: string;
  estudio: number;
  documento: number;
  origen: "HEREDADA" | "EXTRAIDA";
  articulo_id: string | null;
  aprobada: boolean;
  version_desactualizada: boolean;
  celdas: Record<string, CeldaResumen>;
};

export type Ancla = {
  nivel: NivelAncla;
  bloque_id: string | null;
  pagina: number | null;
  rect: [number, number, number, number] | null;
  similitud: number;
  nota: string;
};

export type Evidencia = {
  pagina_pdf: number;
  ubicacion: string;
  cita_textual: string;
  leido_de_figura: boolean;
  fila_tabla: string | null;
  columna_tabla: string | null;
  bloque_id: string | null;
  ancla: Ancla | null;
};

export type CeldaDetalle = Omit<CeldaResumen, "evidencias" | "nota_heredada"> & {
  estudio: number;
  documento: number;
  origen: Fila["origen"];
  clave: string;
  articulo_id: string | null;
  evidencias: Evidencia[];
  inferencia: { regla: string; razonamiento: string; premisas: string[] } | null;
  nota_heredada: { autor: string | null; texto: string } | null;
  hallazgos: { auditor?: string; veredicto?: string; hallazgo?: string; evidencia?: unknown }[];
  discrepancias: { columna: string; fuente_1: string; fuente_2: string; valor_adoptado: string }[];
  historial: {
    autor: string;
    fecha: string;
    accion: string;
    valor_anterior: unknown;
    valor_nuevo: unknown;
    motivo: string | null;
  }[];
};

export type EstadoArticulo =
  | "HEREDADO"
  | "NUEVO"
  | "CONVIRTIENDO"
  | "LISTO"
  | "EN_COLA"
  | "EXTRAYENDO"
  | "AUDITANDO"
  | "POR_REVISAR"
  | "APROBADO"
  | "ERROR"
  | "EXCLUIDO";

export type Articulo = {
  id: string;
  nombre_archivo: string;
  estado: EstadoArticulo;
  paginas: number | null;
  error: { paso: string; mensaje: string } | null;
  excluido_motivo: string | null;
};

export type ResultadoCarga = {
  nombre_archivo: string;
  articulo_id: string | null;
  duplicado: boolean;
  duplicado_de: string | null;
  error: string | null;
};

export type Documento = {
  paginas: { numero: number; ancho_pt: number; alto_pt: number }[];
  bloques: { id: string; pagina: number; tipo: string; rect: [number, number, number, number]; texto: string }[];
};

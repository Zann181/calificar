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
  guia?: GuiaDeColumna;
};

/** Lo que el libro de códigos dice de una columna (derivado en el backend; nada se copia a mano). */
export type GuiaDeColumna = {
  para_que_sirve?: string;
  relacion_con_otras_columnas?: string;
  naturaleza?: string;
  escala_de_medicion?: string;
  nivel_recomendado?: string;
  donde_buscar?: string;
  como_se_extrae?: string[];
  /** Texto, lista o, en algunas columnas, un diccionario (categoría → significado o árbol de decisión). */
  regla_de_decision?: unknown;
  reglas_de_codificacion?: unknown;
  formato?: string;
  codigo_si_falta?: string;
  tratamiento_del_dato_faltante?: string;
  ejemplo?: { estudio?: number; cita_en_matriz?: string; valor_registrado?: unknown; explicacion?: string };
  campos_de_trazabilidad?: { campo: string; descripcion: string }[];
};

export type Protocolo = {
  principios_de_veracidad: string[];
  precedencia_de_fuentes: string[];
  faltantes: Record<string, string>;
  como_se_construye_cada_fila: {
    unidad_de_analisis?: string;
    jerarquia?: string;
    regla_para_abrir_una_fila_nueva: string[];
  };
};

export type InferenciaFila = { columna: string; valor?: unknown; regla_aplicada?: string; razonamiento?: string };

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
  /** Trazabilidad de la fila tal como la entregó el extractor (sin las evidencias, que van por celda). */
  trazabilidad_fila: Record<string, unknown> & { inferencias?: InferenciaFila[] };
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

export type EventoRegistro = { id: number; t: string; nivel: string; origen: string; mensaje: string };

export type EstadoServicios = { componentes: { id: string; nombre: string; estado: "ok" | "aviso" | "error"; detalle: string }[] };

export type AvanceExtraccion = {
  extraccion_id: string;
  articulo_id: string;
  estado: string;
  progreso: number;
  paso: string;
  paso_texto: string;
  hasta: number;
  segundos_tipicos: number;
  paso_desde: string;
  iniciada_en: string;
  terminada_en: string | null;
  error: string | null;
  inactiva: boolean;
  fallida: boolean;
  costo_usd: number;
  estudios: number[];
  acuerdo: number | null;
};

// Pedido que aún no tiene extracción en marcha: en cola, esperando a MinerU o convirtiendo el PDF.
export type PendienteDeExtraccion = {
  articulo_id: string;
  posicion: number;
  fase: "en_cola" | "convirtiendo" | "esperando_mineru";
  desde: string;
};

export type AvanceRespuesta = { extracciones: AvanceExtraccion[]; en_cola: PendienteDeExtraccion[] };

export type ResultadoEncolado = { articulo_id: string; encolado: boolean; posicion?: number; error: string | null };

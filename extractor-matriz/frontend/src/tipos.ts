// Tipos de la API (sección 10). Se reemplazarán por los generados con openapi-typescript.

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
  /** La calcula el programa, no el extractor (libro v2.3). */
  es_derivada?: boolean;
  /** Versión del libro que agregó la columna (null en las 54 originales). */
  agregada_en_version?: string | null;
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

// Uso de la cuenta de Claude en una ventana (5 horas o 7 días): % usado y cuándo se restablece.
export type VentanaCuenta = { usado: number; restablece: string | null };
export type CuentaClaude = {
  cinco_horas: VentanaCuenta | null;
  siete_dias: VentanaCuenta | null;
  bloqueada: boolean;
  actualizado: string;
};
export type EstadoServicios = {
  componentes: { id: string; nombre: string; estado: "ok" | "aviso" | "error"; detalle: string }[];
  cuenta: CuentaClaude | null;
};

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
  fase: "en_cola" | "convirtiendo" | "esperando_mineru" | "pausada";
  desde: string;
  reanuda?: string | null; // solo en pausa: cuándo se reintenta
};

export type AvanceRespuesta = {
  extracciones: AvanceExtraccion[];
  en_cola: PendienteDeExtraccion[];
  detenidos?: string[]; // a medias sin trabajo activo: el botón «Continuar detenidos» los termina
};

// Resultado de «Continuar detenidos» por artículo: terminar la conversión o volver a encolar la extracción.
export type ResultadoContinuar = ResultadoEncolado & { accion: "convertir" | "extraer" };

export type ResultadoEncolado = {
  articulo_id: string;
  encolado: boolean;
  posicion?: number;
  error: string | null;
  sin_datos?: boolean; // retomar: el intento anterior no tiene datos completos
};

// Modelos de la última extracción de un artículo (ADR 0005): por rol, {modelo: llamadas}.
export type RolDelModelo = "extractor" | "auditor" | "ciego" | "conciliador";
export type ModelosDeArticulo = {
  extraccion_id: string;
  estado: string;
  iniciada_en: string;
  registrado: boolean; // false: extracción anterior al portero, sin modelo por llamada
  roles: Record<RolDelModelo, Record<string, number> | null>;
};

// ---- Nube de solo lectura (ADR 0009) ----
export type Capacidades = {
  modo: "local" | "nube";
  escritura: boolean;
  autenticado: boolean;
  lector: string | null;
  acceso: string | null;
  busqueda?: boolean; // la pestaña «Buscar» (falta en servidores antiguos)
  /** Se pueden lanzar búsquedas (también en la web, ADR 0012). */
  puede_buscar?: boolean;
};

export type ResumenExtraccion = {
  id: string;
  articulo_id: string;
  estado: string;
  estudios: number[];
  iniciada_en: string;
  terminada_en: string | null;
  acuerdo: number | null;
  iteraciones_validador: number;
  hallazgos: number;
  hallazgos_pendientes: number;
  anclas: number;
  error: string | null;
  paso_fallido: string | null;
  costo_usd: number;
};

export type AnclaExtraccion = {
  estudio: number;
  columna: string;
  indice_evidencia: number;
  nivel: string;
  similitud: number;
  bloque_id: string | null;
  pagina: number | null;
  rect: [number, number, number, number] | null;
  rango: [number, number] | null;
  leido_de_figura: boolean;
  nota: string;
};

export type HallazgoExtraccion = {
  estudio: number | null;
  columna: string;
  auditor: string;
  veredicto: string;
  detalle: string;
  evidencia_propuesta: unknown;
  resolucion: string | null;
  estado: string;
};

export type ExtraccionCompleta = ResumenExtraccion & {
  version_libro_id: string;
  datos_del_equipo: Record<string, unknown>;
  salida: { fila: Record<string, unknown>; trazabilidad?: Record<string, unknown> }[];
  codificacion_ciega: Record<string, unknown>[];
  anclas: AnclaExtraccion[];
  hallazgos: HallazgoExtraccion[];
  errores_validador: string[];
  avisos_validador: string[];
  uso_tokens: Record<
    string,
    {
      llamadas: number;
      entrada: number;
      cache_escritura: number;
      cache_lectura: number;
      salida: number;
      costo_usd: number;
      segundos: number;
      modelos?: Record<string, number>;
    }
  >;
};

export type OpcionesNube = {
  pdf: boolean;
  documento: boolean;
  matriz: boolean;
  historial: boolean;
  extraccion: boolean;
  crudo: boolean;
  excel: boolean;
  busqueda: boolean;
};

export type AjustesNube = {
  url: string;
  token_guardado: boolean;
  automatico: boolean;
  pausado: boolean;
  agrupar_s: number;
  reconciliar_s: number;
  opciones: OpcionesNube;
  sede: string;
};

export type EstadoSync = {
  estado: "sin_configurar" | "pausado" | "sincronizado" | "subiendo" | "sin_conexion" | "error";
  detalle: string;
  hace_s: number | null;
  hechos: number;
  total: number;
  fase: string;
  pendiente: boolean;
  revision: number | null;
  cambios_pendientes: number;
};

export type CorridaSync = {
  id: string;
  iniciada_en: string;
  terminada_en: string | null;
  motivo: string;
  estado: string;
  sobres: number;
  eliminados: number;
  archivos: number;
  bytes_enviados: number;
  revision: number | null;
  detalle: string;
};

export type ResultadoProbar = {
  ok: boolean;
  pasos: { nombre: string; ok: boolean; detalle: string }[];
};

export type PlanRestauracion = {
  faltan: number;
  distintos: number;
  solo_locales: number;
  archivos_faltan: number;
  archivos_distintos: number;
  hay_conflictos: boolean;
  vacio: boolean;
  ejemplos_distintos: string[];
  ejemplos_solo_locales: string[];
};

export type EstadoRestauracion = {
  estado: "ninguna" | "restaurando" | "ok" | "error";
  hechos: number;
  total: number;
  fase: string;
  detalle: string;
  resultado: { agregados: number; archivos: number; bytes: number; reemplazados: number; solo_locales: number } | null;
};

export type LectoresNube = { fijos: string[]; agregados: { correo: string; agregado_en: string }[] };

// ---- Pestaña «Buscar» (ADR 0011) ------------------------------------------------------------------------------
export type ConceptoBusqueda = { nombre: string; terminos: string[]; obligatorio: boolean };
export type FiltrosBusqueda = { desde: number; hasta: number | null; idiomas: string[]; incluir_preprints: boolean };
export type ConsultaBusqueda = { conceptos: ConceptoBusqueda[]; filtros: FiltrosBusqueda };
export type FuenteBusqueda = {
  id: string;
  etiqueta: string;
  sitio_id: string | null;
  sesion: "NO_CONECTADA" | "VIGENTE" | "VENCIDA" | null;
  utilizable: boolean;
  desactivada: string | null; // el motivo, si se apagó sola porque el sitio cambió de forma
};
export type FuenteNoDisponible = { id: string; etiqueta: string; motivo: string };
export type SitioConCredenciales = {
  id: string;
  nombre: string;
  portal_url: string;
  hosts: string[];
  acceso: string[];
  bases: string[];
  notas: string;
  sesion: "NO_CONECTADA" | "VIGENTE" | "VENCIDA";
  limite: { bytes_por_ventana: number; ventana_s: number; pausa_min_s: number; concurrencia: number };
};
export type ConfiguracionBusqueda = {
  consulta_inicial: ConsultaBusqueda;
  fuentes: FuenteBusqueda[];
  no_disponibles: FuenteNoDisponible[];
  sitios: SitioConCredenciales[];
};
export type ProgresoFuente = {
  estado: "PENDIENTE" | "BUSCANDO" | "LISTA" | "ERROR" | "OMITIDA";
  encontrados: number;
  nuevos: number;
  errores: number;
  ultimo_error: string | null;
};
export type Busqueda = {
  id: string;
  nombre: string;
  /** «nube»: lanzada en la web y todavía sin llegar al equipo. */
  origen: "equipo" | "nube";
  estado: "EN_CURSO" | "TERMINADA" | "TERMINADA_CON_ERRORES" | "CANCELADA";
  creada_en: string;
  terminada_en: string | null;
  fuentes: string[];
  consulta: ConsultaBusqueda;
  cadena: string;
  progreso: Record<string, ProgresoFuente>;
  total_unicos: number;
  errores: number;
  limite_por_fuente: number;
};
export type EstadoCandidato = "NUEVO" | "PRIORIZADO" | "DESCARTADO" | "IMPORTADO";
export type Candidato = {
  id: string;
  titulo: string;
  doi: string | null;
  anio: number | null;
  revista: string;
  autores: string[];
  paises: string[];
  resumen: string;
  palabras_clave: string[];
  idioma: string;
  tipo: string;
  url_oa: string | null;
  es_preprint: boolean;
  fuentes: string[];
  estado: EstadoCandidato;
  motivo: string | null;
  en_matriz: boolean;
  articulo_id: string | null;
  evaluacion?: Evaluacion | null;
};
export type ListadoCandidatos = {
  candidatos: Candidato[];
  total: number;
  contadores: Record<string, number>;
  perfil: Perfil;
};
// Fase 2: columnas a elección, con prioridad (plan «Buscar», sección 5).
export type Nivel = "M" | "R" | "T" | "X";
export type Prioridad = "IMPRESCINDIBLE" | "IMPORTANTE" | "DESEABLE";
export type EstadoCelda = "METADATO" | "INDICIO" | "PENDIENTE" | "AUSENTE" | "NO_APLICA";
export type EtiquetaCandidato = "PROBABLE" | "DUDOSO" | "SIN_DATOS" | "INCOMPLETO" | "NO_APLICA";
export type ColumnaCatalogo = {
  clave: string;
  encabezado: string;
  grupo: string;
  nivel: Nivel;
  vocabulario: number;
  derivada: boolean;
  elegible: boolean;
};
export type CatalogoColumnas = { columnas: ColumnaCatalogo[]; grupos: string[]; niveles: Record<Nivel, string> };
export type ColumnaElegida = { clave: string; prioridad: Prioridad };
export type Perfil = { id: string; nombre: string; predeterminado: boolean; columnas: ColumnaElegida[] };
export type ListaPerfiles = { perfiles: Perfil[]; activo: Perfil; inicial: Perfil };
export type CeldaPrevia = {
  columna: string;
  estado: EstadoCelda;
  valor: string | null;
  origen: string;
  frase: string | null;
  prioridad: Prioridad;
};
export type Evaluacion = {
  puntaje: number;
  maximo: number;
  etiqueta: EtiquetaCandidato;
  razon: string | null;
  etapa: "A" | "B"; // A: metadatos y resumen · B: además, el texto completo del PDF
  peso_total: number;
  celdas: CeldaPrevia[];
};
// Etapa B: leer el texto completo de un PDF abierto (no importa el artículo ni extrae con el modelo).
export type EstadoAnalisis = "ANALIZADO" | "TEXTO_INSUFICIENTE" | "SIN_COPIA_ABIERTA" | "ERROR";
export type ResultadoAnalisis = { id: string; titulo: string; estado: EstadoAnalisis; mensaje: string; con_indicio: number };
export type VistaPreviaRespuesta = { perfil: Perfil; sin_verificar: true; candidatos: Candidato[] };
export type OrdenCandidatos = "reciente" | "puntaje";
export type ExigirColumnas = "nada" | "sin_ausentes" | "confirmadas";
export type FiltroCandidatos = {
  estado?: EstadoCandidato;
  busqueda_id?: string;
  q?: string;
  orden?: OrdenCandidatos;
  exigir?: ExigirColumnas;
  perfil_id?: string;
  en_matriz?: boolean;
  desde?: number;
  cuantos?: number;
};
export type AccionCandidatos = "priorizar" | "descartar" | "reactivar";
export type ResultadoDecision = { cambiados: Candidato[]; rechazados: Record<string, string> };
// Fase 3: importar el PDF abierto de un candidato al flujo de Artículos (no extrae ni toca la matriz).
export type EstadoImportacion = "IMPORTADO" | "YA_ESTABA" | "SIN_COPIA_ABIERTA" | "RECHAZADO" | "ERROR";
export type ResultadoImportacion = {
  id: string;
  titulo: string;
  estado: EstadoImportacion;
  mensaje: string;
  articulo_id: string | null;
};
export const MAX_IMPORTAR = 10;

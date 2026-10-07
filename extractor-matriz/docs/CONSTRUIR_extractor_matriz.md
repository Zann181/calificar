# Especificación de construcción: Extractor de matriz felicidad y desempeño

Versión 1.0 · 2026-09-30 · Responsable del dominio: Pablo Andrés Erazo Muñoz, PhD

Este documento es la especificación para construir el programa. Está escrito para que un desarrollador o un agente de código lo implemente sin tomar decisiones de dominio por su cuenta. Donde algo no está definido, la instrucción es **detenerse y preguntar**, no suponer.

---

## 0. Reglas para quien construye

1. **El libro de códigos es la norma.** Las reglas de extracción, las columnas, los vocabularios y las validaciones salen de `recursos/Libro_de_codigos_extraccion_v2.json`. No se copian reglas al código ni se escriben las 54 columnas a mano: se generan desde el libro.
2. **No se reescriben los insumos existentes.** `validar_extraccion.py` y `escribir_matriz.py` se usan tal como están, a través de adaptadores. Si hace falta cambiarlos, se propone el cambio al responsable del dominio.
3. **Un dato sin ubicación comprobable no entra como verificado.** Esta es la propiedad central del sistema; toda decisión técnica se subordina a ella.
4. **DDD con monolito modular.** Seis contextos delimitados, cada uno con capas de dominio, aplicación, puertos y adaptadores. Un contexto no lee las tablas de otro: se comunican por casos de uso o por eventos.
5. **Cada fase termina con sus pruebas de aceptación en verde** (sección 12). No se avanza con pruebas pendientes.
6. **Idioma.** El código usa el lenguaje ubicuo en español (sección 3). Los identificadores van sin tildes (`Articulo`, `Extraccion`); los textos de la interfaz, con tildes.
7. **Qué hacer si algo contradice este documento.** Si un resultado de la fase F0 (por ejemplo, el sistema de coordenadas de MinerU) contradice lo supuesto aquí, se registra en `docs/decisiones/` como ADR y se consulta antes de seguir.

---

## 1. Qué hace el programa

| Función | Descripción |
| --- | --- |
| Cargar PDF | Arrastrar o seleccionar uno o varios PDF; se rechazan duplicados por huella SHA-256 |
| Ver estados | Panel con el estado de cada artículo y contadores por estado |
| Extraer | Casillas por artículo, Seleccionar todo y Extraer seleccionados; ejecución en segundo plano |
| Llenar la matriz | La extracción escribe las filas de efecto con las 54 columnas del libro de códigos |
| Sustentar cada dato | Cada celda guarda página, bloque, rectángulo y cita literal; si es inferida, la regla y el razonamiento |
| Nota por celda | Al pasar el cursor, una ficha muestra la evidencia, el tipo de valor y los veredictos de auditoría |
| Ir al lugar exacto | Clic en la celda: el visor abre la página y resalta el bloque y las palabras citadas |
| Volver | Una pila de navegación restaura la celda, el desplazamiento y la página anteriores |
| Revisar | Aprobar, corregir (con motivo obligatorio) o rechazar celdas; historial por celda |
| Exportar | Excel con el formato actual, comentarios de fuente, colores y hojas Trazabilidad y Auditoria |

---

## 2. Pila tecnológica (decisiones cerradas)

| Capa | Tecnología | Versión mínima |
| --- | --- | --- |
| Lenguaje del servidor | Python | 3.12 |
| API | FastAPI, Pydantic v2, Uvicorn | FastAPI 0.115 |
| Persistencia | PostgreSQL, SQLAlchemy 2 (estilo tipado), Alembic | PostgreSQL 16 |
| Cola y trabajadores | Dramatiq con Redis | Redis 7 |
| Archivos | Almacenamiento compatible con S3; MinIO en local | |
| Conversión de PDF | MinerU (backend `pipeline`), envuelto en un servicio HTTP propio | MinerU 3.4 |
| Modelo de lenguaje | API de Claude mediante el SDK oficial `anthropic` | |
| Coincidencia de texto | rapidfuzz | 3.x |
| Excel | openpyxl (a través de `escribir_matriz.py`) | |
| Interfaz | React 18, TypeScript, Vite | |
| Grilla | AG Grid Community (licencia MIT) | |
| Visor PDF | pdfjs-dist | 4.x |
| Estado del cliente | TanStack Query para datos del servidor; Zustand para navegación y selección | |
| Tiempo real | WebSocket (FastAPI) | |
| Pruebas | pytest, pytest-asyncio, Testcontainers (PostgreSQL y Redis), Vitest, Playwright | |
| Calidad | ruff, mypy (modo estricto en `domain/`), ESLint, Prettier | |
| Despliegue | Docker Compose (etapas 1 y 2); manifiestos de Kubernetes solo en etapa 3 | |

---

## 3. Lenguaje ubicuo

Estos términos son los nombres de clases, tablas y campos. No se usan sinónimos.

| Término | Significado |
| --- | --- |
| Proyecto | Una revisión sistemática, con su libro de códigos y su matriz |
| Artículo | Un PDF cargado en la biblioteca de un proyecto |
| Documento estructurado | La salida normalizada de MinerU: páginas, bloques y tablas |
| Bloque | Unidad de contenido de una página, con id estable `pNN-bMM`, tipo, rectángulo y texto |
| Libro de códigos | Documento JSON normativo; se versiona (`VersionDelLibro`) |
| Documento (número) | Número del artículo en la matriz (columna A); no es el número del nombre del archivo |
| Estudio | Número único de la fila de efecto (columna B) |
| Fila de efecto | Una fila de la matriz: un par felicidad y desempeño en una muestra |
| Celda | Valor de una columna en una fila de efecto |
| Evidencia | Lugar del artículo que sustenta una celda: página, bloque, cita literal |
| Ancla | Evidencia comprobada por el sistema: bloque, rectángulo y rango de caracteres |
| Inferencia | Valor que el artículo no dice literalmente, deducido con una regla del libro |
| Discrepancia | Contradicción dentro del propio artículo |
| Hallazgo | Observación de un auditor o del codificador ciego sobre una celda |
| Veredicto | Resultado de auditar una celda: CONFIRMADO, REFUTADO, NO_VERIFICABLE |
| Trabajo | Unidad de ejecución en segundo plano (convertir o extraer un artículo) |

---

## 4. Estructura del repositorio

```
extractor-matriz/
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── docs/
│   ├── decisiones/                 # ADR numerados: 0001-coordenadas-mineru.md, ...
│   └── glosario.md                 # copia viva de la sección 3
├── recursos/
│   ├── Libro_de_codigos_extraccion_v2.json
│   ├── validar_extraccion.py
│   ├── escribir_matriz.py
│   └── fixtures/                   # PDF y salidas de MinerU para pruebas (Kumar, Singh)
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── app/
│   │   ├── config.py               # Settings de Pydantic; lee variables de entorno
│   │   ├── main.py                 # arma FastAPI: routers, WebSocket, manejo de errores
│   │   ├── workers.py              # punto de entrada de Dramatiq
│   │   ├── compartido/             # núcleo compartido
│   │   │   ├── dominio.py          # Entidad, ObjetoDeValor, EventoDeDominio, ErrorDeDominio
│   │   │   ├── ids.py              # tipos de identificador (UUID)
│   │   │   ├── unidad_de_trabajo.py
│   │   │   ├── outbox.py           # tabla outbox y despachador
│   │   │   └── normalizacion.py    # norm() idéntica a la de validar_extraccion.py
│   │   └── contextos/
│   │       ├── biblioteca/
│   │       │   ├── dominio/        # Articulo, EstadoArticulo, DocumentoEstructurado, Bloque, Rect
│   │       │   ├── aplicacion/     # CargarPDF, ConvertirArticulo, ExcluirArticulo
│   │       │   ├── puertos.py      # ConversorPDF, AlmacenDeArchivos, RepositorioDeArticulos
│   │       │   ├── adaptadores/    # mineru_http.py, s3.py, repositorio_sql.py
│   │       │   └── api.py          # router /articulos
│   │       ├── normas/
│   │       ├── extraccion/
│   │       ├── matriz/
│   │       ├── orquestacion/
│   │       └── exportacion/
│   └── tests/
│       ├── unitarias/              # dominio y aplicación, sin red ni base de datos
│       ├── integracion/            # adaptadores con Testcontainers
│       └── doradas/                # Kumar y Singh contra resultados esperados
├── servicio-mineru/
│   ├── Dockerfile
│   └── app.py                      # POST /convertir → content_list, middle.json, imágenes
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── app/                    # rutas, disposición responsiva, proveedores
        ├── compartido/             # cliente API tipado, WebSocket, componentes base
        └── funciones/
            ├── articulos/          # panel, carga, selección, estados
            ├── matriz/             # grilla, columnas desde el libro, colores
            ├── evidencia/          # ficha emergente, detalle de inferencias
            ├── visor/              # PDF.js, resaltado, franja de contexto
            ├── navegacion/         # pila de retorno, migas, atajos
            └── revision/           # aprobar, corregir, tarjetas para teléfono
```

Regla de dependencias, verificada con `import-linter` en integración continua:

- `dominio/` no importa nada de `aplicacion/`, `adaptadores/`, SQLAlchemy, FastAPI ni `anthropic`.
- `aplicacion/` importa `dominio/` y `puertos.py`, nunca `adaptadores/`.
- Un contexto importa de otro solo sus eventos públicos (`<contexto>/eventos.py`).

---

## 5. Modelo de dominio por contexto

Notación: `Tipo` en mayúscula inicial; `?` indica opcional. Todos los agregados tienen `id: UUID`, `proyecto_id: UUID`, `creado_en` y `actualizado_en`.

### 5.1 Biblioteca

**Agregado `Articulo`**

- Campos:
  - `nombre_archivo: str`
  - `huella_sha256: str`, única por proyecto
  - `clave_almacen: str`
  - `paginas: int?`
  - `estado: EstadoArticulo`
  - `documento_estructurado_id: UUID?`
  - `error: DetalleError?` con `paso`, `mensaje` y `fecha`
  - `excluido_motivo: str?`
- `EstadoArticulo` toma uno de estos valores:
  - `HEREDADO`
  - `NUEVO`
  - `CONVIRTIENDO`
  - `LISTO`
  - `EN_COLA`
  - `EXTRAYENDO`
  - `AUDITANDO`
  - `POR_REVISAR`
  - `APROBADO`
  - `ERROR`
  - `EXCLUIDO`
- Transiciones permitidas, y ninguna otra; una transición inválida lanza `TransicionInvalida`:

```
NUEVO → CONVIRTIENDO → LISTO → EN_COLA → EXTRAYENDO → AUDITANDO → POR_REVISAR → APROBADO
HEREDADO → EN_COLA
POR_REVISAR → EN_COLA            (reextraer; exige confirmación en la API)
APROBADO → EN_COLA               (reextraer; exige confirmación y motivo)
cualquiera excepto EXCLUIDO → ERROR
ERROR → estado del paso que falló (reintento)
NUEVO | LISTO | HEREDADO | ERROR → EXCLUIDO
EXCLUIDO → NUEVO | HEREDADO      (reactivar)
EN_COLA → LISTO | HEREDADO       (cancelar)
```

**Objeto de valor `DocumentoEstructurado`** (se persiste como JSONB)

- `paginas: list[Pagina]`, donde cada `Pagina` tiene `numero` (base 1), `ancho_pt` y `alto_pt`.
- `bloques: list[Bloque]`. Cada `Bloque` tiene:
  - `id`, con formato `p{pagina:02d}-b{orden:02d}` y el orden de lectura de MinerU;
  - `pagina`;
  - `tipo`: `titulo`, `parrafo`, `tabla`, `figura`, `ecuacion`, `leyenda`, `nota` u `otro`;
  - `rect`: `Rect(x0, y0, x1, y1)` en puntos PDF con origen arriba a la izquierda;
  - `texto`;
  - `texto_norm`;
  - `tabla: Tabla?`.
- `Tabla` tiene `html`, `celdas: list[CeldaTabla]` y `es_imagen: bool`. Cada `CeldaTabla` tiene `fila`, `columna`, `texto`, `etiqueta_fila` y `etiqueta_columna`.
- `texto_norm` usa `compartido/normalizacion.norm()`, que debe dar exactamente el mismo resultado que `norm()` de `validar_extraccion.py`. Una prueba unitaria compara ambas sobre 50 cadenas.

**Eventos:** `ArticuloCargado`, `ArticuloConvertido`, `ConversionFallida`, `ArticuloExcluido`.

### 5.2 Normas

**Agregado `VersionDelLibro`**

- `version: str` (por ejemplo, "2.1")
- `contenido: dict` (el JSON completo)
- `hash: str`
- `activa: bool`: solo una activa por proyecto
- `publicada_en`

**Servicio de dominio `CatalogoDeColumnas`.** Deriva de `contenido`, para cada columna:

- `clave`, `encabezado_excel`, `letra`, `posicion`;
- `tipo_de_dato`, `obligatorio`, `valores_permitidos`;
- `requiere_evidencia`, `nivel_de_registro`;
- `nota_encabezado`, el mismo texto de las notas del Excel.

Todo lo que necesite saber columnas (grilla, validación, exportación) lo obtiene de aquí.

**Evento:** `LibroPublicado`. Al recibirlo, Matriz marca las filas extraídas con otra versión como `version_desactualizada = true`.

### 5.3 Extracción

**Agregado `Extraccion`**, uno por intento sobre un artículo:

- `articulo_id`, `version_libro_id`
- `estado`: `EXTRAYENDO`, `VALIDANDO`, `ANCLANDO`, `AUDITANDO`, `CONCILIANDO`, `COMPLETADA` o `FALLIDA`
- `estudios_reservados: list[int]`
- `salida: list[dict]`, con el formato de `esquema_de_salida` del libro y cada evidencia extendida con `bloque_id`
- `codificacion_ciega: list[dict]`
- `anclas: list[Ancla]`
- `hallazgos: list[Hallazgo]`
- `acuerdo_campos_criticos: float?`
- `iteraciones_validador: int`
- `uso_tokens: dict`, por rol
- `iniciada_en`, `terminada_en`

**Objeto de valor `Ancla`**

- `estudio: int`, `columna: str`, `indice_evidencia: int`
- `bloque_id: str`, `pagina: int`, `rect: Rect`, `rango: (inicio, fin)?`
- `nivel`: `VERIFICADA`, `VERIFICADA_CON_CORRECCION`, `POR_CONFIRMAR` o `NO_VERIFICABLE`
- `similitud: float`
- `leido_de_figura: bool`

**Objeto de valor `Hallazgo`**

- `estudio`, `columna`
- `auditor`: `AUDITOR_EVIDENCIA`, `CODIFICADOR_CIEGO` o `CONCILIADOR`
- `veredicto`
- `detalle`, `evidencia_propuesta?`, `resolucion?`
- `estado`: `PENDIENTE` o `RESUELTO`

**Eventos:** `ExtraccionCompletada`, `ExtraccionFallida`, `CitaNoVerificable`.

### 5.4 Matriz

**Agregado `FilaDeEfecto`**

- `estudio: int`, único por proyecto; se reserva al encolar
- `documento: int`
- `articulo_id: UUID?`
- `origen`: `HEREDADA` o `EXTRAIDA`
- `version_libro_id`, `version_desactualizada: bool`
- `celdas: dict[clave, Celda]`
- `trazabilidad: dict`, con los campos de `trazabilidad_por_fila` del libro que no son por celda

**Entidad `Celda`**

- `clave`
- `valor: Json`
- `estado_dato`: `No indica`, `No indica (no significativo)`, `No aplica` o nulo
- `tipo_valor`: `LITERAL`, `CODIFICADO`, `INFERIDO` o `FALTANTE`
- `evidencias: list[Evidencia]`, con referencia a `Ancla`
- `inferencia: Inferencia?`, con `regla`, `razonamiento` y `premisas`
- `estado_revision`: `SIN_EVIDENCIA`, `PENDIENTE`, `POR_CONFIRMAR`, `NO_VERIFICABLE`, `APROBADA`, `CORREGIDA` o `RECHAZADA`
- `historial: list[CambioDeCelda]`, cada uno con `autor`, `fecha`, `accion`, `valor_anterior`, `valor_nuevo` y `motivo`

**Invariantes, verificadas en el dominio con pruebas unitarias:**

1. No se puede aprobar una celda `NO_VERIFICABLE` ni `POR_CONFIRMAR` sin un `motivo`.
2. Corregir exige `motivo` y deja el valor anterior en el historial.
3. Una fila pasa a aprobada solo si todas sus celdas numéricas están en `APROBADA` o `CORREGIDA`.
4. `estudio` no se repite en el proyecto; lo garantiza una restricción única en la base de datos y una reserva atómica al encolar.
5. El valor de una celda con `valores_permitidos` pertenece a esa lista, validada contra `CatalogoDeColumnas`.

**Eventos:** `FilaEscrita`, `CeldaAprobada`, `CeldaCorregida`, `CeldaRechazada`, `FilaAprobada`.

### 5.5 Orquestación (contexto de soporte)

**Agregado `Trabajo`**

- `tipo`: `CONVERTIR` o `EXTRAER`
- `articulo_id`
- `estado`: `EN_COLA`, `EJECUTANDO`, `COMPLETADO`, `FALLIDO` o `CANCELADO`
- `paso_actual`, `progreso` (de 0 a 100), `intentos`, `max_intentos = 3`, `error?`

Escucha `ArticuloCargado` y encola `CONVERTIR`. `EXTRAER` lo encola el caso de uso `ExtraerSeleccionados`. Los reintentos usan espera exponencial de 30 s, 2 min y 8 min.

### 5.6 Exportación (solo lectura)

Arma, desde Matriz y Extracción, el JSON de entrada de `escribir_matriz.py` y la lista de auditoría, y ejecuta el script. No tiene agregado.

---

## 6. Puertos y adaptadores

```python
class ConversorPDF(Protocol):
    def convertir(self, pdf: bytes, nombre: str) -> DocumentoEstructurado: ...

class ModeloDeLenguaje(Protocol):
    def completar(self, *, rol: str, sistema: list[BloqueDeTexto], mensajes: list[Mensaje],
                  max_tokens: int) -> RespuestaModelo: ...   # texto + uso de tokens

class AlmacenDeArchivos(Protocol):
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...
    def leer(self, clave: str) -> bytes: ...
    def url_temporal(self, clave: str, segundos: int = 900) -> str: ...

class ValidadorDeExtraccion(Protocol):
    def validar(self, salida: list[dict], libro: dict, pdf: bytes | None) -> ResultadoValidacion: ...
    # ResultadoValidacion: errores: list[str], avisos: list[str]

class EscritorDeMatriz(Protocol):
    def escribir(self, salida: list[dict], libro: dict, matriz_base: bytes,
                 auditoria: list[dict]) -> bytes: ...

class BusDeEventos(Protocol):
    def publicar(self, evento: EventoDeDominio) -> None: ...   # escribe en la outbox
```

| Puerto | Adaptador de producción | Adaptador de prueba |
| --- | --- | --- |
| ConversorPDF | `MineruHttp`: llama a `servicio-mineru` y normaliza (sección 7) | `ConversorFijo`: lee salidas guardadas en `recursos/fixtures/` |
| ModeloDeLenguaje | `ClaudeApi`: SDK `anthropic`, caché de instrucciones en el bloque del libro | `ModeloGrabado`: responde desde grabaciones por hash del mensaje |
| AlmacenDeArchivos | `S3` (MinIO en local) | `EnMemoria` |
| ValidadorDeExtraccion | `ScriptValidador`: escribe temporales y ejecuta `recursos/validar_extraccion.py`; clasifica las líneas `ERROR` y `AVISO` | el mismo, porque es determinista |
| EscritorDeMatriz | `ScriptEscritor`: ejecuta `recursos/escribir_matriz.py` | el mismo |
| Repositorios | SQLAlchemy sobre PostgreSQL | en memoria |

**Sobre `bloque_id` y el validador.** El esquema del libro v2.1 no admite `bloque_id` dentro de la evidencia (`additionalProperties: false`). Por eso `ScriptValidador` quita `bloque_id` de una copia antes de validar. Cuando el libro publique una versión que lo admita, se elimina ese paso.

---

## 7. Servicio MinerU y normalización (M3)

**Servicio `servicio-mineru`.** Es un contenedor aparte, que puede ir en un nodo con GPU.

- `POST /convertir`, con un archivo multipart, devuelve un zip con la salida cruda de MinerU (`content_list.json`, `middle.json` e imágenes).
- `GET /salud` devuelve la versión de MinerU y el backend en uso.

**Adaptador `MineruHttp`.** Convierte la salida cruda en `DocumentoEstructurado`:

1. Toma el orden de lectura y la página de cada bloque. `page_idx` es de base 0: se suma 1.
2. Convierte el rectángulo a puntos PDF con origen arriba a la izquierda. **La fórmula exacta la fija el ADR 0001 al cerrar la F0.** Hay que comprobar si MinerU entrega coordenadas en puntos o normalizadas de 0 a 1000, dibujando 20 rectángulos sobre las páginas de Kumar y Singh. Hasta cerrar ese ADR, M3 no se da por terminado.
3. Asigna `id = p{pagina:02d}-b{orden:02d}` según el orden de lectura dentro de la página. Es estable: reconvertir el mismo PDF con la misma versión de MinerU produce los mismos ids, y hay una prueba que lo verifica.
4. Tablas: parsea el HTML y rellena `celdas`, donde `etiqueta_fila` es el texto de la primera columna de esa fila y `etiqueta_columna` el de la fila de encabezado. Si MinerU marca la tabla como imagen, o no hay HTML, `es_imagen = true`.
5. Calcula `texto_norm`.
6. Guarda el documento como JSONB y la salida cruda en el almacén, en `crudo/<articulo_id>.zip`.

---

## 8. Motor de extracción (M4) y anclaje (M5)

### 8.1 Texto etiquetado

El modelo recibe el artículo con los identificadores de bloque:

```
[p03-b07 | parrafo] The study is based on a sample of 395 teachers working for ...
[p03-b12 | tabla | Tabla 1] fila "SWB" | columna "JP" = ".73**"
[p03-b12 | tabla | Tabla 1] fila "JP" | columna "Reliability (Cronbach's Alpha)" = ".90"
[p05-b04 | figura | imagen] (sin texto; ver imagen adjunta)
```

Las páginas con figuras o tablas que son imagen se envían además como imagen al modelo, a 110 ppp.

### 8.2 Llamadas por artículo

| Rol | Ve | Devuelve | Instrucción base |
| --- | --- | --- | --- |
| Extractor | Libro (secciones normativas), texto etiquetado, imágenes, datos del equipo | `salida` según `esquema_de_salida`, con `bloque_id` en cada evidencia | `prompt_para_el_extractor` del libro, más la regla: "cita solo bloques que existen en el texto etiquetado" |
| Auditor de evidencia | Libro, texto etiquetado, imágenes, `salida` y anclas | Lista de hallazgos (solo los distintos de CONFIRMADO) | Paso 2 de la skill `extractor-matriz-felicidad-desempeno` |
| Codificador ciego | Libro, texto etiquetado, imágenes; **no** ve `salida` | Campos críticos con evidencia | Paso 3 de la skill |
| Conciliador | Cada discrepancia con los bloques involucrados | Decisión con bloque y cita, o PENDIENTE | "Resuelve solo con el texto de los bloques; si no alcanza, PENDIENTE" |

**Campos críticos del codificador ciego:**

- número de filas y mapa de efectos;
- Muestra;
- Correlación Feli 1 - JP y `metodo_obtencion_r`;
- Beta Fel 1- JP, `tipo_de_efecto` y `tecnica_del_beta`;
- las dos fiabilidades con su tipo;
- # Ítems e Items instrumento1;
- Desempeño, Hedónica/eudaimónica y Tipo de felicidad real;
- How measure the employee perfomance, Study design, Nivel y Analysis method (principal);
- Direccionalidad de la relación e Incluir en meta análisi.

**Secciones del libro que se envían** (en el bloque de sistema con caché):

- `prompt_para_el_extractor`
- `protocolo_de_extraccion`
- `como_se_construye_cada_fila`
- `vocabularios_controlados`
- `columnas[*].instruccion_operativa`
- `trazabilidad_por_fila`
- `validaciones_automaticas`
- `esquema_de_salida`
- `ejemplo_verificado`

No se envían la capa diagnóstica ni `recomendaciones_generales`.

**Modelos.** Se configuran por rol con variables de entorno (sección 11). La F0 compara calidad y costo para elegir el modelo de cada rol.

### 8.3 Flujo del caso de uso `ExtraerArticulo`

```
1. Reservar números de Estudio (transacción con bloqueo en la tabla de secuencia del proyecto).
2. Extractor → salida.
3. Validador: si hay errores, reenviar al extractor la salida y los errores; máximo 3 iteraciones.
   Si persisten errores → Extraccion FALLIDA con los errores (no se escribe nada en Matriz).
4. Anclaje (M5) de cada evidencia.
5. Auditor y codificador ciego en paralelo.
6. Comparación automática salida contra ciega (numéricos con tolerancia 0.001; categorías por igualdad exacta).
7. Conciliador para cada diferencia y cada hallazgo REFUTADO; su decisión también se ancla.
   Si cambia un valor → se vuelve a validar.
8. Calcular acuerdo en campos críticos.
9. Escribir FilaDeEfecto(s) en estado POR_REVISAR (evento ExtraccionCompletada → Matriz).
10. Si el acuerdo es menor a 0.80 → aviso en la fila y en el panel del artículo.
```

Cada paso actualiza `Trabajo.paso_actual` y `progreso`. El avance llega a la interfaz por WebSocket.

### 8.4 Algoritmo de anclaje

Para cada evidencia `e`, con su bloque citado `B`:

```
q = norm(e.cita_textual)
si B no existe                                   → buscar en todos los bloques (paso 2)
1. si B es tabla y e.fila_tabla/e.columna_tabla:
       celda = celda de B con similitud(etiqueta_fila, e.fila_tabla) ≥ 90
                        y similitud(etiqueta_columna, e.columna_tabla) ≥ 90
       si celda y q ⊂ norm(celda.texto)          → VERIFICADA, rect = B.rect
2. si q ⊂ B.texto_norm                           → VERIFICADA, rango = posición de q
3. si q ⊂ X.texto_norm para otro bloque X        → VERIFICADA_CON_CORRECCION, bloque = X
4. mejor = max(partial_ratio(q, X.texto_norm)) sobre todos los bloques de la página citada y adyacentes
   si mejor ≥ UMBRAL_SIMILITUD (95)              → POR_CONFIRMAR
5. si e.leido_de_figura y B es figura o tabla imagen → POR_CONFIRMAR, rect = B.rect
6. en otro caso                                  → NO_VERIFICABLE
```

La celda toma el nivel **más bajo** de sus evidencias. El color de la interfaz sale de este nivel (sección 9.3).

### 8.5 Pruebas doradas

- **Kumar (2022):** con `ConversorFijo` y `ModeloGrabado`, la fila producida coincide con `ejemplo_verificado.salida` del libro en los campos críticos. Además, las 32 citas que no son de tabla ni de figura quedan en `VERIFICADA`.
- **Singh et al. (2023):** Incluir en meta análisi da `SEM latente` por la condición 9, y Beta Fel 1- JP tiene confianza `Baja` con la discrepancia registrada.

---

## 9. Interfaz (M8)

### 9.1 Disposición responsiva

| Ancho | Disposición |
| --- | --- |
| 1280 px o más | Tres paneles redimensionables: artículos (280 px), matriz (flexible) y visor (40 % del ancho, plegable) |
| 768 a 1279 px | Artículos en un cajón lateral; matriz y visor alternados con pestañas, o lado a lado si el ancho es de 1024 px o más |
| Menos de 768 px | Una vista a la vez: lista de artículos, cola de revisión en tarjetas y visor a pantalla completa. Sin grilla |

### 9.2 Panel de artículos

- Lista virtualizada con casilla, nombre, número de Documento, etiqueta de estado y porcentaje de avance cuando hay un trabajo activo.
- Acciones:
  - **Añadir PDF:** acepta arrastrar y soltar y carga múltiple; muestra un aviso si el archivo está duplicado.
  - **Seleccionar todo:** marca solo los visibles con el filtro actual.
  - **Extraer seleccionados:** se habilita si algún seleccionado está en `LISTO`, `HEREDADO`, `ERROR` o `POR_REVISAR`. Antes de encolar abre un diálogo con:
    - el número de artículos;
    - la estimación de tokens, calculada con el tamaño del texto etiquetado por el promedio medido en F0;
    - una confirmación explícita para los que están en `POR_REVISAR`.
- Filtros por estado y contadores en la cabecera.

### 9.3 Grilla de la matriz

- Las columnas se construyen desde `GET /normas/columnas`, nunca escritas a mano. Documento, Estudio y Cita quedan fijas a la izquierda.
- Cada encabezado muestra un ícono de información con la `nota_encabezado`.
- Colores de celda, por `estado_revision` y nivel de ancla:

| Estado | Color |
| --- | --- |
| SIN_EVIDENCIA (heredada) | gris |
| PENDIENTE con todas las anclas VERIFICADAS | sin color |
| INFERIDO | amarillo |
| POR_CONFIRMAR | amarillo con borde |
| Discrepancia del artículo | naranja |
| NO_VERIFICABLE o hallazgo pendiente | rojo |
| APROBADA o CORREGIDA | verde |

- **Ficha de evidencia.** Se abre al pasar el cursor 300 ms o con Enter. Muestra:
  - el valor y el tipo de valor;
  - cada evidencia, con página, ubicación y cita, y la cita resaltada;
  - la regla y el razonamiento, si el valor es inferido;
  - los veredictos de los auditores;
  - los botones Ir al PDF, Aprobar, Corregir y Rechazar.

### 9.4 Visor PDF

- pdfjs-dist con capa de texto activada.
- **Ir a una evidencia:**
  1. renderizar la página;
  2. desplazar hasta el rectángulo del ancla;
  3. dibujar una superposición con el rectángulo;
  4. resaltar las palabras: buscar `norm(cita)` en el texto concatenado de la capa de texto de la página y marcar los fragmentos que cubren ese rango.
- **Conversión de coordenadas:** `escala = viewport.width / pagina.ancho_pt`; `x_px = rect.x0 × escala`, y lo mismo con los demás lados. El origen arriba a la izquierda coincide con el de la vista de PDF.js.
- Una franja superior indica: `Estudio {n} · {columna} · p. {pagina} · {ubicacion}`.
- El PDF se sirve con una URL temporal del almacén.

### 9.5 Navegación con retorno

Estado en Zustand, sincronizado con la URL, para que el botón Atrás del navegador también funcione:

```ts
type Vista = {
  articuloId?: string; estudio?: number; columna?: string;
  scrollGrilla: { fila: number; col: number };
  visor?: { articuloId: string; pagina: number; zoom: number; anclaId?: string };
};
type Navegacion = { pila: Vista[]; actual: Vista; ir(v: Vista): void; volver(): void };
```

- `ir()` apila `actual` en cada salto a una evidencia o cambio de artículo. La pila guarda como máximo 50 entradas y la lista desplegable muestra las 10 últimas.
- Volver se activa con el botón de la barra, con Alt + flecha izquierda o con el botón Atrás del sistema en el teléfono.
- Migas: `Matriz › Estudio 45 › AE › p. 3`, y cada parte es navegable.
- Atajos: Enter (evidencia), A (aprobar), E (corregir), R (rechazar), N y P (siguiente y anterior celda pendiente).

### 9.6 Revisión en teléfono

Cola de tarjetas, una por celda pendiente, ordenadas por rojo, luego amarillo, luego el resto. Cada tarjeta muestra la columna, el valor, la cita y los botones Ver en el PDF, Aprobar y Corregir.

---

## 10. API (M7)

Todas las rutas van bajo `/api/v1/proyectos/{proyecto_id}`. Las respuestas siguen el esquema OpenAPI generado, y el cliente del frontend se genera desde ese esquema con `openapi-typescript`.

| Método y ruta | Caso de uso |
| --- | --- |
| `POST /articulos` (multipart, varios archivos) | CargarPDF |
| `GET /articulos?estado=` | Listado con contadores |
| `POST /articulos/{id}/excluir` · `/reactivar` | Excluir o reactivar |
| `POST /extracciones` con `{articulos: [id], confirmar_reextraccion: bool}` | ExtraerSeleccionados |
| `POST /trabajos/{id}/cancelar` · `/reintentar` | Orquestación |
| `GET /normas/columnas` | CatalogoDeColumnas |
| `POST /normas/libros` | Publicar una versión del libro |
| `GET /matriz/filas?pagina=&filtro=` | Filas con celdas (paginado) |
| `GET /matriz/filas/{estudio}/celdas/{clave}` | Detalle: evidencias, anclas, inferencia, hallazgos, historial |
| `POST /matriz/filas/{estudio}/celdas/{clave}/aprobar` · `/corregir` · `/rechazar` | Revisión (motivo obligatorio en corregir y rechazar) |
| `GET /articulos/{id}/pdf` | Redirige a la URL temporal |
| `GET /articulos/{id}/documento` | Documento estructurado (para depuración y resaltado) |
| `POST /exportaciones` · `GET /exportaciones/{id}` | Generar y descargar el Excel |
| `POST /importaciones/matriz` | Importar la matriz actual (filas HEREDADAS) |
| `WS /ws` | Eventos: estado de artículo, avance de trabajo, fila escrita, celda revisada |

Autenticación: sesión con cookie segura desde la F1, con un usuario administrador creado por semilla. Los roles `extractor`, `revisor` y `administrador` se activan en la etapa 2; solo `revisor` y `administrador` aprueban.

---

## 11. Configuración

`.env.example`:

```
DATABASE_URL=postgresql+psycopg://extractor:extractor@postgres:5432/extractor
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000
S3_BUCKET=biblioteca
S3_ACCESS_KEY=
S3_SECRET_KEY=
MINERU_URL=http://mineru:8001
ANTHROPIC_API_KEY=
MODELO_EXTRACTOR=claude-opus-5-5
MODELO_AUDITOR=claude-opus-5-5
MODELO_CIEGO=claude-sonnet-5-5
MODELO_CONCILIADOR=claude-opus-5-5
CONCURRENCIA_EXTRACCION=2
UMBRAL_SIMILITUD=95
MAX_ITERACIONES_VALIDADOR=3
UMBRAL_ACUERDO=0.80
TOPE_TOKENS_MENSUAL=
```

Los modelos son valores iniciales; la F0 los confirma o los cambia con base en la calidad y el costo medidos. Si `TOPE_TOKENS_MENSUAL` está definido, `ExtraerSeleccionados` rechaza lotes que lo superen.

`docker-compose.yml` levanta estos servicios: `postgres`, `redis`, `minio`, `mineru`, `api`, `trabajador` (se puede escalar con `--scale trabajador=N`), `despachador-outbox` y `frontend` (servido por nginx).

---

## 12. Fases, tareas y pruebas de aceptación

Cada casilla es una tarea. La fase se cierra cuando pasan sus pruebas de aceptación, que se automatizan salvo que se diga lo contrario.

### F0 · Prueba técnica

- [ ] Levantar `servicio-mineru` y convertir Kumar y Singh.
- [ ] Dibujar 20 rectángulos de bloque sobre las páginas renderizadas y guardar las imágenes en `docs/decisiones/0001/`.
- [ ] Escribir el ADR 0001: sistema de coordenadas y fórmula de conversión.
- [ ] Medir el tiempo de conversión por página, con CPU y, si hay, con GPU.
- [ ] Ejecutar una extracción completa de Kumar (los cuatro roles) con la API y registrar tokens por rol y costo.
- [ ] Comparar dos modelos para el rol extractor en Kumar y Singh contra el ejemplo verificado.

**Aceptación:** los 20 rectángulos caen sobre su texto (revisión visual, firmada en el ADR), y están registradas las mediciones de tiempo y costo.

### F1 · Núcleo y esqueleto

- [ ] Repositorio con la estructura de la sección 4, `import-linter` y CI (ruff, mypy, pytest, Vitest).
- [ ] Núcleo compartido: entidad, evento, unidad de trabajo, outbox y despachador.
- [ ] Contextos Biblioteca y Normas completos; Matriz con agregado, repositorio e invariantes.
- [ ] Migraciones de Alembic.
- [ ] Importación de la matriz actual como filas HEREDADAS, conservando los 25 comentarios existentes en `trazabilidad.notas_heredadas`.
- [ ] Exportación básica.
- [ ] Carga de PDF, con deduplicación, y conversión de los 48 PDF del proyecto.
- [ ] Docker Compose funcional y usuario administrador semilla.

**Aceptación:**

- Las pruebas unitarias de dominio corren sin base de datos ni red.
- Importar y exportar la matriz de 71 filas da los mismos valores celda por celda (prueba automática).
- Un PDF repetido se rechaza.
- La grilla de columnas proviene de `CatalogoDeColumnas`: la prueba cambia una columna en un libro de prueba y la ve reflejada.

### F2 · Extracción y anclaje

- [ ] Texto etiquetado.
- [ ] Adaptador de Claude con caché de instrucciones.
- [ ] Los cuatro roles y el ciclo con el validador.
- [ ] Algoritmo de anclaje.
- [ ] Comando `python -m app.cli extraer <articulo_id>`.

**Aceptación:**

- Pasan las pruebas doradas de la sección 8.5.
- El validador da 0 errores.
- Al menos el 95 % de las citas quedan verificadas en 5 artículos piloto elegidos por el responsable del dominio.

### F3 · Cola, eventos y API

- [ ] Dramatiq y Redis, con el agregado Trabajo y los reintentos.
- [ ] Reserva atómica de números de Estudio.
- [ ] Todos los endpoints de la sección 10 y el WebSocket.

**Aceptación:**

- Un lote de 10 artículos termina con estados correctos.
- Cancelar funciona.
- Un error forzado en el paso de anclaje se reintenta desde ese paso.
- Con `--scale trabajador=2` no se repiten números de Estudio (prueba con 20 extracciones simuladas en paralelo).

### F4 · Interfaz responsiva

- [ ] Disposición de la sección 9.1.
- [ ] Panel de artículos.
- [ ] Grilla con colores y ficha de evidencia.
- [ ] Visor con resaltado.
- [ ] Navegación con retorno.
- [ ] Tarjetas para teléfono.

**Aceptación (Playwright):**

- 20 de 20 celdas de prueba abren la página y el rectángulo correctos.
- Volver restaura la celda y la página.
- Seleccionar todo y Extraer seleccionados encolan los artículos esperados.
- En una ventana de 390 × 844 px se puede aprobar una celda desde una tarjeta.
- Un cambio de estado llega sin recargar.

### F5 · Revisión y exportación

- [ ] Aprobar, corregir y rechazar, con historial.
- [ ] Roles.
- [ ] Exportación completa con `escribir_matriz.py`, que incluye notas de encabezado, comentarios de fuente, colores y hojas de trazabilidad y auditoría.

**Aceptación:**

- Cada acción deja autor, fecha y motivo.
- Un usuario `extractor` no puede aprobar.
- El Excel exportado abre en Excel y en Google Sheets con comentarios y colores; esta prueba es manual y se registra con capturas.

### F6 · Piloto con la matriz

- [ ] Extraer las filas 65 a 71 y reextraer 5 filas antiguas elegidas por el responsable del dominio.
- [ ] Informe de diferencias con la matriz actual.

**Aceptación:** acuerdo de 0.80 o más entre extractor y codificador ciego en campos críticos, y el responsable del dominio revisa y firma el informe de diferencias.

---

## 13. Etapas de despliegue

| Etapa | Cómo | Cambios de código |
| --- | --- | --- |
| 1. Local | `docker compose up` en el equipo del responsable | Ninguno |
| 2. Servidor del grupo | El mismo Compose en un servidor con HTTPS (proxy inverso) y roles activados | Ninguno; solo configuración |
| 3. Escalado | Kubernetes: API con varias réplicas, trabajadores con escalado automático por largo de cola, MinerU en nodo con GPU, PostgreSQL y almacenamiento gestionados; outbox con Redis Streams | Solo manifiestos y adaptador del intermediario de eventos |

Una instalación aloja varios proyectos (revisiones sistemáticas), cada uno con su libro, su biblioteca y su matriz. El aislamiento se hace por `proyecto_id` en todas las consultas, con una prueba de integración que lo verifica.

---

## 14. Fuera de alcance de la versión 1

- Edición del libro de códigos dentro de la aplicación (se publica un JSON nuevo).
- OCR propio distinto del que trae MinerU.
- Metaanálisis, forest plots y cálculo de tamaños del efecto combinados.
- Colaboración simultánea sobre la misma celda (el último cambio queda en el historial; no hay edición en tiempo real compartida).

---

## 15. Insumos que acompañan este documento

Todos están en el proyecto "SKILLER ARTICULOS CIENTIFICOS" y se copian a `recursos/`:

- `Libro_de_codigos_extraccion_v2.json` (versión 2.1): norma de extracción.
- `validar_extraccion.py`: 29 validaciones, incluida la comprobación de citas literales contra el PDF.
- `escribir_matriz.py`: escritura del Excel con comentarios, colores y hojas de trazabilidad.
- `Matriz_de_sintesis_con_notas.xlsx`: matriz vigente con las notas de encabezado.
- Los 48 PDF de `Artículos revisión sistemática/`.
- La skill `extractor-matriz-felicidad-desempeno`, cuyos pasos 1 a 4 son la especificación funcional de los roles de la sección 8.2.

# Plan · Pestaña «Buscar»: encontrar artículos que traigan los datos de la matriz (fuentes gratuitas + Bibliotecas UNAL)

- Estado: **v8 · Fases 1, 2 (con etapa B), 3 y 4 construidas (2026-11-25); Fase 0 parcial; solo falta la 5 (Biblioteca UNAL)** · Responsable: Pablo Andrés Erazo Muñoz
- **Ronda 3 (2026-11-25):** la cuenta es la `@unal.edu.co`, y la lista de sitios con credenciales queda **abierta** para
  agregar más en el futuro (sección 7.0). Se pidió avanzar sin más preguntas: se construyó la Fase 1 (ver «Estado de la
  Fase 1» más abajo).
- Decisión asociada: `docs/decisiones/0011-descubrimiento-de-literatura-y-limites-del-scraping.md`
- **Solo PDF gratuito (2026-11-25):** a pedido del responsable, solo entran artículos cuyo PDF gratuito y legal se
  comprueba (`docs/decisiones/0013-solo-articulos-con-pdf-gratuito.md`). Los paneles laterales se ensanchan en escritorio.
- **En la nube (2026-11-25):** a pedido del responsable, en la nube también **se busca**, y lo encontrado vuelve al
  equipo (`docs/decisiones/0012-buscar-desde-la-nube.md`).
- **Decisiones de la segunda ronda (2026-11-25):** las credenciales de la UNAL las escribe siempre el usuario; se aceptan los
  límites de la sección 7.2 y la exclusión de evasión; los errores quedan marcados en el registro (sección 4.5); el
  metadato **no** rellena la matriz por defecto; se aprueba la clasificación M/R/T con corrección mía (sección 5.2);
  búsqueda **de 2020 hasta la fecha**; idiomas, tipos, términos y formato de `Cita` los fijo yo (sección 11); **sin IA**.
- Tallas: **S** ≤ 1 día · **M** 2–4 días · **L** ≥ 1 semana (una persona, con pruebas)
- Qué **no** está verificado (se marca «⚠ verificar» y se cierra en la Fase 0): las condiciones de licencia de cada base,
  los límites/llaves vigentes de cada API y cómo se mapea cada base al proxy. Ninguno se dio por cierto.
- **Cambios frente a la v1** (pedidos el 2026-11-25):
  1. Se exploró `bibliotecas.unal.edu.co` de verdad: la sección 7 está reescrita con lo observado (Aluna, bases, proxy,
     acceso y **un límite de descarga que bloquea 8 horas**).
  2. **Selección y vista previa**: marcar candidatos y ver, antes de importar, cómo encajan con la matriz según sus
     metadatos (secciones 5 y 6).
  3. **Columnas a elección y con prioridad**: quien usa la pestaña escoge qué columnas le importan y cuánto (sección 5).
  4. **Cero tokens**: nada en la pestaña llama a un modelo. Se eliminó la Fase 6 (cribado con modelo).
  5. Tu correo de Gmail queda como contacto de las APIs abiertas, solo en el `.env` local (sección 3).

## 1. Qué se construye

Una pestaña nueva **Buscar** en la aplicación web que:

1. Consulta varias fuentes a la vez con una cadena de búsqueda guardada (reproducible, estilo PRISMA).
2. Junta y **desduplica** los resultados, y marca los que ya están en la matriz (47 documentos hoy).
3. Deja que la persona **elija las columnas de la matriz que le importan y su prioridad** (imprescindible, importante,
   deseable) y calcula para cada candidato cuánto de eso parece poder aportar, con la frase que lo sugiere.
4. Permite **seleccionar** candidatos (casillas, selección múltiple) y muestra una **vista previa de la fila**: cada columna
   con el valor que sugieren los metadatos, su origen y si falta el PDF para confirmarla.
5. Deja **priorizar, descartar con motivo, exportar o importar** lo seleccionado. Importar = obtener el PDF y entregarlo al
   flujo que ya existe (`CargarPDF` → conversión → extracción con anclaje). **La búsqueda nunca escribe en la matriz.**
6. **No gasta tokens.** Toda la pestaña es determinista: APIs, expresiones regulares y lectura de PDF con `pymupdf`.
   (La extracción posterior de un PDF importado sí usa el modelo, como hoy; sigue siendo una acción aparte que se pide y
   se confirma, ~2,6 USD y ~4 min por artículo.)

### Regla central (CLAUDE.md): dato sin ubicación comprobable nunca entra como verificado

Un metadato de un buscador (año, autores, un «N = 245» leído del resumen) es un **indicio**, no un dato. Por eso la vista
previa se pinta siempre como «sin verificar», no se guarda en la matriz, y los valores de la matriz siguen saliendo
únicamente del PDF con página, bloque y cita literal. Si quieres que el metadato rellene `Cita`, `Title`, `Author` o
`Año` (origen «metadato de fuente», sin anclaje), es decisión de dominio: sección 11, pregunta 3.

### Fuera de alcance

- Descargas masivas o rastreo continuo de sitios de editoriales.
- Evadir defensas de los sitios: **no se construye** rotación de IP/proxies, suplantación de huella del navegador,
  «stealth», ni resolución automática de CAPTCHA. Si un sitio plantea un reto, el programa se detiene y avisa.
  Razón: viola los términos de casi todos los proveedores y, con la cuenta de la Universidad, el castigo lo recibe toda la
  institución, no solo tú (sección 7).
- Escribir tu contraseña por ti: el programa nunca la pide, la ve ni la guarda.
- Google Scholar (sus términos prohíben el acceso automatizado) y cualquier sitio pirata de PDF.
- Modelos de lenguaje dentro de la pestaña (sin tokens, por decisión tuya).
- **Decidir, importar, analizar o cambiar perfiles desde la nube:** allí solo se busca, se mira y se exporta
  (ADR 0012).

## 2. «Scraping avanzado»: qué significa aquí

Avanzado = **robusto y cortés**, no sigiloso. En orden de preferencia, para cada fuente:

| Nivel | Técnica | Cuándo |
|---|---|---|
| 1 | API oficial (JSON), con paginación por cursor, reintentos con espera creciente, caché y ETag | Siempre que exista |
| 2 | Protocolos abiertos (OAI-PMH, RSS/Atom, sitemap) | Repositorios y revistas sin API propia |
| 3 | HTML estático con `httpx` + `beautifulsoup4`/`lxml` (ya son dependencias), respetando `robots.txt` | Sitios sin API |
| 4 | Navegador real con Playwright (páginas que pintan con JavaScript) | Solo si el nivel 3 no ve el contenido |
| 5 | Peticiones con **la sesión que inició la persona** (cookie del proxy de la Biblioteca) | Solo fuentes con credenciales |

Comunes a todos los niveles: un cliente HTTP único con límite de ritmo **por host** (1 petición concurrente, intervalo
mínimo configurable), **contador de bytes por ventana** (sección 7), caché en disco con vigencia, `User-Agent`
identificable, reintentos que respetan `Retry-After`, y un *interruptor de circuito* por host (tras 403/429 repetidos
se detiene y lo dice en pantalla).

## 3. Fuentes

Todas entran por el mismo puerto `FuenteDeLiteratura`; añadir una es añadir un adaptador.

| Fuente | Qué da | Acceso | Notas |
|---|---|---|---|
| OpenAlex | Metadatos, resumen (índice invertido), DOI, instituciones y país de cada autor, enlace de acceso abierto | API; llave gratuita recomendada (`OPENALEX_API_KEY`), la crea la persona | Punto de partida; el país por afiliación alimenta la columna `Pais` (ADR 0010) |
| Crossref | Metadatos y DOI | API pública | Sin resumen fiable; completa y valida DOI |
| Semantic Scholar | Metadatos, resumen, citas | API ⚠ verificar llave gratuita | |
| Europe PMC | Metadatos y texto completo abierto | API | |
| CORE | Texto completo de repositorios | API ⚠ llave gratuita | |
| DOAJ | Revistas de acceso abierto | API | |
| Unpaywall | **Resolutor** DOI → copia abierta legal | API (pide correo) | No busca: resuelve el PDF |
| SciELO, Redalyc, Dialnet | Literatura iberoamericana (la Biblioteca UNAL los lista como recursos) | OAI-PMH / HTML (niveles 2–3) | Primer caso real de scraping |
| PsyArXiv / OSF Preprints | Preprints de psicología | API de OSF | Marcados «preprint» |
| **Aluna** (catálogo y descubrimiento UNAL) | Metadatos de artículos de muchas editoriales | Primo VE ⚠ verificar | Sección 7 |
| **Bases con suscripción vía proxy** | Scopus, Web of Science, ScienceDirect, Wiley, Springer-Nature Link, Sage, Taylor & Francis, Emerald, EBSCO (Academic Search Ultimate, Business Source Complete, **Psychology & Behavioral Sciences Collection**, Sociology Source Ultimate) | Sesión de la persona (nivel 5) o API institucional | Sección 7 |

**Correo de contacto (decidido el 2026-11-25):** varias APIs (Crossref, OpenAlex, Unpaywall) piden un correo para
atender mejor a quien consulta con cortesía. Tú autorizaste usar tu correo de Gmail. Queda **solo** en la variable
`CONTACTO_API` del `.env` local (ya ignorado por git, y ya escrita ahí); no va en `.env.example`, en el código ni en este
documento, porque `Zann181/calificar` está en GitHub. Se añade al `User-Agent` y a los parámetros `mailto` **únicamente**
de las fuentes abiertas que lo piden; **nunca** a la Biblioteca UNAL ni a editoriales. Sin esa variable, las consultas
salen sin correo y el cliente se identifica como `ExtractorMatriz/0.1`. Ojo: ese correo **no** sirve para entrar a la
Biblioteca, que pide una cuenta `@unal.edu.co` o usuario y contraseña institucionales (sección 7).

## 4. Arquitectura

Contexto nuevo `descubrimiento` con la estructura de siempre (`dominio/`, `aplicacion/`, `puertos.py`, `adaptadores/`,
`eventos.py`). Respeta las reglas existentes: no lee tablas de otros contextos y solo `app/composicion.py` lo conecta.

```mermaid
flowchart LR
  UI[Pestaña Buscar<br/>React] --> API[/api/v1/proyectos/{id}/busquedas<br/>/candidatos · /perfiles-de-columnas/]
  API --> CU[Casos de uso<br/>descubrimiento]
  CU --> D[Dominio: Búsqueda · Candidato<br/>Perfil de columnas · Vista previa de fila<br/>Desduplicador]
  CU --> P1{{puerto FuenteDeLiteratura}}
  CU --> P2{{puerto ResolutorDeTextoCompleto}}
  CU --> P3{{puerto SesionInstitucional}}
  P1 --> A1[OpenAlex · Crossref · S2 · EPMC · CORE · DOAJ]
  P1 --> A2[SciELO · Redalyc · Dialnet<br/>OAI-PMH / HTML]
  P1 --> A3[Aluna y bases UNAL<br/>httpx + cookie de la sesión]
  P2 --> A4[Unpaywall · enlaces OA · proxy UNAL]
  P3 --> A5[Chrome del usuario<br/>CDP local · cookie en keyring]
  CU -. composicion.py .-> BIB[biblioteca.CargarPDF]
  CU -. composicion.py .-> MAT[matriz: ¿ya está?<br/>consulta por DOI/título]
  CU -. composicion.py .-> NOR[normas: columnas del libro]
  BIB --> FLUJO[conversión → extracción → matriz]
```

### 4.1 Piezas de dominio (sin dependencias de infraestructura)

- **Búsqueda**: nombre, cadena (árbol AND/OR por concepto, no texto suelto), filtros (por defecto **2020 hasta la
  fecha de hoy**, decisión del responsable; idiomas EN/ES/PT; tipos: sección 11), fuentes elegidas, conteos por fuente y fecha. Inmutable una vez ejecutada: repetirla crea otra.
- **Candidato**: DOI normalizado, título, autores, año, revista, resumen, palabras clave, afiliaciones, idioma, URL de
  acceso abierto, estado `NUEVO → PRIORIZADO | DESCARTADO(motivo) | IMPORTADO`, y la marca `YA_EN_MATRIZ`.
- **Hallazgo**: qué fuente devolvió qué candidato, en qué posición y cuándo (trazabilidad para el diagrama de flujo).
- **Desduplicador**: clave por DOI; sin DOI, título normalizado + año + primer autor con `rapidfuzz` (ya es dependencia) y
  `compartido/normalizacion.py`. Dos fuentes con el mismo trabajo ⇒ un candidato, varios hallazgos.
- **Perfil de columnas**: las columnas que la persona eligió, con su prioridad y su orden (sección 5).
- **Vista previa de fila**: para un candidato y un perfil, una celda propuesta por cada columna (sección 5.3).

### 4.2 Persistencia (migraciones nuevas desde la 0009; SQLite y PostgreSQL)

`descubrimiento_busquedas`, `descubrimiento_candidatos`, `descubrimiento_hallazgos`, `descubrimiento_perfiles`
(nombre, columnas, prioridades, orden; uno puede ser el «predeterminado»), `descubrimiento_sesiones` (solo estado:
fuente, vigente sí/no, última comprobación; **nunca** cookies ni contraseñas). Caché HTTP en `datos/cache_http/`
(carpeta ya ignorada por git, igual que todo `datos/`).

### 4.3 Registro y errores marcados (decidido)

La aplicación ya tiene un registro (`datos/registro.jsonl`, panel «Registro» con contador de errores y filtro por nivel).
La pestaña lo reutiliza, sin inventar otro:

- `descubrimiento` se añade a `ORIGENES` en `app/compartido/registro.py`; todo lo que pase sale con su nivel.
- **Todo fallo se registra como `ERROR`** (no `WARNING`) con: fuente, servidor, código HTTP o excepción, causa en una
  frase y qué se hizo (reintento, circuito abierto, fuente apagada). Nunca URL con parámetros sensibles, cookies,
  contraseñas ni el correo de contacto.
- Pasan a `ERROR` también: sesión vencida, tope de bytes alcanzado, circuito abierto, parser que ya no entiende un sitio,
  PDF que no es PDF, duplicado inesperado.
- En la interfaz, cada fuente muestra una **insignia roja con su número de errores** y «Ver errores» abre el panel de
  registro ya filtrado por origen `descubrimiento` y nivel Errores. El contador global de errores del registro los suma.
- Cada búsqueda guarda cuántos errores tuvo por fuente, para que el historial diga «esta búsqueda quedó incompleta en X».

### 4.4 Ejecución

Una búsqueda toma segundos o minutos y varias fuentes: corre en un hilo con progreso por fuente, que la interfaz
consulta cada pocos segundos (sondeo, igual que el avance de extracción; el ADR 0007 descarta WebSocket). Cancelable.

### 4.5 Dependencias

`playwright` va en un extra opcional `[busqueda]` de `pyproject.toml` (solo para el nivel 4): la imagen de la nube
(512 MB) no lo lleva. El resto usa `httpx`, `beautifulsoup4`, `lxml`, `rapidfuzz` y `pymupdf`, que ya están. `keyring`
también (lo usa la sincronización). `import-linter`: `playwright` y `httpx` solo en `adaptadores/`; el dominio no
importa ninguno.

## 5. Columnas a elección, prioridad y perfil de completitud

### 5.1 Qué elige la persona

Un **selector de columnas** alimentado por el libro de códigos (`/normas/columnas`; no se copian columnas al código):

- Las 59 columnas agrupadas como las muestra la matriz; casillas para marcar las que importan.
- Cada columna marcada recibe una **prioridad**: **Imprescindible** · **Importante** (peso 3) · **Deseable** (peso 1).
  Se reordenan arrastrando; ese orden es el de las columnas de la tabla de candidatos y de la vista previa.
- **Perfiles guardados** («Esencial para metaanálisis», «Solo identificación», los que la persona cree) y uno por defecto.
  Cambiar el perfil recalcula todo al instante, sin volver a consultar las fuentes.
- Interruptor **«Exigir las imprescindibles»**: oculta (no borra) los candidatos que todavía no muestran indicio de
  alguna imprescindible.
- Propuesta inicial de perfil (la apruebas o la cambias): imprescindibles = muestra (N), correlación o β entre
  felicidad y desempeño, instrumento de felicidad, instrumento de desempeño; importantes = fiabilidad de ambos, país;
  deseables = sector, diseño, software, años del estudio.

### 5.2 Qué se puede saber, y cuándo: «detectabilidad»

No todas las columnas se pueden anticipar con metadatos. Se clasifica cada columna en un archivo de datos
(`recursos/detectabilidad_columnas.json`, **propuesta que aprueba el responsable**, validada por una prueba contra el libro
para que ninguna columna se pierda ni se renombre en silencio):

| Nivel | Qué fuente la aporta | Ejemplos (propuesta) | Confiabilidad |
|---|---|---|---|
| **M** · Metadato | Los campos bibliográficos de la fuente | `Title`, `Author`, `Año`, `Cita` (derivada con la regla de la sección 11), `Pais` por afiliación (ADR 0010) | Alta |
| **R** · Resumen | Título, resumen y palabras clave (patrones deterministas) | `Muestra` (N), `Study design`, `Aim of study`, `Población`, `Sector`, instrumentos nombrados, `Conclusion` | Media-baja: los resúmenes callan mucho |
| **T** · Texto completo | Solo el PDF (métodos y resultados) | correlación y β, fiabilidad α/ω, CFA, `# ítems`, ejemplos de ítem, criterios de inclusión y exclusión, fechas, software | Alta, pero hay que tener el PDF |

El perfil se calcula en dos etapas, sin gastar nada:

- **Etapa A (metadatos + resumen):** cubre las columnas M y R. Se hace para **todos** los candidatos.
- **Etapa B (texto completo):** cubre además las T. Solo para candidatos con copia abierta o ya descargada; `pymupdf`
  lee el PDF y los mismos patrones buscan en métodos y resultados. Se puede pedir por selección («Analizar texto completo»).
- Detectores: patrones y vocabularios que salen del **libro de códigos** (vocabularios controlados y descripciones), no de
  listas copiadas al código. Donde el libro no tenga vocabulario (por ejemplo, nombres de instrumentos), se propone al
  responsable. Ninguno llama a un modelo.

### 5.3 Cómo se lee el resultado (sin engañar)

Para cada columna elegida, el candidato muestra uno de cuatro estados:

| Estado | Significado |
|---|---|
| **Metadato** | Viene de un campo de la fuente (muestra la fuente) |
| **Indicio** | Hay una frase literal que lo sugiere (resumen o página del PDF); se muestra resaltada |
| **Pendiente de PDF** | Columna de nivel T que la etapa A no puede juzgar: **no cuenta como ausente** |
| **Ausente** | Solo se afirma tras la etapa B, sin indicio en el texto completo |

- **Barra de cobertura apilada:** verde = metadato/indicio, rayado = pendiente de PDF, vacío = ausente. Así un artículo no
  se castiga por lo que ningún resumen cuenta.
- **Puntaje** = peso de las columnas con metadato/indicio ÷ peso de todas las elegidas, mostrado junto a «máximo
  posible» (si todo lo pendiente apareciera). Etiquetas: «Probable», «Dudoso», «Sin datos suficientes», **«No aplica»**
  (revisiones, metaanálisis y cualitativos no aportan una correlación primaria). Si falta una imprescindible ya
  descartable (etapa B sin indicio) → «Incompleto».
- La etapa que produjo cada cosa se ve siempre («solo resumen» / «texto completo»).

### 5.4 Vista previa de la fila

Al marcar uno o varios candidatos y abrir **Vista previa**, aparece la fila que se formaría en la matriz:

| Columna | Valor propuesto | Estado | Origen / frase |
|---|---|---|---|
| Cita | Wright et al. (2002) | Metadato | OpenAlex · autores y año |
| Pais | Colombia | Metadato | afiliación del primer autor (ADR 0010) |
| Muestra | 245 | Indicio | «…a sample of N = 245 employees…» (resumen) |
| Correlación Feli 1 – JP | — | Pendiente de PDF | solo texto completo |

Siempre con el rótulo **«sin verificar: no se escribe en la matriz»**. Con varios candidatos seleccionados se ve como
tabla comparativa (candidatos en filas, columnas elegidas en el orden de la persona). Exportable a CSV desde ahí.

## 6. Pestaña «Buscar» (interfaz)

Hoy no hay selector de vistas de primer nivel: `App.tsx` siempre pinta `Espacio` (artículos · matriz · visor). Cambios:

- Escritorio y tableta (≥ 768 px): control segmentado **Matriz | Buscar** en la cabecera (`header.herramientas`).
  La sección «Buscar» sustituye a `Espacio`; las migas siguen mostrando «Matriz» como raíz.
- Teléfono: cuarta pestaña «Buscar» en la barra inferior (`Pestana` ampliado y su `TITULOS`).
- Se oculta si `useCapacidades()` no declara la capacidad `busqueda` (un servidor antiguo). En la nube
  (`escritura: false`, `puede_buscar: true`) están el formulario y la búsqueda, sin decisiones, importación ni
  análisis.

Disposición en escritorio: **izquierda** consulta y columnas (cadena, filtros, fuentes, selector de columnas con
prioridad) · **centro** tabla de candidatos con casillas · **derecha** ficha / vista previa del candidato o de la selección.
En tableta y teléfono esas tres zonas pasan a alternarse.

Componentes nuevos en `frontend/src/componentes/`:

| Componente | Función |
|---|---|
| `PanelBusqueda` | Constructor de cadena por conceptos (felicidad ES/EN · desempeño ES/EN, sinónimos sugeridos y editables), filtros, fuentes con su estado (libre · requiere sesión · sesión vencida), botón Buscar y progreso por fuente |
| `SelectorDeColumnas` | Casillas por grupo, prioridad por columna (Imprescindible/Importante/Deseable), arrastrar para ordenar, perfiles guardados, insignia **M/R/T** de detectabilidad |
| `ListaCandidatos` | Tabla ordenable con **casillas** y «seleccionar todos los visibles»: título, autores, año, fuentes, acceso abierto, barra de cobertura apilada, columnas elegidas como chips con su estado, «ya en la matriz». Filtros por estado, etiqueta y fuente |
| `BarraDeSeleccion` | Aparece al marcar: **Vista previa · Priorizar · Descartar (motivo) · Analizar texto completo · Exportar (CSV/RIS) · Importar** |
| `VistaPreviaDeFila` | La tabla de la sección 5.4 con frases resaltadas y rótulo «sin verificar» |
| `FichaCandidato` | Resumen, hallazgos por fuente, indicios, enlaces a la fuente |
| `SesionFuente` | «Conectar con la Biblioteca UNAL», semáforo de vigencia y contador de bytes de la ventana |
| `HistorialBusquedas` | Cadenas guardadas y conteos (alimenta el diagrama PRISMA) |

Estado del servidor con `@tanstack/react-query` como el resto; el perfil de columnas activo vive en el servidor, no solo
en el navegador. Reutiliza `Icono`, `Divisor` y los estilos existentes.

## 7. Bibliotecas UNAL (observado el 2026-11-25) y su acceso con credenciales

### 7.0 Lista abierta de sitios con credenciales (construido)

La cuenta que se usa en la Biblioteca UNAL es la institucional `@unal.edu.co` (por Google) o usuario y contraseña, **siempre
escritos por la persona**. Para que mañana se puedan sumar otros sitios sin tocar código:

- `recursos/sitios_con_credenciales.json` describe cada sitio: id, nombre, servidores (`hosts`), métodos de acceso,
  bases, y su **límite propio** (bytes por ventana, ventana, pausa mínima, concurrencia). La UNAL es la primera entrada.
- Agregar un sitio = agregar una entrada. El cliente HTTP cortés aplica solo, por servidor, su pausa y su presupuesto de
  bytes, y **nunca** le manda el correo de contacto. La interfaz (`SitiosConCredenciales`) lo lista con su estado de sesión.
- Una fuente que necesite sesión declara su `sitio_id` en el puerto `FuenteDeLiteratura`; si la sesión no está vigente se
  **omite** y queda como ERROR en el registro, sin intentar nada a ciegas.
- Lo que falta (Fase 5): capturar la sesión que inicie la persona. Hoy todos los sitios figuran «No conectado» y el botón
  de conexión está desactivado. Una prueba impide que el catálogo tenga campos para usuario, contraseña o cookies.

### 7.1 Qué hay (leído en el sitio público; no entré con ninguna cuenta)

- **Portal** `bibliotecas.unal.edu.co`. Su `robots.txt` no prohíbe nada (`Disallow:` vacío) y publica un sitemap.
- **Aluna** (`aluna.unal.edu.co`): el «único punto de búsqueda» de libros, artículos, tesis y bases. Detrás es **Ex Libris
  Primo VE** (`bibliotecasunal.primo.exlibrisgroup.com`, vista `57UNDC_INST:57UNDC_INST_V1`); la caja de búsqueda del
  portal envía la consulta por GET a ese servicio. ⚠ verificar si ofrece búsqueda de invitado y qué metadatos devuelve
  (¿resumen? ¿DOI?) sin iniciar sesión.
- **Recursos electrónicos** (`bases.unal.edu.co`): **181 recursos**, filtrables por área, tipo de acceso y formato. Buscando
  por nombre encontré, entre otros: **Scopus, Web of Science, ScienceDirect, Wiley Online Library, Springer-Nature Link,
  Sage Journals, Taylor & Francis, Emerald Insight**, EBSCO (**Academic Search Ultimate, Business Source Complete,
  Psychology & Behavioral Sciences Collection, Sociology Source Ultimate**), y de acceso libre OpenAlex, Dialnet, Redalyc,
  SciELO y OPAL (psicología latinoamericana). **PsycINFO y PsycArticles no aparecen por nombre** (0 resultados): es una laguna
  para esta revisión; la colección EBSCO de psicología la cubre en parte (⚠ verificar solapamiento).
- **Proxy**: cada «Descubrir» apunta a un servidor `<base>.unalproxy.elogim.com`, un proxy que reescribe el nombre del
  servidor (estilo EZproxy, operado por un tercero). La relación entre cada base y su servidor la da el propio portal.
- **Entrada**: la página `unalproxy.elogim.com/auth-meta/login.php` ofrece **«Ingresar con @unal.edu.co»** (OAuth de
  Google) o **«Ingresar con credenciales»** (usuario sin el dominio y contraseña).

### 7.2 Límites que publica el propio proxy (los que más importan)

> «Si usted descarga un volumen de información mayor a **250 MB en un periodo de 15 minutos**, se restringirá el acceso a
> su usuario por **8 horas**.»  ·  «Si ingresa sus datos de acceso más de **5 veces** de forma errónea en **5 minutos**,
> se restringirá el acceso por **15 minutos**.»

Consecuencias de diseño (no negociables):

1. **Presupuesto de bytes**: el cliente cuenta **todo** lo que baja por el proxy (HTML y PDF) en una ventana móvil de
   15 min y se corta al llegar a **100 MB** (40 % del límite), con aviso en la interfaz. Un PDF típico de la carpeta pesa
   ≤ 3,4 MB, así que el tope real lo ponen las pausas, no los megabytes.
2. **Nunca reintenta un inicio de sesión.** La app no escribe credenciales; si algo falla, avisa y espera a la persona.
3. **Un solo hilo y pausa de ≥ 8 s** entre peticiones al proxy; selección explícita de qué PDF bajar; sin «bajar todo».

### 7.3 Cómo se inicia sesión sin que el programa vea la contraseña

**Decidido por el responsable (2026-11-25): las credenciales de la UNAL las ingresa siempre el usuario.** El programa no
tiene campo, variable de entorno ni archivo donde guardarlas, ni las pide, ni las repite al fallar. El mecanismo de abajo
(Chrome propio con puerto local temporal) sigue siendo una propuesta que la compuerta 0.4 debe validar; si no pasa, se
usan exportaciones.

El acceso con Google **se niega en navegadores controlados por automatización** (Playwright incluido): lanzarlo ahí fallaría
o empujaría a trucos de evasión que están excluidos. Camino propuesto:

1. «Conectar con la Biblioteca UNAL» abre **tu Chrome real** con un perfil propio (`datos/perfiles/chrome-unal/`) y el
   puerto de depuración abierto **solo en 127.0.0.1**, en la página de acceso del proxy.
2. **Tú** inicias sesión (con tu cuenta `@unal.edu.co` o con credenciales) y haces el segundo factor si lo hay.
3. El programa lee, por ese puerto, **solo las cookies de `unalproxy.elogim.com`**, las guarda en el Administrador de
   credenciales de Windows (`keyring`) y **cierra el puerto**. No toca ninguna otra cookie ni la contraseña.
4. Las peticiones posteriores van con `httpx` y esa cookie, sin navegador controlado, con el ritmo y el presupuesto de
   arriba. Una sonda barata detecta si la sesión venció y lo muestra en `SesionFuente`.
5. «Cerrar sesión y borrar» elimina la cookie del almacén y el perfil de Chrome.

⚠ Alternativa si 0.4 muestra que el puerto de depuración no es aceptable: no automatizar el acceso y trabajar con
exportaciones que tú descargas desde Scopus/WoS/EBSCO (RIS, BibTeX, CSV con resumen) y que la pestaña **importa**. Es la
vía más segura frente a la licencia y no necesita ninguna cookie.

### 7.4 Qué se hace con la sesión viva

- **Buscar** en Aluna (y, si la Biblioteca o la editorial ofrecen una API para afiliados con llave institucional,
  mejor por esa vía: ⚠ verificar en cada editorial). Solo se leen listas de resultados.
- **Obtener el PDF de un candidato seleccionado por ti**, uno a la vez, pasando por el proxy.
- **Bitácora**: cada petición a un servidor con credenciales se anota en `registro.jsonl` (fecha, servidor, ruta sin datos
  personales, bytes) por si la Biblioteca pregunta.
- Orden de preferencia para obtener un texto: copia abierta legal (Unpaywall/CORE/Europe PMC) → API institucional →
  proxy con tu sesión. Lo que se pueda sin gastar la suscripción, no la gasta.

### 7.5 Compuerta de licencia (antes de escribir una línea de la Fase 5)

El proxy dice qué límites aplica, pero **no** dice si la descarga automatizada está permitida: eso lo fijan las condiciones
de cada editorial (muchas prohíben la descarga sistemática y la minería de texto sin permiso). Hay que leer las de las
bases que vayas a usar. Si lo prohíben, la Fase 5 se reduce a la alternativa de arriba (exportaciones tuyas + subir el PDF
a mano, que ya funciona con `POST /articulos`) y el valor de la pestaña se concentra en las fuentes abiertas. La salida
limpia es pedirle a la Biblioteca (chat con el bibliotecario) acceso formal para minería de texto.

## 8. Fases

### Fase 0 · Compuertas (esfuerzo total: M). Si una falla se usa su plan B

| # | Prueba | Talla | Pasa si | Si falla |
|---|---|---|---|---|
| 0.1 | ADR 0011 redactado y aprobado | S | Alcance, límites de ritmo/bytes y exclusiones (sección 1 y 7.2) aceptados | No se avanza |
| 0.2 | Condiciones de uso de las editoriales relevantes y respuesta de la Biblioteca sobre minería | S | Queda por escrito qué se permite (búsqueda, PDF individual, minería) | Fase 5 reducida a exportaciones + subir a mano |
| 0.3 | Cada API abierta: llave, límites, campos de resumen y acceso abierto, medidos con 20 consultas reales | S | Tabla de límites vigentes en el ADR | Se descarta esa fuente |
| 0.4 | Aluna: ¿búsqueda de invitado y qué metadatos? ¿Cookie del proxy utilizable con `httpx`? ¿Puerto de depuración aceptable? | S | Mecanismo reproducible en Windows y medido en MB | Solo exportaciones |
| 0.5 | Fixtures grabadas: respuestas JSON/HTML de cada fuente guardadas para las pruebas | S | Las pruebas no tocan la red | — |
| 0.6 | Clasificación M/R/T de las 59 columnas aprobada por el responsable (`detectabilidad_columnas.json`) | S | Revisada y firmada | Se usan solo las M y las R |

### Fase 1 · Núcleo y fuentes abiertas (esfuerzo total: L)

| # | Entregable | Talla |
|---|---|---|
| 1.1 | Dominio: Búsqueda, Candidato, Hallazgo, Desduplicador, constructor de cadenas (con pruebas unitarias) | M |
| 1.2 | Migración 0009, repositorios SQL, casos de uso `EjecutarBusqueda`, `ListarCandidatos`, `Descartar/Priorizar` | M |
| 1.3 | Cliente HTTP cortés (ritmo por host, caché, reintentos, circuito, presupuesto de bytes) y registro de errores (4.3) | M |
| 1.4 | Adaptadores OpenAlex, Crossref, Semantic Scholar, Europe PMC, CORE, DOAJ + `FuenteGrabada` | M |
| 1.5 | «Ya está en la matriz»: puente en `composicion.py` hacia consulta de matriz por DOI/título (no leer tablas ajenas) | S |
| 1.6 | API REST bajo `/api/v1/proyectos/{id}/busquedas` y `/candidatos`; capacidad `busqueda` en `/capacidades` | S |
| 1.7 | Interfaz: selector de vistas, `PanelBusqueda`, `ListaCandidatos` con casillas, `HistorialBusquedas` | L |

**Aceptación:** una búsqueda sobre 4 fuentes devuelve candidatos únicos; los 47 documentos de la matriz salen marcados;
repetir la búsqueda no duplica; sin red (fixtures) todo pasa.

**Estado de la Fase 1 (2026-11-25):**

| # | Estado | Notas |
|---|---|---|
| 1.1 | Hecho | `descubrimiento/dominio`: `Busqueda`, `Candidato`, desduplicación por DOI y por título parecido, cadena por conceptos con evaluación local, sitios con credenciales |
| 1.2 | Hecho | Migración **0009** (la 0008 ya la ocupaba «lectores»), repositorios SQL, casos de uso de buscar, listar y decidir (priorizar, descartar con motivo, reactivar) |
| 1.3 | Hecho | `ClienteCortes`: ritmo por servidor, `Retry-After` con tope, circuito, caché en disco, presupuesto de bytes, errores sin secretos |
| 1.4 | Parcial | **OpenAlex, Europe PMC y Crossref** con respuestas grabadas. Pendientes: Semantic Scholar, CORE, DOAJ |
| 1.5 | Hecho | Puente en `composicion.py`; compara por título (la matriz no tiene columna DOI) |
| 1.6 | Hecho | `/busqueda/configuracion`, `/busquedas`, `/candidatos`, `/candidatos/decision`; capacidad `busqueda` |
| 1.7 | Hecho | Selector Matriz \| Buscar, cuarta pestaña en teléfono, `PanelBusqueda` con casillas, filtros, progreso por fuente con insignias de error, historial y ficha. **La elección de columnas con prioridad y la vista previa de fila son de la Fase 2** |

Verificado: `ruff`, `mypy`, `lint-imports` (4 contratos, incluido «Descubrimiento no usa modelos de lenguaje»), `alembic check`,
pruebas unitarias e integración nuevas, `tsc` y `vitest`; y a mano en el navegador sobre una base de prueba aparte, con
búsquedas reales a OpenAlex, Europe PMC y Crossref (125 candidatos únicos con límite de 50 por fuente, 8 ya presentes en la
matriz), selección, priorizar y descartar con motivo, en escritorio y en teléfono.

Hallazgos de la ejecución que cambian cosas:

- **OpenAlex ya reparte un presupuesto diario compartido por IP si no hay llave.** Para uso sostenido hace falta la llave
  gratuita que **crea la persona** en su cuenta de OpenAlex; se lee de `OPENALEX_API_KEY` en el `.env` local. Sin ella la
  búsqueda funciona hasta que se agote el cupo y entonces la fuente queda como ERROR (HTTP 429), no se rompe nada.
- OpenAlex rechaza el comodín `*` en su búsqueda con raíces: se quita (`employee*` → `employee`; sus raíces cubren las
  variantes). Europe PMC sí admite el comodín.
- Europe PMC entrega títulos con HTML escapado (`&lt;i&gt;`); se limpian al leerlos.
- Crossref no sabe de lógica booleana y casi no trae resúmenes: se hacen hasta 6 consultas de texto libre y cada resultado se
  vuelve a evaluar en local (con los dos primeros conceptos).

### Fase 2 · Columnas con prioridad, perfil y vista previa (esfuerzo total: L)

| # | Entregable | Talla |
|---|---|---|
| 2.1 | `detectabilidad_columnas.json` + prueba de que cubre las 59 columnas del libro | S |
| 2.2 | Perfil de columnas (dominio, tabla `descubrimiento_perfiles`, API, perfiles guardados) | M |
| 2.3 | Detectores etapa A (metadatos y resumen) generados desde el libro; `Cita` derivada y `Pais` por afiliación | M |
| 2.4 | Cobertura, puntaje y etiquetas (sección 5.3) con recálculo instantáneo al cambiar el perfil | M |
| 2.5 | `SelectorDeColumnas`, `BarraDeSeleccion`, `VistaPreviaDeFila`, exportar CSV/RIS | L |
| 2.6 | Etapa B: texto completo con `pymupdf` + resolutor Unpaywall | M |

**Aceptación (la prueba que importa):** con los **53 PDF ya cargados** y su matriz verificada se mide, columna por columna,
cuántas veces el perfil acierta si hay valor. Meta provisional: ≥ 85 % de acuerdo en las columnas imprescindibles de la
propuesta; si no, se ajustan los detectores o se declara que esa columna no se puede anticipar (se marca «T»). La vista
previa nunca escribe en la matriz (prueba de que el conteo de filas no cambia).

**Estado de la Fase 2 (2026-11-25): 2.1–2.5 hechas; 2.6 (texto completo y Unpaywall) pendiente.**

| # | Estado | Notas |
|---|---|---|
| 2.1 | Hecho | `recursos/detectabilidad_columnas.json` (59 columnas con nivel M/R/T/X y grupo); una prueba exige que coincida exactamente con el libro. **Corrección mía aprobada:** se añadió el nivel **X** (la asigna el equipo o la deriva el programa: `Documento`, `Estudio`, `Covidence #`, `ID muestra`, `Incluir en meta análisi`, `Cultura Hofstede`, `Método obtención r`, `Conjunto MA`); no se pueden elegir. `Pais` es M con «pendiente» si la fuente no trae afiliaciones |
| 2.2 | Hecho | Migración **0010**, tabla `descubrimiento_perfiles`, perfiles guardados, el predeterminado se autoguarda, propuesta inicial de la sección 5.1 |
| 2.3 | Hecho | `recursos/detectores_columnas.json` (27 detectores) y `recursos/paises_iso.json`; motor determinista en `dominio/detectores.py`. Una prueba exige que los valores de vocabulario existan en el libro. `Cita`: regla del responsable; `Pais`: país más frecuente entre las afiliaciones (empate: el del primer autor) |
| 2.4 | Hecho | Cobertura ponderada (5/3/1), máximo posible, etiquetas Probable/Dudoso/Sin datos/Incompleto/No aplica, `exigir` en tres niveles. Lo pendiente de PDF no castiga |
| 2.5 | Hecho | Pestaña «Columnas» (elegir, prioridad, orden con ▲▼, perfiles), barra de cobertura apilada, orden «mejor encaje», **Vista previa** (una fila o comparativa) siempre rotulada «sin verificar», exportar **CSV** (con BOM para Excel) y **RIS** |
| 2.6 | Hecho | Resolutor Unpaywall (en la Fase 3) y **etapa B**: «Analizar texto completo» (ver «Estado de la etapa B» más abajo) |

**Medición contra la matriz verificada** (`herramientas/medir_deteccion.py`; 46 documentos con PDF; el «resumen» se recorta de
la primera página del PDF con una heurística, así que parte del error es de ella). «Acuerdo» = el indicio coincide con algún
valor de la matriz para ese documento:

| Columna | Con dato | Detectado | Acuerdo | Recall | Precisión |
|---|---|---|---|---|---|
| Hedónica/eudaimónica | 46 | 26 | 21 | 46 % | **81 %** |
| Study design | 44 | 22 | 16 | 36 % | **80 %** |
| Sector | 46 | 20 | 16 | 35 % | **80 %** |
| Analysis method (principal) | 46 | 20 | 14 | 30 % | 70 % |
| Teoría 1 | 27 | 7 | 3 | 11 % | 60 % |
| Muestra | 46 | 17 | 10 | 22 % | 59 % |
| Tipo de felicidad real | 46 | 30 | 13 | 28 % | 43 % |
| Instrumento felicidad | 46 | 5 | 1 | 2 % | 20 % |
| Software | 29 | 3 | 1 | 3 % | 33 % |
| Correlación / Beta, fiabilidad, escala de desempeño | — | 0–3 | 0 | ~0 % | — |

Lectura honesta: **la meta provisional (≥ 85 %) NO se cumple en la etapa A**, y era lo esperable para lo que casi nunca está en
un resumen (correlación, β, fiabilidad, instrumentos, software: recall cercano a 0). Cuando el detector habla acierta entre
60 % y 80 % en las columnas de diseño, sector, tipo de felicidad y método, y menos en las demás. Por eso la interfaz presenta
todo como **indicio**, deja esas columnas como «pendiente de PDF» (no «ausente») y las confirma la etapa B. Decisión
pendiente tuya: ¿marcar `Muestra` como «T» (solo PDF) por su precisión de 59 %, o dejarla en «R» como indicio? Hoy queda en R.
Mejoras ya vistas: ajustar `Instrumento felicidad`/`Software` con los nombres que usa la matriz, y leer el país también del
texto cuando la fuente no trae afiliaciones.

Rendimiento: evaluar 126 candidatos con 11 columnas tarda ~0,5 s (la normalización de texto se guarda en caché; antes eran 2 s).

**Estado de la etapa B (2026-11-25): construida y medida; no probada con una descarga real.**

- **Qué hace:** «Analizar texto completo» (hasta 10 por pedido). Usa el PDF ya importado a Artículos si el candidato lo tiene; si no,
  baja la copia abierta (mismos frenos que «Importar», sin importar el artículo). Extrae el texto con `pymupdf` (hasta 80 páginas), corta
  en «References», reconoce las secciones por sus encabezados (método, resultados, discusión, introducción; también con números
  romanos) y corre los detectores. Cada columna se busca solo en las secciones que le corresponden (p. ej. sector, diseño y software
  en el método; correlación y β en resultados; teoría y definiciones en la introducción) y se ignoran las frases de «investigación
  futura». **Guarda solo indicios cortos con su página** («p. 2 · método»): ni el texto ni el PDF (tabla `descubrimiento_analisis`,
  migración 0011).
- **Cómo se combina con la etapa A:** si el resumen ya daba un indicio, se conserva (medido: el cuerpo cita otros estudios y empeora
  la precisión). Si no, vale el del texto completo. Solo con texto **suficiente** (≥ 4 000 caracteres) y una columna que el detector
  sí buscó, la falta de indicio pasa a **«Ausente»**; un PDF casi sin texto (¿escaneado?) no afirma nada. Una imprescindible
  «ausente» vuelve al candidato «Incompleto».
- **Detectores nuevos** solo para el texto completo: número de ítems de cada escala, AFC/CFA y validez, criterios de inclusión y
  exclusión, fechas de recolección (inicio y cierre), definiciones y ejemplos de ítem, método de análisis y validez de las escalas.
  La correlación y la β exigen que la oración nombre la felicidad **y** el desempeño.
- **Interfaz:** botón «Analizar texto completo» en la barra de selección; la columna «Encaje» dice «solo resumen» o «texto completo»; la
  ficha y la vista previa muestran la página de cada indicio. La lista se recalcula con lo hallado.

**Medición de la etapa B** (`herramientas/medir_deteccion.py --etapa B`, 46 documentos, texto completo de sus PDF; precisión = cuando
el detector da un indicio, ¿coincide con la matriz?):

| Columna | Precisión A → B | Recall B | Nota |
|---|---|---|---|
| Study design | 80 % → 80 % | 73 % | |
| Hedónica/eudaimónica | 81 % → 81 % | 54 % | |
| Tipo de muestreo | — → 92 % | 27 % | |
| Direccionalidad de la relación | 100 % → 93 % | 33 % | |
| Start date | — → 88 % | 35 % | |
| Fiabilidad (desempeño / felicidad) | — → 81 % / 76 % | 45 % / 34 % | |
| Validez? / CFA / Validez CFA | — → 79 % / 67 % / 57 % | 24–30 % | |
| Definition Happiness / Performance | — → 100 % / 100 % | 36 % / 18 % | solo comprueba que existan |
| Sector | 80 % → 53 % | 43 % | el cuerpo cita otros sectores |
| Muestra | 59 % → 47 % | 39 % | submuestras y pilotos |
| Instrumento felicidad / escala de desempeño | 20 % / 0 % → 30 % / 5 % | 15 % / 2 % | la matriz usa descripciones largas |
| Correlación / Beta | ~0 % → 20 % / 33 % | 2 % | casi siempre están en **tablas**, que el texto plano no recoge |

Lectura honesta: la etapa B **sube mucho el recall** de lo que el resumen calla (fiabilidad, fechas, validez, definiciones, diseño) y con
buena precisión, pero **no resuelve** lo que vive en tablas (matrices de correlación, coeficientes), ni los instrumentos y teorías, que la
matriz redacta con texto largo. Esas columnas siguen necesitando el PDF y la extracción verificada. La meta global del 85 % no se alcanza;
sí se cumple en columnas concretas (diseño, tipo de muestreo, fechas, fiabilidad). Mejora clara que queda: leer las **tablas** del PDF.

### Fase 3 · Importar al flujo (esfuerzo total: S–M)

Botón «Importar» sobre la selección: obtiene el PDF abierto → `CargarPDF` (mismo rechazo de duplicados por SHA-256) → el
artículo aparece en «Nuevo» del panel de Artículos, con vínculo candidato ↔ artículo y evento `CandidatoImportado`.
**No lanza extracción** (cuesta ~2,6 USD y ~4 min por artículo: se pregunta antes, como ya manda CLAUDE.md).

**Estado de la Fase 3 (2026-11-25): construida y probada con descargas simuladas; sin probar con una descarga real.**

- **Qué hace:** «Importar PDF» sobre la selección (máx. **10 por pedido**: una descarga por decisión, sin «bajar todo»). Por cada
  candidato prueba, en orden, la dirección de acceso abierto que trajo la fuente y lo que **Unpaywall** conoce para su DOI (solo
  si `CONTACTO_API` está configurado: Unpaywall lo exige; el correo va únicamente a Unpaywall). Si la dirección lleva a una
  página en lugar del PDF, lee `citation_pdf_url` (un solo salto). Verifica que el archivo empiece por `%PDF` y tope de 60 MB.
- **Resultado por candidato:** Importado · Ya estaba (misma huella SHA-256, enlaza con el artículo que ya existía) ·
  Sin copia abierta (le dice que lo suba a mano desde Artículos) · No se importó (está descartado) · Error (con la causa). Los
  fallos quedan como ERROR en el Registro.
- **Qué NO hace:** no convierte, no extrae, no escribe en la matriz (pruebas: la fila de artículos queda en «Nuevo», no hay cola
  ni conversión, el conteo de filas de la matriz no cambia). No usa el proxy de la Biblioteca ni credenciales (Fase 5).
- **Se reutiliza** `CargarPDF` de Biblioteca por un puente en `composicion.py`, así que el rechazo de duplicados y el
  almacenamiento son los de siempre. El evento `ArticuloCargado` que ya emite Biblioteca cubre el aviso; no se creó un evento propio.
- **Resolutor Unpaywall** (parte de 2.6) quedó hecho aquí; falta solo la lectura del texto completo (etapa B).
- **Sin probar:** una descarga real de internet. Las pruebas usan respuestas simuladas (PDF directo, página con
  `citation_pdf_url`, página sin PDF, archivo falso, demasiado grande, 404). La primera descarga real conviene hacerla tú con
  un artículo de acceso abierto que elijas.

### Fase 4 · Fuentes sin API: scraping de nivel 2–4 (esfuerzo total: M)

SciELO y Redalyc (OAI-PMH primero), Dialnet (HTML). Respeto de `robots.txt`, pruebas contra HTML grabado y un
**canario** (`herramientas/canario_fuentes.py`, manual) que avisa cuando un sitio cambia de estructura y el adaptador deja
de entender la página. Un adaptador roto se desactiva solo y lo muestra; no devuelve basura en silencio.

**Estado de la Fase 4 (2026-11-25): hecha en lo que los sitios permiten. De los tres sitios previstos, solo Redalyc se pudo leer.**

Se leyó el `robots.txt` de cada sitio **antes** de escribir una línea, y eso cambió el alcance:

| Sitio | Qué encontré | Decisión |
|---|---|---|
| **SciELO** (`search.scielo.org`) | `User-agent: *` → `Disallow: /` (solo permite a Google, Bing y otros buscadores) | **No se lee.** Sus artículos con DOI llegan por OpenAlex y Crossref. Su ArticleMeta/OAI-PMH no sirven para buscar por palabras |
| **Dialnet** | `Disallow: /buscar/*` para todos, y no tiene API | **No se lee.** Igual: lo que tenga DOI llega por OpenAlex y Crossref; lo demás, subir el PDF a mano |
| **Redalyc** | `robots.txt` no prohíbe `/service/`; no publica API de búsqueda, pero su propia página usa un servicio JSON (`service/r2020/getArticles/…`) | **Sí**, con cortesía y como vía **frágil** (no documentada) |

- **Respeto de `robots.txt` (nuevo, genérico):** `ClienteCortes` lee y guarda `robots.txt` (24 h), entiende `*`, `$`, «gana la regla
  más larga» y el grupo propio (`urllib.robotparser` no entiende comodines, así que hay un lector propio con pruebas contra los
  `robots.txt` reales de los tres sitios). Si lo prohíbe, no se pide la página; si no se puede leer (5xx o sin red), se detiene por precaución.
- **Redalyc:** consultas `"a" AND "b"` con términos de los dos primeros conceptos (español primero) y reevaluación local con la cadena;
  filtro de años; autores desde `apellidoNombre`, resumen en todos los idiomas, DOI, palabras clave y el PDF en
  `redalyc.org/journal/<revista>/<artículo>/<artículo>.pdf` (se descubrió mirando las etiquetas `citation_pdf_url` de sus páginas).
- **Autodesactivación:** si el sitio cambia de forma (`ErrorDeEstructura`) **tres veces seguidas**, la fuente se apaga sola, se registra
  como ERROR, queda marcada en la interfaz con el motivo y un botón «Reactivar», y no devuelve nada hasta entonces. Un corte de red o
  un 429 **no** cuentan. El estado vive en `datos/estado_fuentes.json` y sobrevive al reinicio.
- **Interfaz:** SciELO y Dialnet aparecen como «no disponible» con su motivo (para que se sepa que no es un olvido); Redalyc aparece
  como fuente abierta.
- **Canario** (`herramientas/canario_fuentes.py`, a mano, sale a internet): hace una búsqueda mínima por fuente y dice bien/falla/cambió.
  **Ya sirvió:** descubrió que el servicio de Redalyc responde **HTTP 406** si se le pide solo `application/json` (contesta `text/plain`);
  quedó corregido y cubierto por una prueba que repite ese comportamiento.
- **Verificado en vivo:** búsqueda real solo en Redalyc desde la pestaña: 7 candidatos de 2022–2026, todos con PDF abierto.

### Fase 5 · Aluna y bases UNAL con tu sesión (esfuerzo total: L) — solo si pasan 0.2 y 0.4

5.1 `SesionInstitucional`: apertura de Chrome, lectura de cookies del proxy y almacenamiento en `keyring` (M) ·
5.2 sonda de vigencia, aviso y contador de bytes (S) · 5.3 adaptador de búsqueda en Aluna (L) · 5.4 obtención de PDF
individual por proxy (M) · 5.5 frenos, bitácora y pausa ante retos (M) · 5.6 importación de exportaciones RIS/BibTeX/CSV
de Scopus, Web of Science y EBSCO (S–M; esta pieza sirve aunque 0.2 o 0.4 fallen).

**Orden:** 0 → 1 → (2 ∥ 3 ∥ 4) → 5. La importación de exportaciones (5.6) puede adelantarse a la Fase 1 si quieres
resultados de Scopus/WoS cuanto antes sin tocar cookies. La Fase 6 de la v1 (cribado con modelo) **se eliminó**.

## 9. Pruebas

1. **Dominio:** constructor de cadenas, desduplicación (mismo DOI, DOI con distinto formato, sin DOI con título casi igual,
   falsos positivos entre artículos del mismo autor), cobertura y puntaje con prioridades, «No aplica».
2. **Perfil de columnas:** `detectabilidad_columnas.json` cubre exactamente las columnas del libro; cambiar el perfil
   recalcula sin llamadas de red.
3. **Adaptadores por contrato:** cada uno contra sus fixtures grabadas (JSON/HTML), incluyendo página vacía, paginación,
   resultado sin resumen y respuesta 429.
4. **Cliente cortés:** intervalo mínimo por host, `Retry-After`, circuito abierto tras fallos repetidos, caché con
   vigencia, **corte a 100 MB por ventana de 15 min**.
5. **API e integración (SQLite):** ciclo búsqueda → candidatos → seleccionar → vista previa → importar; la vista previa no
   cambia el número de filas de la matriz; en `MODO=nube` se lee igual que en el equipo, se puede buscar (con sesión),
   toda otra escritura da 405 y lo buscado allí llega al equipo sin borrarse ni duplicarse
   (`tests/integracion/test_descubrimiento_nube.py`).
6. **Cero tokens:** una prueba falla si el contexto `descubrimiento` importa el adaptador del modelo o llama a `claude`.
7. **Completitud:** la medición de la Fase 2 contra la matriz verificada.
8. **Arquitectura:** contratos de `import-linter` (dominio sin `httpx` ni `playwright`; `descubrimiento` no importa otros
   contextos).
9. **Interfaz (Vitest):** selector de vistas, ocultar «Buscar» sin capacidad, selección múltiple, orden y prioridad de
   columnas, vista previa.
10. **Manual de extremo a extremo:** buscar → elegir columnas → seleccionar → vista previa → importar un PDF abierto → verlo
    en «Nuevo»; conectar la Biblioteca, ver el semáforo en verde, dejar vencer la sesión y ver el aviso.
11. **Errores marcados:** una fuente simulada que falla (429, 500, HTML irreconocible, sesión vencida, tope de bytes)
    deja líneas `ERROR` con origen `descubrimiento` en el registro, sin cookies, contraseñas ni el correo de contacto, y
    el contador de errores de la interfaz sube.
12. **Seguridad y privacidad:** ninguna contraseña ni cookie en base, logs ni respuestas; el correo de contacto solo en
    `.env` y solo hacia las fuentes abiertas que lo piden (prueba con servidor simulado); `datos/` ignorado por git.

Comandos antes de dar una fase por terminada (desde `backend/`): `ruff check`, `mypy app`, `lint-imports`, `pytest -q`,
`alembic … upgrade head` y `alembic … check`.

## 10. Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Superar 250 MB en 15 min y quedar **8 horas** sin acceso a las bases | Media si se descuida | Alto | Presupuesto de 100 MB, un hilo, pausas, sin «bajar todo», contador visible |
| La licencia de una editorial prohíbe la descarga automatizada | Media | **Alto** (bloqueo de la IP o de la cuenta institucional) | Compuerta 0.2; semiautomático; exportaciones propias como vía alternativa; pedir acceso formal para minería |
| Una editorial detecta tráfico automatizado | Media | Alto | Ritmo humano, un artículo a la vez, parada ante cualquier reto; sin técnicas de evasión |
| El inicio de sesión con Google falla en navegadores automatizados | Alta | Medio | Chrome real del usuario con puerto local temporal; o exportaciones sin cookies |
| Cookie del proxy robable | Baja | Medio | Solo en `keyring`, botón «Cerrar sesión y borrar», puerto de depuración solo en 127.0.0.1 y solo durante el inicio |
| Los resúmenes casi nunca traen `r`/β/fiabilidad: la etapa A engaña | Alta | Medio | Estado «Pendiente de PDF» (no cuenta como ausente), máximo posible visible, etapa B; medido contra los 53 PDF |
| Un sitio cambia su HTML y el adaptador falla en silencio | Alta | Medio | Pruebas con HTML grabado, canario, adaptador que se autodesactiva |
| PsycINFO no está en la Biblioteca (laguna de cobertura) | Alta | Medio | Psychology & Behavioral Sciences Collection, Scopus, WoS, fuentes abiertas; el historial documenta la cobertura |
| Cambian límites o llaves de las APIs | Media | Bajo | Tabla de límites en el ADR; cada fuente se puede apagar por configuración |
| Sesgo de la búsqueda (solo lo abierto) sesga la revisión | Media | Alto | La interfaz muestra cuántos candidatos no tienen texto accesible; el historial documenta fuentes y cadenas |
| Playwright engorda el instalador o la imagen de la nube | Media | Bajo | Extra opcional `[busqueda]`; solo para el nivel 4 |

## 11. Decisiones (todas cerradas el 2026-11-25) y lo que sigue pendiente

| # | Tema | Decisión | Quién |
|---|---|---|---|
| 1 | Credenciales UNAL | **Las ingresa siempre el usuario**; el programa no las pide ni guarda (7.3). Cómo se captura la sesión después (Chrome con puerto local temporal o exportaciones) lo valida la compuerta 0.4 | Responsable |
| 2 | Límites y evasión | Aceptados: una descarga por decisión del usuario, 100 MB por ventana de 15 min, sin evasión. **Los errores se marcan en el registro** (4.3) | Responsable |
| 3 | Metadato → matriz | **No** rellena `Cita`, `Title`, `Author`, `Año` por defecto: solo vista previa. Podría ofrecerse un interruptor explícito más adelante, apagado | Responsable |
| 4 | Clasificación M/R/T y perfil inicial | **Aprobadas, con corrección mía.** Corregí que `Pais` es M solo cuando la fuente trae afiliaciones con país; si no, pasa a R/T. `Cita`: regla de abajo. Se versiona en `recursos/detectabilidad_columnas.json` | Responsable aprueba, yo corrijo |
| 5 | Años | **2020 hasta la fecha** de la búsqueda (extremo superior = hoy, no fijo). La matriz ya contiene estudios de 1999 a 2023: el filtro solo aplica a lo nuevo; «ya en la matriz» sigue comparando contra todo | Responsable |
| 6 | Sin IA | Ninguna llamada a un modelo en la pestaña, ni opcional. Lo impide una prueba (sección 9, punto 6) | Responsable |
| 7 | Correo de contacto | En `CONTACTO_API` del `.env` local, solo hacia fuentes abiertas (sección 3) | Responsable |

### Lo que fijé yo («la que tú decidas»), revisable cuando quieras

- **Idiomas:** inglés, español y portugués (SciELO, Redalyc y Dialnet publican en los dos últimos).
- **Tipos:** artículos de revista; **preprints incluidos pero marcados «preprint»**; revisiones y metaanálisis incluidos pero
  marcados «No aplica» (sirven para rastrear referencias, no aportan una correlación primaria). Excluidos de entrada:
  libros, capítulos, tesis, reseñas y editoriales. Todo exclusión se puede reactivar y queda en el historial.
- **Cadena inicial** (en título, resumen y palabras clave; editable en `PanelBusqueda`):
  - *Felicidad:* `happiness` · `"subjective well-being"` · `"psychological well-being"` · `hedonic` · `eudaimonic` ·
    `"happy-productive"` · `felicidad` · `"bienestar subjetivo"` · `"bienestar psicológico"` · `eudaimonía` · `felicidade`.
  - **AND** *Desempeño:* `"job performance"` · `"work performance"` · `"task performance"` · `"employee performance"` ·
    `"desempeño laboral"` · `"rendimiento laboral"` · `"desempenho no trabalho"` · `productivity`.
  - **AND** *Contexto:* `employee*` · `worker*` · `workplace` · `empleado*` · `trabajador*`.
  - Apagados por defecto, con casilla para sumarlos: `"job satisfaction"`, `"work engagement"` (amplían mucho y meten ruido).
- **`Cita`** (solo en la vista previa), según lo que muestran los 47 documentos de la matriz: 1 autor → `Apellido (año)`;
  2 → `Apellido y Apellido (año)`; 3 o más → `Apellido et al. (año)`. En la matriz hoy hay una excepción
  (`Peiro, Kozusznik, Soriano (2019)`, con los 3 apellidos): la regla elegida es la mayoritaria, y no se reescribe nada existente.
- **`Author`** (solo vista previa): `Nombre Apellido; Nombre Apellido`, como en `Sattar` o `Bryson`; el original queda en la
  ficha del candidato.

### Pendiente de ti (no bloquea la Fase 0 ni la 1)

| # | Pregunta | Para qué |
|---|---|---|
| A | ¿Puedes preguntar al chat del bibliotecario si hay permiso de minería de texto y una API para Scopus/WoS? | Compuerta 0.2 |
| B | ¿Qué cuenta usarás (`@unal.edu.co` por Google, o usuario y contraseña)? | Probar 0.4 |

## 12. Primer paso concreto

Con las decisiones de arriba ya se puede ejecutar la **Fase 0** (sin credenciales) y la **Fase 1**: una pestaña útil con
fuentes abiertas, selección, columnas con prioridad, vista previa de metadatos y errores marcados en el registro. La
parte de la Biblioteca UNAL se decide después con la licencia de cada editorial en la mano; mientras tanto, la importación
de exportaciones RIS/CSV de Scopus y Web of Science (5.6) permite usar esas bases sin automatizar nada.

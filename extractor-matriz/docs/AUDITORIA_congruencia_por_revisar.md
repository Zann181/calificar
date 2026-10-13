# Auditoría de congruencia: matriz manual (Excel) vs extracción de la IA, artículos POR_REVISAR

Fecha: 2026-10-07. Artículos: Sattar, Bibi 2022, Ayala 2017, Kozusznik 2019 (estado `POR_REVISAR` en `datos/extractor.db`).

## 0. Cómo se hizo y cómo leer este informe

**Árbitro de cada discrepancia.** No basta con saber quién coincide con el PDF: el Excel y la IA pueden leer bien el PDF y aun así no seguir la norma. Cada discrepancia se juzgó contra `recursos/Libro_de_codigos_extraccion_v2.json` (capa normativa: `instruccion_operativa`, vocabularios y reglas de desempate) y contra el PDF. Cada fila de la sección 3 lleva uno de estos veredictos:

| Veredicto | Significa |
|---|---|
| IA cumple | La IA sigue la norma y el Excel no |
| Excel cumple | El Excel sigue la norma y la IA no |
| Ambos | Los dos son defendibles o iguales |
| Ninguno | Ni la IA ni el Excel cumplen la norma |
| Norma calla | El libro no decide el caso. Pasa a la sección 7 como pregunta |

**Lectura de los PDF.** El extractor no usa `pdftotext`: usa MinerU (reconoce tablas y da coordenadas) y PyMuPDF para anclar citas. En una primera pasada de esta auditoría un sub-agente leyó los PDF con `pdftotext`, que desordena las tablas. Esa pasada se descartó y se repitió con la salida de MinerU (la que el extractor ya guardó) más cada página renderizada como imagen. Todo número de tabla se confirmó celda por celda en la imagen. Lo que no se pudo asegurar está marcado como pendiente (sección 8).

**Comparación columna a columna.** Se hizo por posición de columna (letra de Excel), no por nombre. El libro de códigos tiene columnas con nombre repetido (`cómo lo llaman`, `Fiabilidad Alfa - Omega` y `Analysis method` aparecen dos veces), y la primera versión de este informe las confundió.

### Correcciones a versiones anteriores de este informe

Estas afirmaciones de versiones previas eran erróneas y quedan retiradas:

1. **"La IA no llena `cómo lo llaman`, `Fiabilidad` y `Analysis method`": falso.** Era un error de la comparación (columnas duplicadas). La IA las llena.
2. **"La IA mezcló datos de otro artículo (513 o 467 en Kozusznik)": sin sustento.** Las celdas `Muestra` de Kozusznik contienen 80, 83 y 80, con n = 80–82 de la Tabla 1 y N = 83 de la sección de muestra. La cifra salió de un resumen de sub-agente y no se encontró en la base.
3. **`# Ítems` y `Items instrumento1`:** la norma pide los ítems **retenidos**, así que el 3 y el 5/22 de la IA son lo correcto, y el 7 y el 11/28 del Excel no.
4. **Teorías en Sattar:** la norma manda la teoría citada en la hipótesis felicidad→desempeño. En el PDF esa hipótesis (H4, H5) cita work adjustment. El orden de la IA es el correcto y el del Excel no.
5. **Direccionalidad en Ayala:** la norma codifica por el coeficiente de la fila; con r = .41** corresponde HP, como puso la IA.
6. **Año de Savickas en Sattar:** 2011 es el que cita el artículo para career construction, así que la IA tenía razón en ese dato.

## 1. Resultado global

| Artículo | Filas Excel | Filas IA | Columnas que coinciden (de 54) | Resumen contra la norma |
|---|---|---|---|---|
| Sattar | 2 | 2 | 32 | La IA cumple en teoría, muestreo, medición del desempeño y coeficiente. Fallos menores de la IA en códigos de faltante |
| Bibi | 2 | 2 | 30 | La IA cumple en ítems, método y ejemplos. El Excel cumple en "adaptado al trabajo" |
| Ayala | 1 | 1 | 31 | La IA cumple en correlación, direccionalidad y teoría. Hay dos casos donde la norma calla |
| Kozusznik | 1 | 3 | 21–24 | **Es donde la IA falla de verdad:** elige un coeficiente no significativo y crea una fila de más |

**Conclusión.** Frente a la norma, la IA es más fiel que el Excel en la mayoría de los campos discrepantes. El Excel infiere cosas que el libro prohíbe inferir (conveniencia, autoinforme, ítems originales). Los fallos reales de la IA se concentran en la elección del coeficiente en estudios con muchas estimaciones (Kozusznik) y en algunos casos puntuales (sección 4). El resto son preguntas que el libro no resuelve.

## 2. Dónde se concentra la incongruencia (mapa por campo)

Para cada una de las 54 columnas se contó en cuántas de las 8 filas de la IA el valor difiere de la fila equivalente del Excel (Kozusznik pesa más: sus 3 filas se comparan contra una sola). Se normalizaron mayúsculas, tildes y números (0,59 = 0.59), y una coincidencia parcial de texto cuenta como acuerdo. **43 de 54 columnas difieren en al menos una fila y 11 difieren en las 8.**

| Tipo | Definición | Gravedad |
|---|---|---|
| D. Formato o vocabulario | Mismo dato escrito distinto | Baja |
| B. Redacción libre | Texto largo parafraseado por la IA y copiado o traducido en el Excel | Media: impide comparar |
| C. Dato distinto | Cambia el valor, la categoría o la teoría | Alta: hay que ir al PDF y a la norma |

### 2.1 Columnas con más diferencias

| Diferencias | Columna | Tipo | Qué pasa | Quién sigue la norma |
|---|---|---|---|---|
| 8 de 8 | `Teoría 1`, `Teoría 2` | C | Teorías distintas o en otro orden | La IA en Sattar, Ayala y probablemente Bibi. En Kozusznik hay que revisar |
| 8 de 8 | `Correlacion o Beta felicidad` | C/D | El Excel usa texto libre ("Betas 0,514", "Cluster…"); la IA usa el formato de la norma: Correlación r (tabla, página) y Beta (tabla, página) | La IA |
| 8 de 8 | `Ejemplo ítem felicidad`, `Ejemplo ítem desempeño` | C | Excel vacío o con la definición del constructo; IA con ítem y página | La IA, salvo Bibi (pendiente) |
| 8 de 8 | `Definition Happiness`, `Definition Performance`, `Aim of study`, `Conclusion`, `Tipo de desempeño`, `Analysis method (detalle)` | B | Paráfrasis vs texto copiado | Ninguno de los dos: ver pregunta 12 |
| 7 de 8 | `Población`, `Escala de medición: Performance`, `Tipo de felicidad real` | B/D | Etiquetas con redacción distinta | Ambos |
| 6 de 8 | `Tipo de muestreo` | C | Excel infiere "Conveniencia"; IA copia lo que dice el artículo o "No indica" | La IA |
| 6 de 8 | `Beta Fel 1- JP` | C | La IA la deja vacía en 6 filas | Depende del caso (sección 3) |
| 6 de 8 | `Teoria 3`, `End date` | C | La IA completa lo que el Excel deja vacío | Ver preguntas 8 y 11 |
| 6 de 8 | `Analysis method (principal)` | C | "Correlación" o "MSEM" vs "Análisis de conglomerados" o descripción larga | Norma calla en Ayala |
| 5 de 8 | `Start date`, `Validez CFA`, `Validez de las escalas`, `Instrumento felicidad`, `Software`, `Estudio` | D/B | Formato | Ambos; `Estudio` ver pregunta 10 |
| 4 de 8 | `Correlación Feli 1 - JP` | C | Excel "No reporta"; IA 0.41 (Ayala) o vacío (Kozusznik) | La IA en Ayala |
| 3 de 8 | `Direccionalidad`, `Adaptado al trabajo`, `Método de aplicación`, `Inclusion criteria`, `Fiabilidad (desempeño)` | C | Valores opuestos | Caso a caso (sección 3) |
| 2 de 8 | `# Ítems`, `Items instrumento1`, `Muestra`, `Covidence #`, `How measure…` | C | Ver sección 3 | La IA en ítems y medición |

### 2.2 Lectura por bloque

1. **Coeficientes.** Alimentan el meta-análisis. La diferencia viene de que el Excel mezcla tipos de coeficiente (B no estandarizado en la columna Beta; "No reporta" aunque haya una correlación en la Tabla 1) y de que la IA elige mal en un caso (Kozusznik).
2. **Teorías.** Diferencia en las 8 filas. La norma da un criterio claro (la primera teoría citada en la hipótesis felicidad→desempeño) y la IA lo aplica; el Excel no lo sigue.
3. **Metodología (muestreo, método, medición del desempeño).** El Excel infiere y la norma lo prohíbe ("no asumir conveniencia", "no inferir autoinforme", "no deducir el método").
4. **Estructura de filas.** Kozusznik (3 filas contra 1) es el único caso de discrepancia estructural real.
5. **Texto libre.** Diferencia de estilo; la norma pide cita literal, el Excel traduce.

### 2.3 Por artículo

| Artículo | Coinciden | Observación |
|---|---|---|
| Kozusznik | 21–24 de 54 | El más incongruente: filas, coeficiente y direccionalidad |
| Bibi | 30 de 54 | Diferencias de ítems (el Excel cuenta originales), teorías y método |
| Ayala | 31 de 54 | Diferencias de correlación, método y teorías |
| Sattar | 32 de 54 | Diferencias de teorías, beta y muestreo |

## 3. Veredicto por discrepancia (norma + PDF)

Páginas del PDF.

### 3.1 Bibi 2022 (Excel estudios 4 y 5; IA filas 4 y 5)

| Campo | Excel | IA | Qué dice el PDF | Norma | Veredicto |
|---|---|---|---|---|---|
| `# Ítems` (escala de desempeño) | 7 | 3 | Innovación: 7 ítems aplicados, 3 retenidos (Tabla 2) | Ítems retenidos; los aplicados van a trazabilidad | IA cumple |
| `Items instrumento1` | 11 (hedónica) y 28 (eudaimónica) | 5 y 22 | 11→5 y 28→22 (Tabla 2) | Retenidos | IA cumple |
| `Teoría 1/2` | Autodeterminación / satisfacción de necesidades | Maslow-Sirgy 2001 / autodeterminación (Patrick) | Las hipótesis felicidad→innovación (H5, H6) vienen precedidas por Sirgy 2001, que parte de la teoría de Maslow (§2.4). Autodeterminación sustenta otras rutas | Primera teoría citada en la hipótesis felicidad→desempeño | IA cumple (confirmar lectura completa del §2.4) |
| `Método de aplicación` | on-site | No indica | Solo dice "distributed… with small souvenirs" (p. 8) | No deducir | IA cumple |
| `Ejemplo ítem felicidad` | Con texto | No indica | Los ítems están en un apéndice suplementario fuera del PDF | Ítem del artículo o anexo, con página | IA cumple |
| `Adaptado al trabajo` (fila 5) | Si | No indica | Sí, referida al trabajo (p. 9) | Si cuando los ítems o la consigna se refieren al trabajo | **Excel cumple** |
| `Correlación y Beta` | Beta .514 y .766 | r .770 y .787; β .514 y .766 | Tabla 3 y Tabla 5 coinciden con la IA. El texto de H5 y la Figura 2 dicen .541 / .54 | Registrar la fuente de mayor precedencia y anotar la discrepancia | Ambos (ver pregunta 6) |
| `Fiabilidad (felicidad)` | 0.738 y 0.871 | Igual | Son CR (fiabilidad compuesta); los alfas están en otras columnas de la Tabla 2 | La norma acepta alfa, omega o CR | Ambos |
| `Inclusion criteria` | No indica | Hoteles 4–5 estrellas, Shanghái | No hay criterios individuales, sí de la muestra de hoteles | Ver pregunta 12 | Ambos |
| `Ejemplo ítem desempeño` | Con texto | No indica | **Pendiente de verificar** | | Pendiente |

### 3.2 Ayala 2017 (Excel estudio 6; IA fila 6)

| Campo | Excel | IA | Qué dice el PDF | Norma | Veredicto |
|---|---|---|---|---|---|
| `Correlación Feli 1 - JP` | No reporta | 0.41 | Tabla 1 (p. 10): .41** entre satisfacción laboral y desempeño innovador | Correlación de orden cero reportada | IA cumple |
| `Direccionalidad` | "4 tipos de relación" (no es un valor del vocabulario) | HP | Diseño transversal; r = .41** | Se codifica por el coeficiente de la fila; "HP: positivo y significativo"; en transversal es asociación, no causalidad | IA cumple |
| `Teoría 1` | Intercambio social (Blau) | Trabajador feliz y productivo (Staw) | No hay hipótesis felicidad→desempeño; el marco general declarado es la tesis feliz-productivo (p. 2) | Sin hipótesis, la teoría del marco general declarada como base | IA cumple |
| `Método de aplicación` | Teléfono | on-site | Contacto telefónico con selección de ruta aleatoria; el cuestionario se aplicó cara a cara en el domicilio (p. 8) | on-site es "presencial en el lugar de trabajo"; Teléfono es "entrevista telefónica" | Norma calla (pregunta 4) |
| `Analysis method (principal)` | Análisis de conglomerados | Correlación | La relación se estima con Tabla 1 (r) y los patrones con conglomerados | "Técnica que produjo el coeficiente de la fila" | Norma calla (pregunta 5) |
| `Muestra` | 513 | 513 | 513 en conglomerados (texto); 467 en discriminantes (Tablas 2–3); la Tabla 1 no indica N | N de la tabla de donde sale el coeficiente | Ambos; ver pregunta 6 |
| `Fiabilidad` | 0.94 (felicidad) | Igual | α .94 es satisfacción; .83 es desempeño innovador | | Ambos |
| `End date` | No indica | 2011 | "Sexta ola de 2011" | Formato AAAA permitido | Ambos (pregunta 11) |

### 3.3 Kozusznik 2019 (Excel estudio 7: 1 fila; IA filas 72, 73, 74)

Diseño verificado en las tablas: 83 oficinistas, 603 observaciones, 4 días consecutivos, 2 veces al día. H1 es autoinformado y prospectivo (tarde → mañana siguiente); H2 es el desempeño global evaluado por el supervisor; el bienestar hedónico es solo control ("above and beyond").

| Campo | Excel | IA | Qué dice el PDF | Norma | Veredicto |
|---|---|---|---|---|---|
| Número de filas | 1 (eudaimónica → supervisor) | 3 | Dos fuentes de desempeño con coeficientes separados (autoinforme H1, supervisor H2); hedónico es solo control | Fuente evaluadora distinta con coeficiente separado abre fila nueva; en oleadas, una fila por par con la correlación prospectiva | Filas 72 y 73 correctas; la 74 (covariable) dudosa (pregunta 1); el Excel omite la fila autoinformada |
| Coeficiente de la fila 72 | n/a | .02 (mismo día, no significativo) | La relación prospectiva significativa es .30 [.05; .56] (Tabla 1, p. 14) | Prospectiva de retardo más corto | **IA falla** |
| Coeficiente de la fila 73 | .71 [.49; .93] | .71 (en la celda general; `Beta Fel` vacío) | .71 es H2, solo en el texto (p. 14), sin tabla | Beta solo estandarizado (pregunta 2) | Ambos coinciden en el valor; la IA no lo lleva a la columna Beta |
| Coeficiente de la fila 74 | n/a | −.15 | Es la covariable hedónica del mismo día, no un hallazgo | | IA falla (si se acepta la fila) |
| `Direccionalidad` | HP | 72: No relation; 74: No relation | H1 parcial (soportada tarde→mañana), H2 sí, H3 (inversa) no | Por el coeficiente de la fila; HP si positivo y significativo | **IA falla en la fila 72** (consecuencia del coeficiente mal elegido) |
| `Muestra` | 83 | 80, 83, 80 | N = 83 personas (p. 9); la Tabla 1 indica n = 80–82 | Multinivel: personas. También: "N de la tabla de donde sale el coeficiente; rango: el menor" | Norma calla (pregunta 3) |
| `Adaptado al trabajo` | Si | No | Las escalas se refieren a "positive emotions at work" y "activities … worthwhile" (§2.3.1) | Si cuando consigna o ítems se refieren al trabajo | **Excel probablemente cumple**; confirmar la consigna literal |
| `Start/End date` | Descripción del diseño | No indica | Sin fechas de calendario | Formato AAAA / No indica | IA cumple |
| `Tipo de muestreo` | Conveniencia | Otro: no aleatorio | "was not random" | No asumir conveniencia | IA cumple |
| `Ejemplo ítem felicidad` | Definición del constructo | "worthwhile and meaningful" | p. 11 | Ítem tal como aparece | IA cumple |
| `Teoría 2/3` | OIT | Park 2010 / Kahn 1990 | SDT y OIT están en las hipótesis; Park y Kahn: **pendiente** de ver si se citan en la hipótesis | "Una teoría mencionada solo de paso no cuenta" | Pendiente (pregunta 8) |
| `Fiabilidad (desempeño, fila 73)` | 0.74 | 0.86 | **Pendiente de verificar** | | Pendiente |
| `Incluir en meta análisi` | "mulinivel" | "Multinivel" | | Vocabulario controlado: "Multinivel" | IA cumple |

### 3.4 Sattar (Excel estudios 2 y 3; IA filas 75 y 76)

| Campo | Excel | IA | Qué dice el PDF | Norma | Veredicto |
|---|---|---|---|---|---|
| `Teoría 1` | Career construction (Savickas 1997) | Work adjustment (Dawis 1968) | Las hipótesis felicidad→desempeño H4 y H5 citan work adjustment (p. 3). Career construction sustenta H2 y H3 (adaptabilidad→desempeño) | Primera teoría citada en la hipótesis felicidad→desempeño | **IA cumple** |
| `Teoría 2` | Work adjustment | Career construction (Savickas 2011) | El año que cita el artículo para career construction es 2011 | Año y autores: los que cita el artículo | IA cumple |
| `Beta Fel 1- JP` | 0.4 y 0.28 | Vacío, estado "No aplica" | Son B no estandarizados (Tabla 2, p. 5), tramo felicidad→desempeño del Modelo 4 de PROCESS; SE .06 y .05 | Beta: solo estandarizado | IA cumple en el valor; el código de faltante debería ser "No indica", no "No aplica" (pregunta 7) |
| `Correlación` | .59 y .34 | Igual | Tabla 1: felicidad–in-role .59, felicidad–extra-role .34 | | Ambos |
| `How measure performance` | Self perception | No indica | Ítems en primera persona; los supervisores solo repartieron los cuestionarios; no dice "autoinforme" | No inferir autoinforme | IA cumple |
| `Tipo de muestreo` | Conveniencia | No indica | No lo declara | No asumir conveniencia | IA cumple |
| `Tipo de felicidad real` | Engagement / Pleasure / Meaning | Orientación a la felicidad, total | El análisis usa un solo puntaje total (α .71) | Constructo que mide el instrumento | IA cumple |
| `Fiabilidad (desempeño)` | .72 (in-role) y .84 (extra) | .84 y .72 | El texto da in-role .72 y extra-role .84; la diagonal de la Tabla 1 los invierte | Fuente de mayor precedencia + discrepancia | Norma calla (pregunta 6) |
| `Covidence #` | 580 | Vacío | No aparece en el PDF | Si el equipo no lo entrega: PENDIENTE_EQUIPO | Revisar flujo (pregunta 13) |
| `Software`, `Analysis method` | SPSS 22 / PROCESS | SPSS V22 / PROCESS | Modelo 4 PROCESS, bootstrap 5000 | | Ambos |

## 4. Defectos de la IA a corregir (violan la norma)

| # | Artículo | Defecto | Norma | Prioridad |
|---|---|---|---|---|
| 1 | Kozusznik, fila 72 | Toma el coeficiente del mismo día (.02, no significativo) en lugar del prospectivo significativo (.30 [.05; .56], Tabla 1) | Una fila por par con la correlación prospectiva de retardo más corto | Alta |
| 2 | Kozusznik, fila 72 | `Direccionalidad` = "No relation" como consecuencia del punto 1 | Se codifica por el coeficiente de la fila | Alta |
| 3 | Kozusznik, filas 72–74 | `Beta Fel 1- JP` vacía en las tres filas, aunque el artículo reporta estimaciones "Est." (pendiente de decidir si cuentan como estandarizadas: pregunta 2) | Todo número de Correlación y Beta debe aparecer en la celda general, y la columna específica se llena si aplica | Alta |
| 4 | Kozusznik, fila 74 | Crea fila para una covariable de control como si fuera hallazgo | Pendiente de decisión (pregunta 1) | Media |
| 5 | Bibi, fila 5 | `Adaptado al trabajo` = "No indica" cuando el artículo lo dice (p. 9) | Si cuando los ítems se refieren al trabajo | Media |
| 6 | Kozusznik | `Adaptado al trabajo` = "No", probablemente erróneo | Idem | Media |
| 7 | Sattar | Beta vacío con estado "No aplica", cuando corresponde "No indica" | "No aplica" se reserva para el artículo que solo modela desempeño→felicidad | Baja |
| 8 | Sattar | `Covidence #` vacío; la norma pide `PENDIENTE_EQUIPO` si no lo recibe | Insumos del extractor | Baja |
| 9 | Varios | `Teoria 3` completada en 6 de 8 filas con teorías que el Excel no registra y que podrían ser menciones de paso | "Una teoría mencionada solo de paso no cuenta" | Media: verificar |

## 5. Defectos del Excel (violan la norma o el PDF)

| # | Artículo | Defecto | Norma o evidencia |
|---|---|---|---|
| 1 | Bibi | `# Ítems` = 7 y `Items instrumento1` = 11 y 28 son ítems aplicados | La norma pide los retenidos |
| 2 | Ayala | `Correlación Feli 1 - JP` = "No reporta" | Tabla 1 (p. 10): .41** |
| 3 | Ayala | `Direccionalidad` = "4 tipos de relación" | Fuera del vocabulario cerrado |
| 4 | Sattar y Kozusznik | `Tipo de muestreo` = Conveniencia | No asumir conveniencia |
| 5 | Sattar | `How measure performance` = Self perception | No inferir autoinforme |
| 6 | Bibi | `Método de aplicación` = on-site | No deducir |
| 7 | Sattar | `Teoría 1` = career construction; Savickas 1997 | La hipótesis felicidad→desempeño cita work adjustment; el artículo cita Savickas 2011 |
| 8 | Sattar | Beta = 0.4 y 0.28 (B no estandarizado) | Beta: solo estandarizado |
| 9 | Kozusznik | `Ejemplo ítem felicidad` = definición del constructo | Debe ser un ítem literal |
| 10 | Kozusznik | `Start/End date` con el diseño de medición | Formato AAAA o No indica |
| 11 | Kozusznik | Falta la fila de la relación autoinformada (H1, .30) | Fuente evaluadora distinta abre fila |
| 12 | Varios | `Correlacion o Beta felicidad` en texto libre | Formato de la norma |

## 6. Inconsistencias internas de los propios artículos

No son errores de la IA ni del Excel: el artículo se contradice y la norma (P4) pide registrar la fuente de mayor precedencia y anotar la discrepancia.

| Artículo | Contradicción |
|---|---|
| Bibi | β hedónica: .514 en la Tabla 5 y .541 en el texto de H5 y la Figura 2. La tabla además rotula "EDU→EIN" por error |
| Bibi | El artículo nombra "purpose in life" donde debería decir relaciones positivas y no informa que se eliminó 1 ítem (7→6) |
| Sattar | Alfas del desempeño: .72 / .84 en el texto y .84 / .72 en la diagonal de la Tabla 1 |
| Ayala | N: 513 (conglomerados, texto) y 467 (discriminantes, Tablas 2–3); la Tabla 1 no indica su N |
| Ayala | Celdas mal impresas en la Tabla 1 ("17**", "39**") |
| Kozusznik | La Discusión (p. 17) dice que no hubo relación con la evaluación del supervisor, lo que contradice H2 (.71) |
| Kozusznik | El IC de H5 en el texto omite el signo menos; 7.61 observaciones por persona no cuadra con 603/83 = 7.27 |

## 7. Preguntas que la norma no resuelve

Solo están las preguntas donde el libro de códigos calla o es ambiguo. Todo lo demás ya está decidido por la norma (sección 3).

| # | Pregunta (con el caso del PDF que la origina) | Respuesta del responsable del dominio |
|---|---|---|
| 1 | **Covariable de control como fila.** En Kozusznik el bienestar hedónico aparece en H1 y H2 solo como control ("above and beyond"). La norma abre fila cuando cambia el indicador de felicidad. ¿Se abre fila cuando el indicador es solo una covariable, o solo cuando el artículo lo pone como predictor del desempeño? | |
| 2 | **¿Qué es "estandarizado" en estimaciones bayesianas?** Kozusznik reporta "Est." (.30, .71) de modelos bayesianos multinivel sin decir si están estandarizadas. Beta admite "solo estandarizado". ¿Se registran en `Beta Fel 1- JP`, o quedan solo en la celda general y `otros_coeficientes`? | |
| 3 | **N en estudios multinivel.** La norma dice "personas" (83) y también "N de la tabla de donde sale el coeficiente; con rango, el menor" (Tabla 1: n = 80–82 → 80). ¿Cuál manda cuando chocan? | |
| 4 | **Método de aplicación sin código.** Ayala: contacto telefónico, entrevista presencial en el domicilio. `on-site` es "presencial en el lugar de trabajo" y `Teléfono` es "entrevista telefónica". ¿Se agrega una categoría (p. ej. "Presencial en domicilio") o se usa "No indica"? | |
| 5 | **Analysis method (principal) cuando el coeficiente y el diseño difieren.** En Ayala el coeficiente (.41) sale de una correlación (Tabla 1), pero el análisis central es de conglomerados. La norma dice "técnica que produjo el coeficiente de la fila". ¿Se codifica Correlación o Análisis de conglomerados? ¿Y entra esta fila al meta-análisis? | |
| 6 | **Orden de precedencia entre fuentes del mismo artículo.** P4 pide "la fuente de mayor precedencia", pero no se ve el orden en el libro. Casos: Bibi .514 (tabla) vs .541 (texto/figura); Sattar alfas del desempeño (texto vs Tabla 1); Ayala N 513 vs 467. ¿Tabla > texto > figura? ¿Resumen < resultados? | |
| 7 | **Código de faltante para Beta cuando solo hay B no estandarizado** (Sattar). La IA usó "No aplica"; la norma reserva "No aplica" para el artículo que solo modela desempeño→felicidad. ¿"No indica"? ¿Y el B va a `otros_coeficientes`? | |
| 8 | **Teoría 2 y Teoría 3.** El libro define Teoría 1 con precisión; para 2 y 3 solo dice "igual que Teoría 1". ¿Se llenan solo con teorías citadas en hipótesis o también las del marco general? ¿Hay tope (hoy la IA llena Teoría 3 en 6 de 8 filas)? | |
| 9 | **Kozusznik y la regla de oleadas.** La norma manda una sola fila por par con la correlación prospectiva de retardo más corto, pero también abre fila por fuente evaluadora (autoinforme vs supervisor). El artículo mezcla ambas: H1 es prospectivo y autoinformado; H2 es global semanal evaluado por el supervisor y no es prospectivo. ¿Confirma que son 2 filas (H1 con .30 y H2 con .71)? | |
| 10 | **Conciliación con el Excel.** La fila 7 del Excel (Kozusznik, "multinivel, no tener en cuenta") se reemplazaría por 2 filas de la IA. ¿Se conserva la numeración del Excel y se agregan filas nuevas, o la IA asigna números nuevos (hoy 72–76)? ¿Cuál es la "verdad de referencia" para calibrar: la norma o el Excel? | |
| 11 | **Fechas con solo la oleada.** Ayala dice "sexta ola de 2011". ¿Start y End son ambos 2011? | |
| 12 | **Texto libre.** La norma pide cita literal en el idioma original, pero el Excel traduce y la IA parafrasea ("Paráfrasis: …"). Para `Definition Happiness`, `Definition Performance`, `Aim of study`, `Conclusion` e `Inclusion criteria` (¿criterios de participantes o de la muestra de organizaciones?), ¿qué formato se calibra? | |
| 13 | **Identificadores.** ¿Qué número entrega el equipo a la app (Documento, Estudio inicial, Covidence #)? En Sattar `Covidence #` quedó vacío; el libro pide `PENDIENTE_EQUIPO` si no se recibe. | |

## 8. Pendientes de verificación (resueltos el 2026-10-12)

Leídos en el PDF con PyMuPDF; las páginas son del PDF.

| Pendiente | Qué dice el PDF | Veredicto |
|---|---|---|
| Bibi: `Ejemplo ítem desempeño` | Innovación se mide con 7 ítems adaptados de George y Zhou (2001). "The items of all the scales mentioned are provided in the Supplementary Appendix" (p. 9). Ningún ítem aparece en el texto ni en las tablas | **IA cumple** ("No indica"). El ítem del Excel sale del apéndice, que no está en el PDF |
| Bibi: §2.4 completo | El §2.4 (p. 7) cita Sirgy et al. (2001), "based on Maslow's need theory", y de ahí deriva H5 y H6 (p. 8). No cita autodeterminación en ese tramo | **IA cumple**: Teoría 1 = Maslow / Sirgy 2001 |
| Kozusznik: consigna de `Adaptado al trabajo` | Hedónico: "how they had been feeling at work in the past couple of hours" (p. 10). Eudaimónico: "whether they felt the activities they had been doing in the past couple of hours were '…worthwhile and meaningful'" (p. 10–11); la consigna no dice "at work", aunque se aplicó en la oficina durante la jornada | Hedónico: **Excel cumple** ("Si"). Eudaimónico: la consigna literal no nombra el trabajo; queda como pregunta 14 |
| Kozusznik: fiabilidad del desempeño, fila 73 | Desempeño extra-rol autoinformado: α = .74 (p. 11). Desempeño global evaluado por el supervisor: α = .86 (p. 11) | La fila 73 es la del supervisor: **IA cumple** (0.86). El 0.74 del Excel es la escala autoinformada (fila 72) |
| Kozusznik: Park 2010 y Kahn 1990 en las hipótesis | Park [22] (meaning-making) se cita en la introducción (p. 2), en el razonamiento de la fluctuación del bienestar (p. 4) y en el de H4–H5 (p. 7). Kahn [58] se cita en el razonamiento de H3 (inversa, p. 6) y de H4–H5 (p. 7). El tramo de H1 y H2 cita solo SDT [15] | Para las filas de H1 y H2, **Park y Kahn no cuentan** ("una teoría mencionada solo de paso no cuenta"). Teoría 2/3 de la IA: **IA falla** salvo que la pregunta 8 admita teorías de otras hipótesis |
| Ayala: página de la privación relativa | "Based on the relative deprivation theory, overqualified employees…" en la p. 7 del PDF (p. 1383 de la revista); vuelve a aparecer en la discusión (p. 18) | Página confirmada: 7 |

Pregunta nueva que sale de esta verificación:

14. **`Adaptado al trabajo` cuando la consigna no nombra el trabajo pero se aplica en la jornada** (Kozusznik, escala eudaimónica): ¿"Si" o "No"?

## 9. Qué corregir primero

1. **Selección de coeficiente en estudios con muchas estimaciones** (defectos 1–3): es lo que más daña el meta-análisis. Requiere decidir las preguntas 2, 3 y 9.
2. **Corregir el Excel** donde viola la norma (sección 5), empezando por Ayala (correlación .41) y los datos inferidos (muestreo, autoinforme, método).
3. **`Adaptado al trabajo`** (defectos 5 y 6): ajustar la instrucción para que mire los ítems y la consigna, no solo si el autor dice "adaptada".
4. **Teorías 2 y 3** (pregunta 8): definir el alcance para evitar sobre-extracción.

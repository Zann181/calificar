# Plan de columnas nuevas y refuerzo de la matriz (libro de códigos v2.2 → v2.3)

Estado: **propuesta para aprobación del responsable del dominio** (Pablo Andrés Erazo Muñoz). Nada de esto está aplicado todavía en
`recursos/Libro_de_codigos_extraccion_v2.json`.

Fuentes: `MANUAL_CODIFICACION_DETALLADO.md` (v1.0, Pablo Erazo – JWOP), libro de códigos v2.2, y la matriz importada (71 filas, 47 documentos).

## 1. Resultado del cruce manual ↔ matriz

La primera propuesta hablaba de 6 columnas nuevas. Al cruzar el manual con el libro v2.2 completo, **son 5**, porque dos de las seis ya existen:

| Del manual | Ya existe como | Qué se hace |
|---|---|---|
| `Constructo_felicidad` | Col. U «Tipo de felicidad real» (19 valores cerrados + «Otro») | No se agrega. Se refuerza (sección 4). |
| `Fuente_evaluacion` | Col. AC «How measure the employee perfomance» (8 valores) | No se agrega. Se alinean los nombres (sección 4). |
| `r_final`, `N_final` | Col. AE y AB | No se agregan. |
| `Concepto_felicidad` | Col. S «Hedónica/eudaimónica» | No se agrega. |
| `Tipo_desempeno` | Col. L «Desempeño» | No se agrega. Ver conflicto C2. |
| `Instrumento_*`, `Alfa_*`, `Items_*`, `Diseño_estudio`, `Nivel_analisis` | V, O, X, P, W, R, AL, AI | No se agregan. |

Además, tres de las columnas nuevas ya viven **dentro de la trazabilidad** de cada fila (`id_muestra`, `metodo_obtencion_r`,
`conjunto_sugerido`) y no en la hoja. La propuesta es **subirlas a columnas de la hoja** para que se puedan filtrar y analizar.

## 2. Las 5 columnas nuevas (posiciones 55 a 59, a la derecha de BB)

| # | Letra | Columna | Origen |
|---|---|---|---|
| 55 | BC | `ID muestra` | Sube de `trazabilidad.id_muestra` |
| 56 | BD | `Método obtención r` | Sube de `trazabilidad.metodo_obtencion_r` |
| 57 | BE | `Constructo desempeño` | Nueva (refina la col. M, que hoy es texto libre) |
| 58 | BF | `Cultura Hofstede` | Nueva, derivada de `Pais` |
| 59 | BG | `Conjunto MA` | Sube y amplía `trazabilidad.conjunto_sugerido` |

La matriz pasa de **54 a 59 columnas**.

### 2.1 `ID muestra` (col. 55)

- **Tipo / nivel:** texto · Muestra · obligatoria.
- **Formato:** `D<Documento>-M<n>`. Ejemplo: `D28-M1`.
- **Regla:** las filas que salen de la misma muestra de personas comparten el ID. Un documento con dos muestras independientes usa `M1` y `M2`.
  Si la muestra ya apareció en otro documento, se usa el ID de la primera aparición y se anota en `advertencias_pendientes`.
- **Dónde buscar:** «Participants / Sample / Procedure». Si el artículo dice que los datos vienen de un estudio anterior, es la misma muestra.
- **Faltante:** no debe faltar. Si no se puede decidir, `D<Documento>-M1` con confianza Baja.
- **Evidencia:** sí (la frase donde el artículo describe la muestra).
- **Por qué importa:** es la variable de conglomerado del metaanálisis de tres niveles. Documentos 28 (dos muestras) y 30/31 (posible muestra repetida) lo exigen.

### 2.2 `Método obtención r` (col. 56)

- **Tipo / nivel:** categoría · Efecto · obligatoria.
- **Valores:** `Pearson observado` · `Correlación entre variables latentes CB-SEM` · `Correlación entre compuestos PLS` · `No especificado` · `No disponible`
  (se conservan los nombres del libro v2.2; el manual usa `Latente CB-SEM` y `Compuestos PLS`, son equivalentes).
- **Dónde buscar:** (1) título de la tabla de donde sale la r, (2) «Data analysis», (3) software (AMOS, Mplus, LISREL = SEM; SmartPLS, WarpPLS = PLS).
- **Regla de decisión, en este orden:**
  1. Si existe una tabla de descriptivos con correlaciones entre puntajes de escala («Means, standard deviations and intercorrelations», «Correlation matrix», alfas en la diagonal) → `Pearson observado`, **aunque el artículo pruebe sus hipótesis con SEM**.
  2. Si la única correlación viene de una tabla de constructos latentes o del modelo de medida CFA → `Correlación entre variables latentes CB-SEM`.
  3. Si viene de una tabla de constructos de un modelo PLS (Fornell-Larcker, «composite reliability») → `Correlación entre compuestos PLS`.
  4. Si el artículo no permite saberlo → `No especificado`.
  5. Si la fila no tiene correlación (solo beta o nada) → `No disponible`.
- **Faltante:** `No disponible` cuando no hay r; nunca vacía.
- **Evidencia:** sí (título de la tabla o frase de «Data analysis»).
- **Errores comunes:** confundir la diagonal (alfa) con r; tomar la r del modelo estructural cuando existe la bivariada.

### 2.3 `Constructo desempeño` (col. 57)

- **Tipo / nivel:** categoría · Efecto · obligatoria.
- **Valores (13 del manual):** `Task Performance` · `In-Role Behavior` · `Job Proficiency` · `OCB-Individual` · `OCB-Organization` · `Contextual Performance` · `Helping` · `Civic Virtue` · `Job Performance Global` · `Sales` · `Productivity` · `Innovation` · `Creativity` · y `Otro: <especificar>`.
- **Regla:** se decide por lo que miden los ítems, no por el nombre. Consistente con la col. L: In-rol ↔ Task/IRB/Proficiency; Extra-rol ↔ OCB/Contextual/Helping/Civic Virtue; General ↔ Global; Innovador ↔ Innovation/Creativity.
  Con varias subescalas, **una fila por subescala**.
- **Dónde buscar:** «Measures» (nombre y ejemplos de ítems) y encabezados de tabla.
- **Faltante:** `No indica`. No se crean valores fuera de la lista (principio P5).
- **Evidencia:** sí.
- **Validación cruzada nueva:** el par (`Desempeño`, `Constructo desempeño`) debe ser compatible (tabla en la sección 5).

### 2.4 `Cultura Hofstede` (col. 58)

- **Tipo / nivel:** categoría · Muestra · obligatoria · **derivada, sin IA**.
- **Valores:** `Individualista` (IDV > 50) · `Colectivista` (IDV ≤ 50) · `No indica`.
- **Regla:** se calcula con una tabla país → IDV guardada en el libro de códigos (no se pregunta al modelo). El país es el de la recolección de datos (col. I), no el de los autores.
  `Multinacional` o país fuera de la tabla → `No indica` y se avisa para revisión humana.
- **Evidencia:** no (se hereda de `Pais`).
- **Cobertura hoy:** ver sección 6. Con solo la tabla del manual quedan 15 filas sin IDV (Australia 7, Emiratos 2, Malasia 2, Irán, Portugal, Francia, Taiwán). Una fila dice «Gran Bretaña» y se normaliza a «Reino Unido» (regla de la col. I) antes de buscar el IDV.
- **IDV a agregar (Hofstede, pendientes de confirmar por el responsable):** Australia 90, Emiratos Árabes Unidos 25, Malasia 26, Irán 41, Portugal 27, Francia 71, Taiwán 17.

### 2.5 `Conjunto MA` (col. 59)

- **Tipo / nivel:** categoría · Efecto · obligatoria · **derivada, sin IA**.
- **Valores:** `Principal_Hedonico` · `Principal_Eudaimonico` · `Principal_Mixto` · `Sensibilidad` · `Excluir`.
- **Regla (calculada, no leída), según el número de condición del árbol de `Incluir` (motivo_decision_inclusion, 11 condiciones):**

  | Condición | Resultado de `Incluir` | `Conjunto MA` |
  |---|---|---|
  | 6 (r Pearson observado o `r_derivado`) | SI | según col. S: Hedónica → `Principal_Hedonico`; Eudaimónica → `Principal_Eudaimonico`; Hedónica y eudaimónica → `Principal_Mixto` |
  | 7 (r imputada desde beta) | SI | `Sensibilidad` |
  | 9 (solo CB-SEM latente) | SEM latente | `Sensibilidad` |
  | 5 (multinivel) | Multinivel | `Excluir` (decidido: difiere del libro) |
  | 8 (solo PLS) | PLS | `Excluir` (decidido: difiere del libro) |
  | 10 (no significativo sin valor) | No | `Excluir` (**por confirmar**: el libro dice Sensibilidad) |
  | 1, 2, 3, 4, 11 | No / Organizacional / Experimental | `Excluir` |

  Se usa la condición y no `Método obtención r`, porque la condición 6 también admite `r_derivado` (de t, F o d) sin que el método sea «Pearson observado».
- **Decisión del responsable (C4 ampliada):** se adoptan los 5 valores del manual; Narrativo → `Excluir`, y además PLS (cond. 8) y Multinivel (cond. 5) pasan de `Sensibilidad` a `Excluir`. Esto **cambia la V27** (hoy 5, 8, 9 y 10 → Sensibilidad): hay que proponerlo (sección 8).
- **Fuente de verdad:** `trazabilidad.conjunto_sugerido` (3 valores, V27) se conserva sin cambios; la col. 59 se deriva aparte del número de condición, con la tabla de arriba. Por eso la V27 no se toca.

## 3. Instrucciones para la IA (extractor)

**Como quedó construido:** el extractor solo llena la col. 57 (`Constructo desempeño`). Las 55 y 56 las refleja el programa desde `trazabilidad.id_muestra` y `trazabilidad.metodo_obtencion_r` (una sola fuente de verdad), y las 58 y 59 se calculan. Texto original del plan: las columnas 55, 56 y 57 las llena el extractor, con las reglas de arriba y el protocolo vigente (P1–P9: nada sin página y cita literal; nada con conocimiento externo; lo dudoso baja la confianza).
Las columnas 58 y 59 se calculan en código después de la extracción y las valida `validar_extraccion.py`. Instrucciones que se agregan a `prompt_para_el_extractor`:

1. «Antes de leer cualquier tabla, decide si el artículo reporta una tabla bivariada de puntajes de escala. Si existe, esa es tu fuente de r aunque el modelo final sea SEM.»
2. «Una fila por cada par felicidad–desempeño y por cada subescala de desempeño. Cada fila lleva su `ID muestra`.»
3. «No copies valores de la diagonal. Un valor mayor que 0,80 entre felicidad y desempeño se vuelve a verificar contra la tabla (puede ser un alfa).»
4. «No llenes `Cultura Hofstede` ni `Conjunto MA`; las calcula el programa.»

## 4. Refuerzos a las columnas existentes (lo que el manual aporta y el libro v2.2 no dice)

| Col. | Refuerzo propuesto |
|---|---|
| AE Correlación Feli 1 - JP | Con varios tiempos, usar la correlación del mismo tiempo (T1–T1) y anotar «se usó T1–T1». Con varias subescalas de felicidad, una fila por cada una. Un `n.s.` nunca se convierte en valor: se busca el número en otra parte o queda `No indica (no significativo)`. |
| AF Beta | Recordar que beta ≠ r: el modelo de regresión controla otras variables. Nunca pasa a la columna AE. |
| AB Muestra | Longitudinal: el N de la correlación extraída (T1–T3 usa el menor por atrición). Con N variable por datos faltantes, el N específico del par felicidad–desempeño (nota de tabla «N ranges from…»). |
| P, X Fiabilidad | Rango de plausibilidad 0,60–0,99; fuera de rango se marca para revisión, no se corrige. Con varios tiempos, el del tiempo de la correlación. Omega es válido si no hay alfa (ya lo dice el libro). |
| R, W # Ítems | Si el artículo no lo dice, `No indica`; **no** se infiere de la referencia del instrumento (principio P2). |
| S / U Felicidad | Añadir al libro las reglas del manual para casos ambiguos (ver C1 sobre Engagement). «Happiness at Work» genérico: decidir por el instrumento y por cómo lo define el artículo. |
| V Instrumento felicidad | Anexar una lista de **siglas canónicas** (SWLS, PANAS, UWES-9, UWES-17, PWB-Ryff, MSQ, JSS, JDI, PHI, PERMA, FS, WAMI) solo para **normalizar** cuando el artículo ya la usa; no para completarla. |
| O Escala desempeño | Lista de siglas canónicas: Williams-Anderson, Goodman-Svyantek, Koopmans, Podsakoff-OCB, Campbell, Janssen, Single-item, Objetivo. Misma restricción. |
| I País | Anexar la tabla IDV (sección 2.4) como referencia fija. |
| AC Fuente de evaluación | Alinear nombres: Self-report = `Self perception`; Supervisor = `Supervisor/manager`; Objetivo = `Cifras organizacionales`; Mixto = `Combinada`; Pares = `Pares`. Se conservan los nombres del libro. |
| AI Nivel / AL Study design | `Experimental` del manual = `Randomised controlled trial`; `Diary` = `Diary study`. Diario: el N es de personas, nunca de días ni observaciones. |
| AD Texto del coeficiente | Antes de copiar, comprobar que la variable es felicidad↔desempeño y no felicidad↔otra variable (compromiso, rotación…). |

## 5. Compatibilidad `Desempeño` ↔ `Constructo desempeño` (nueva validación)

| `Desempeño` (col. L) | `Constructo desempeño` admitido |
|---|---|
| In-rol | Task Performance, In-Role Behavior, Job Proficiency, Sales, Productivity |
| Extra-rol | OCB-Individual, OCB-Organization, Contextual Performance, Helping, Civic Virtue |
| General | Job Performance Global |
| Innovador | Innovation, Creativity |
| Organizacional | Otro: <especificar> |
| Contraproductivo | Otro: <especificar> |

## 6. Porcentaje que falta hoy (conjunto de test, 71 filas)

Medido sobre `datos/test/extractor.db`. **Ojo:** «llena» cuenta como llena una celda con «No indica» (294) o «No aplica» (31); solo `null` cuenta como vacía. Contando solo datos reales, hoy son 46,6 de 54 (86 %).

| Medida | Hoy (54 col.) | Con las 5 nuevas (59 col.) |
|---|---|---|
| Promedio de celdas llenas por fila | **94,8 %** (51,2 de 54) | **86,8 %** (51,2 de 59) |
| Falta en promedio | 5,2 % | 13,2 % |
| Fila menos completa | 37 de 54 (68,5 %) | 37 de 59 (62,7 %) |

Columnas que más faltan hoy (de 71 filas): Teoría 3 (60 vacías, es normal), Teoría 2 (49, normal), Covidence # (12), Ejemplo ítem desempeño (10),
Start date / End date / Exclusion criteria / Validez de las escalas (7 cada una), Teoría 1 (5), Inclusion criteria, Método de aplicación y Tipo de muestreo (5 cada una).

Qué se puede completar **sin leer los PDF**:

| Columna nueva | Filas completables sin IA | Pendientes |
|---|---|---|
| `Cultura Hofstede` | **56 de 71** (78,9 %) con la tabla del manual; **71 de 71** al agregar los 7 IDV de la sección 2.4 | 15 filas: Australia (7), Emiratos Árabes (2), Malasia (2), Irán, Portugal, Francia, Taiwán. Hace falta que confirmes los valores IDV. Una fila «Gran Bretaña» se normaliza a «Reino Unido». |
| `ID muestra` | 71 de 71 de forma provisional (`D<doc>-M1`) | Revisar documentos con varias muestras o muestra repetida (28, 30, 31 y los que salgan de la lectura). |
| `Método obtención r` | 0 de 71 | Hay que leer el PDF (53 artículos). |
| `Constructo desempeño` | 0 de 71 seguras | Se puede proponer desde la col. M, pero requiere revisión humana o lectura del PDF. |
| `Conjunto MA` | 0 de 71 hasta tener `Método obtención r` | Depende de la col. 56. |

Con solo lo derivable (y los 7 IDV agregados), cada fila llegaría a **~91 %** (53,1 de 59 en promedio, contando «No indica» como llena; la cuenta anterior de 53,6 estaba mal). Con la pasada de IA sobre los 53 PDF, a **100 %** de las columnas aplicables.

## 7. Conflictos entre el manual y el libro v2.2 (decide el responsable del dominio)

| # | Tema | Manual | Libro v2.2 | Recomendación |
|---|---|---|---|---|
| C1 | Work Engagement (UWES) | Hedónico por defecto si no es claro | «Hedónica y eudaimónica» | Mantener el libro; el manual da la excepción (si el autor lo enmarca como hedónico, Hedónica). |
| C2 | Desempeño «Objetivo» | Categoría propia (ventas, productividad) | Ventas y productividad son In-rol; la fuente se registra en AC | Mantener el libro: «Objetivo» es una fuente, no un tipo. Queda cubierto con `Constructo desempeño` = Sales / Productivity. |
| C3 | Redondeo de r | Redondear a 2 decimales (0,287 → 0,29) | P6: no redondear, transcribir con la precisión del artículo | Mantener P6. Redondear distorsiona el metaanálisis. |
| C4 | Valores de `Conjunto MA` | 5 valores | Principal / Sensibilidad / Narrativo | Adoptar los 5 del manual y mapear Narrativo → `Excluir`. **Decidido:** además PLS (cond. 8) y Multinivel (cond. 5) → `Excluir` (el libro los tenía en Sensibilidad). Cond. 10 por confirmar. |
| C5 | Tipo de felicidad vs. `Constructo_felicidad` | 12 constructos | 19 valores | Mantener los 19 (son más finos). Mapa de equivalencias en un anexo. |
| C6 | Puntajes IDV | 12 países | No existe | Completar para Australia, EAU, Malasia, Irán, Portugal, Francia y Taiwán. |

## 8. Qué se hace al aprobar (orden de trabajo) · estado al 2026-11-21

Aprobado por el responsable el 2026-11-21 (C1–C6; PLS y Multinivel → `Excluir`; condición 10 → `Excluir` y los 7 IDV por confirmar).

1. **Hecho.** Libro de códigos v2.3 (`recursos/Libro_de_codigos_extraccion_v2.json`; la v2.2 queda en `Libro_de_codigos_extraccion_v2.2_original.json`): 5 columnas con su `instruccion_operativa`, vocabularios, tabla IDV, validaciones V30–V32 propuestas y refuerzos de la sección 4.
2. **Propuesto, no aplicado** (regla de la sección 0: los scripts no se reescriben). Detalle en el ADR 0008. `escribir_matriz.py` no necesitó cambios (lee las columnas del libro; la aplicación completa `fila`). `validar_extraccion.py` sigue válido; las V30–V32 quedan por implementar.
3. **Hecho** en `datos/test` y `datos/extractor.db` (con copia `*.antes-libro-v2.3.db`): `python -m app.cli migrar-libro`. En la base de test, 71 filas con `ID muestra` provisional y `Cultura Hofstede` (71 de 71). `Método obtención r`, `Constructo desempeño` y `Conjunto MA` quedan pendientes hasta leer los PDF.
4. **Hecho.** ADR 0008.
5. **Pendiente.** Prueba con Kumar y Singh antes de cualquier pasada sobre los 53 PDF. Una extracción real cuesta dinero: se pregunta antes de lanzarla.

## 9. Extracciones en curso

Al revisar, el backend estaba apagado y no había extracciones en marcha ni en cola. No se lanza ninguna mientras esta propuesta esté pendiente.

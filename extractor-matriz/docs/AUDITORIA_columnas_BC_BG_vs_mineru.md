# Auditoría uno a uno de las columnas BC a BG contra MinerU

Fecha: 2026-11-24. Base: `datos/extractor.db` (79 filas, 39 artículos). Fuente: solo el texto que MinerU ya extrajo (`biblioteca_documentos.contenido`); ningún PDF se volvió a leer. Auditores: 13 subagentes de Claude (3 artículos cada uno). El resultado son **propuestas**: no se escribió nada en la base.

Método: cada agente revisó fila por fila las 5 columnas y dio un veredicto con cita literal y bloque. Un script comprobó que las 395 citas son subcadenas exactas del texto de MinerU (0 citas inválidas, 79 de 79 filas cubiertas).

## 1. Resultado global (79 filas x 5 columnas = 395 celdas)

| Columna | Coincide | Dudoso | Discrepa |
|---|---|---|---|
| BC `ID muestra` | 79 | 0 | 0 |
| BD `Método obtención r` | 67 | 12 | 0 |
| BE `Constructo desempeño` | 70 | 4 | 5 |
| BF `Cultura Hofstede` | 78 | 1 | 0 |
| BG `Conjunto MA` | 61 | 18 | 0 |
| Total | 355 | 35 | 5 |

- **Ninguna celda con valor es contradicha por el texto.** Las 5 «discrepa» son celdas vacías de `Constructo desempeño` con propuesta del agente.
- Revisión por código previa: `Cultura Hofstede`, `Conjunto MA`, `ID muestra` y `Método obtención r` son coherentes con su fuente (país, condición del árbol, trazabilidad). 0 inconsistencias.
- `Constructo desempeño` sigue vacío en 9 filas (71, 78, 98, 130, 133, 135, 137, 144, 145).

## 2. Dudas que pueden mover una fila entre análisis principal y exclusión

Son decisiones de criterio del responsable del dominio; el texto de MinerU admite dos lecturas.

| Grupo | Filas | Duda | Efecto si cambia |
|---|---|---|---|
| Tabla «observada» o «latente» | Bibi 4 y 5; Salas-Vallina 77; Sarfraz 132; Singh 71; Kumar 1 | La tabla se titula descriptivos o correlaciones, pero la diagonal es raíz de AVE o dice «Factor correlations» | Pearson (cond. 6) frente a latente CB-SEM (cond. 9, Sensibilidad) o PLS (cond. 8, Excluir) |
| Diseño no aleatorio | Coo 79 a 84 | Ensayo controlado con lista de espera asignada por orden de inscripción; hoy «longitudinal» (cond. 6) | Como ensayo sería cond. 4 (Experimental, Excluir) |
| Artículo contradictorio | Darvishmotevali 78 | La sección 3.3 dice regresión jerárquica y la 4.3 dice PLS | Hoy Excluir (cond. 8); con regresión sería cond. 6, Principal_Hedonico |
| Tabla ilegible o ausente | Wu 94; Magnier-Watanabe 129; Kozusznik 72 a 74 (S1 Table suplementaria); Wang 120 y 121; Ilker Met 138 | No se puede atribuir la r de la fila | Wu 94 pasaría a cond. 6; Magnier 129 de cond. 9 a 6; Kozusznik, Wang e Ilker no mueven `Conjunto MA` |
| Columna S (Hedónica/eudaimónica) | Dagenais 86 y 89 (estados negativos); Zelenski 97 (ítem único); Santoso 144; Psychological Well-Being 139; Coo 82 a 84; Soyalin 133; Boivin 90 a 92 | El texto no fija el tipo de felicidad | Cambia Principal_Hedonico / Eudaimonico / Mixto |

## 3. `Constructo desempeño` vacío: propuestas del agente

| Estudio | Artículo | Propuesta | Confianza |
|---|---|---|---|
| 71 | Singh | Helping (alternativa: OCB-Individual) | Baja |
| 78 | Darvishmotevali | Task Performance (la ronda anterior sugería Job Proficiency) | Media |
| 98 | Shanmugam | Job Performance Global | Baja |
| 130 | Chian-Fang | Job Performance Global | Media |
| 133 | Soyalin | Job Performance Global (alternativas: In-Role Behavior, Task Performance) | Baja |
| 135 | Al-shami | OCB-Organization | Media |
| 137 | Kara y Çetinel | Job Performance Global | Media |
| 144 | Santoso | Job Performance Global | Media |
| 145 | derkinderen | Job Performance Global; vacío también es defendible (revisión sin medida propia) | Baja |

**Aplicado el 2026-11-24:** las cinco de confianza Media (estudios 78, 130, 135, 137 y 144) se escribieron por la API de la app, con autor, motivo, bloque y cita en el historial de cada celda (`CORREGIDA`, «pendiente de verificación humana»). Copia previa de la base: `datos/extractor.antes-constructo-media-20261124.db`. Siguen vacías las 4 de confianza Baja (71, 98, 133 y 145). Con esto `Constructo desempeño` queda lleno en 75 de 79 filas.

Dudoso en una fila con valor: Ilker Met 138 (`Sales`, media); Job Performance Global o Productivity también serían razonables.

## 4. Otras dudas

- `Cultura Hofstede` Chian-Fang 130: el texto no nombra el país de recolección (solo Taipei y aerolíneas); Taiwán da Colectivista, la lectura estricta daría `No indica`. Ilker Met y Shanmugam: el país se infiere (Estambul / Coimbatore), no se declara literalmente.
- Trazabilidad: Oswald 141 y 142 registraban la condición 4 y la 11, pero la correcta es la 2 (sin coeficiente felicidad–productividad). Aplicado, ver sección 7. **Corrección:** en la primera versión de este informe señalé como inconsistencia que en Kumar, Li, Cao y Peiró `conjunto_sugerido` dice «Sensibilidad» mientras `Conjunto MA` da `Excluir`. No lo es: `conjunto_sugerido` es otro campo (V27, tres valores) y el libro manda PLS y Multinivel a «Sensibilidad»; solo `Conjunto MA` (cinco valores) los manda a `Excluir` (ADR 0008).
- Taris: la Tabla 1 vino desordenada y se reconstruyó por posición; en las filas 110 y 114 el signo de la r es ambiguo (costo alto = peor desempeño).
- Salgado: los rótulos de la Tabla 2 están desfasados; los valores .15, .19 y .21 están en JP11.

## 5. Filas que faltan en la matriz (señaladas por los agentes)

Lista para decidir cuáles reextraer (no se corrió ninguna extracción; cada una cuesta unos 2,6 USD y 4 minutos por artículo). Todos los datos salen del texto de MinerU.

| Artículo | Fila que falta | Dato | Dónde |
|---|---|---|---|
| Kumar 2022 (Doc. 1) | Satisfacción laboral → desempeño (H1) | Hipótesis H1 del modelo; la matriz solo tiene SWB → JP | Hipótesis H1 (bloque p02-b07); el coeficiente no se extrajo en esta auditoría |
| Santoso (Doc. 50) | Felicidad × desempeño evaluado por el supervisor | r = 0.478** (la matriz solo tiene el autoinforme) | Tabla 2 |
| Awada 2020 (Doc. 33) | PS (performance appraisal) | r = 0.656, beta 0.221 (H1); hay 6 de 7 hipótesis | Tablas de resultados |
| Al-shami (Doc. 42) | HAW → IWB | beta 0.213 | Tabla 5 |
| Dagenais-Desmarais 2017 (Doc. 9) | Bienestar psicológico en el trabajo × desempeño contextual | r = .30** (fila 1 de la tabla; el agente la lee como eudaimónica) | Tabla 1 |
| Taris (Doc. 26) | Satisfacción × Efficiency y × Client satisfaction | r = .07 y r = .49 | Tabla 1 (desordenada en MinerU) |
| Magnier-Watanabe 2020 (Doc. 36) | Muestra de Francia (D36-M2) | N = 273; SWB → JP no significativo | Resultados |
| Oswald 2015 (Doc. 48) | Experimento 1 (D48-M1, N = 276) | No verificado si trae un coeficiente felicidad–productividad | Experimento 1 |

## 6. Columna S (`Hedónica/eudaimónica`) en las 12 filas dudosas

En el libro, S se deriva de `Tipo de felicidad real` con una tabla de correspondencia (V25, advertencia). Contra esa tabla:

- **Ya correctas (9):** Dagenais 86 (agotamiento, signo invertido → Hedónica) y 89 (afecto negativo, signo invertido → Hedónica); Psychological Well-Being 139 (bienestar psicológico en el trabajo → Eudaimónica); Coo 82 a 84 (engagement laboral → mixta); Boivin 90 a 92 (bienestar psicológico en el trabajo → Eudaimónica). Las dudas de los agentes sobre estas filas las resuelve el libro.
- **Contradice la tabla (1):** Santoso 144 tenía Tipo «Bienestar subjetivo compuesto» (→ Hedónica) y S mixta. Resuelto, sección 7.
- **Tipo «Otro», a criterio (2):** Zelenski 97 (calidad de vida laboral, ítem único, hoy Hedónica) y Soyalin 133 (felicidad en el lugar de trabajo, hoy mixta). El responsable pidió cambiar Zelenski 97: pasó a «Hedónica y eudaimónica» (sección 7). Soyalin 133 se mantiene.

## 7. Decisiones del responsable aplicadas (2026-11-24)

| Qué | Cambio | Efecto |
|---|---|---|
| Coo 79 a 84 | Se mantiene longitudinal (cond. 6) | Ninguno |
| Darvishmotevali 78 | Se mantiene PLS (cond. 8) | Ninguno |
| Tablas ilegibles (Wu 94, Magnier 129, Kozusznik 72 a 74, Wang 120 y 121, Ilker 138) | Quedan como están; se revisa el PDF después | Ninguno |
| Observada o latente (Bibi 4 y 5, Sarfraz 132, Singh 71, Kumar 1, Salas-Vallina 77) | Caso por caso; pendiente de revisar cada tabla en el PDF | Ninguno por ahora |
| Santoso 144 | `Tipo de felicidad real`: «Bienestar subjetivo compuesto» → «Índice compuesto (PHI, OHQ)» (por la API, con cita p03-b04) | S ya era mixta y ahora coincide con la tabla; `Conjunto MA` sigue `Principal_Mixto` |
| Oswald 141 | `Incluir en meta análisi`: Experimental → No (por la API); condición 4 → 2 en la trazabilidad | `Conjunto MA` sigue `Excluir`; `conjunto_sugerido` sigue «Narrativo» |
| Oswald 142 | Condición 11 → 2 en la trazabilidad (escritura directa, con copia previa) | Ninguno en valores |
| Zelenski 97 | `Hedónica/eudaimónica`: Hedónica → Hedónica y eudaimónica (caso de uso `RevisarCelda`, con cita p08-b04) y `migrar-libro` para recalcular lo derivado | `Conjunto MA` de la fila 97: `Principal_Hedonico` → `Principal_Mixto`; ninguna otra celda derivada cambió |
| País de Chian-Fang 130, Ilker Met 138 y Shanmugam 98 | Sin cambio de valor; el responsable aprobó una regla general por afiliación (ADR 0010): el libro se editó y se publicó como versión activa | Ninguno en los datos; rige para las extracciones nuevas |

Copias previas de la base: `datos/extractor.antes-constructo-media-20261124.db`, `datos/extractor.antes-santoso-oswald-20261124.db` y `datos/extractor.antes-zelenski97-20261124.db`.

Hallazgo de la app: la API de celdas no puede direccionar la columna `Hedónica/eudaimónica` (la barra parte la ruta y el servidor responde 404, también con `%2F`, que es lo que envía la interfaz). Por eso el cambio de Zelenski 97 se hizo con el mismo caso de uso, sin pasar por HTTP. Tampoco `corregir` recalcula las columnas derivadas: después de corregir S hay que correr `migrar-libro` para que `Conjunto MA` se actualice. Ambas cosas quedan como observación para el responsable; no se tocó código.

## 8. Limitaciones

- Solo se verificó contra el texto de MinerU: figuras (Oswald, Peiró, Singh, Ilker Met) y material suplementario (Kozusznik S1) no están, y varias tablas llegaron desordenadas.
- Los veredictos son de agentes de IA con cita literal comprobada por código; las decisiones de la sección 2 requieren criterio humano.

# ADR 0001 · Sistema de coordenadas de MinerU y fórmula de conversión

- Estado: **Propuesto, pendiente de firma del responsable del dominio**
- Fecha: 2026-10-05
- MinerU 3.4.5, backend `pipeline`, método `auto` (Kumar y Singh se clasifican como `txt`: tienen capa de texto)
- Evidencia: `docs/decisiones/0001/` (imágenes, `bloques.md`, `verificacion.csv`, `tiempos.csv`)

## Pregunta

¿En qué sistema entrega MinerU los rectángulos de cada bloque, y cómo se convierten a puntos PDF con origen arriba a
la izquierda (el sistema de PDF.js y PyMuPDF) para resaltar la cita en el visor?

## Hallazgo

MinerU entrega dos sistemas distintos:

| Archivo | Sistema | Ejemplo (Kumar, página 1) |
| --- | --- | --- |
| `content_list.json` | Escala 0 a 1000 relativa a la página, origen arriba a la izquierda | `bbox [67, 98, 917, 152]` |
| `middle.json` | Puntos PDF, origen arriba a la izquierda | `page_size [595, 841]` |

`page_size` viene redondeado al punto entero. El PDF real mide 595,32 × 841,92 pt (Kumar) y 439,37 × 666,14 pt (Singh).
Usar el valor redondeado introduce un error menor de 1 pt.

## Decisión

```
x_pt = bbox_x / 1000 × ancho_pt
y_pt = bbox_y / 1000 × alto_pt
(ancho_pt, alto_pt) = middle.json pdf_info[i].page_size
origen arriba a la izquierda; pagina = page_idx + 1
```

Es la fórmula que ya aplica `MineruHttp.normalizar`. En el visor:
`escala = viewport.width / pagina.ancho_pt; x_px = x_pt × escala` (sección 9.4).

## Comprobación

1. **Visual (criterio de aceptación de F0).** Se dibujaron 20 rectángulos, 10 de Kumar y 10 de Singh, de tipos
   título, párrafo, tabla, figura, nota y encabezado, en 13 páginas distintas. Resultados en
   `docs/decisiones/0001/*.png` y el índice en `bloques.md`. **Los 20 caen sobre su contenido.**
2. **Automática, todos los bloques** (`herramientas/f0_verificar_rectangulos.py` → `verificacion.csv`). Para cada uno
   de los 213 bloques de texto se comparó el texto de MinerU con el texto que el PDF tiene dentro del rectángulo:
   - de los 213 bloques, 16 no tienen texto en MinerU (hallazgo H1) y 197 sí lo tienen. De esos 197, 187 dan
     similitud de 90 % o más, con una media de 99,7 %;
   - con el mismo rectángulo desplazado 40 pt hacia abajo, la similitud cae a 40 %. Eso confirma que la prueba
     discrimina: si la fórmula estuviera mal, el recorte traería otro texto;
   - 10 bloques salen marcados REVISAR, y ninguno se debe a la fórmula. Ocho son el logotipo "JEEF" de Kumar (es una
     imagen sin capa de texto), uno es "Published online" de Singh (sin capa de texto) y uno es Singh p12-b03, con
     74 % por el LaTeX del hallazgo H3.

**Conclusión: la fórmula es correcta.**

## Hallazgos que afectan al anclaje (M5) y deben resolverse en F2

| # | Hallazgo | Magnitud | Propuesta |
| --- | --- | --- | --- |
| H1 | **Párrafos que cruzan página.** MinerU une el párrafo que continúa en la página siguiente, mueve todo el texto al bloque de la página anterior y deja vacío el bloque de la página nueva (`lines_deleted`, `cross_page` en `middle.json`). Una cita de la página 5 quedaría anclada a un bloque de la página 4. | Kumar 7 y Singh 9 bloques vacíos (de 85 y 128) | En PDF con capa de texto, el texto de un bloque vacío se toma de la capa del PDF dentro de su rectángulo. Lo aplica `f0_extraccion.py` y funciona. Llevarlo a `normalizar()`. |
| H2 | **Párrafos que cruzan columna** en la misma página: el bloque de la columna izquierda incluye líneas de la derecha, pero su rectángulo no las cubre. | Kumar 4 bloques | El rango resaltado se calcula con las líneas de `middle.json`, no solo con el rectángulo del bloque. |
| H3 | **Números convertidos en LaTeX.** El detector de fórmulas convierte texto como `(b = 0.510, p < 0.001)` en `$( \mathrm { b } { = } 0 . 5 1 0 ,$`. Las citas de β y r no coincidirían. | Singh: varios bloques de resultados | En PDF con capa de texto, el texto de un bloque con `$` se toma de la capa del PDF. Opción alternativa: desactivar la detección de fórmulas en línea en `mineru.json` y medir el efecto. |
| H4 | **Validador en Windows.** `pdftotext` (xpdf 4.00) escribe Latin-1 y Python decodifica con cp1252. "–" y "−" se pierden, y V23 rechaza citas correctas: 3 errores en el ejemplo verificado de Kumar y 1 en el piloto de Singh. | Ambos ejemplos verificados | `herramientas/validar_utf8.py` ejecuta el validador **sin modificarlo**, forzando `-enc UTF-8`. Con eso, ambos ejemplos dan 0 errores. El adaptador del validador debe hacer lo mismo. |
| H5 | **`bloque_id` no cabe en el esquema.** La sección 8.2 pide `bloque_id` en cada evidencia, pero `esquema_de_salida` declara `additionalProperties: false`. | Toda extracción | **Decidido el 2026-10-05 por el responsable del dominio: libro v2.2.** Cada evidencia admite `bloque_id` (patrón `pNN-bMM`), opcional en el esquema para que las filas heredadas sigan validando y obligatorio para el programa en extracciones nuevas. La versión 2.1 queda en `recursos/Libro_de_codigos_extraccion_v2.1_original.json`. |
| H6 | El encabezado de revista de Kumar en la página 4 sale como `text`, no como `header`. | 1 bloque | Sin acción: no afecta coordenadas. |
| H7 | **El texto de MinerU y el del validador no coinciden.** MinerU pierde ligaduras ("efective" por "eﬀective") y espacios finos ("N=219" por "N = 219"). `pdftotext`, que usa V23, no ve el texto sin capa ("Published online") y mezcla columnas o páginas en frases largas. El modelo cita bien lo que lee, pero V23 lo rechaza. | Primera iteración: Kumar 1 o 2 errores, Singh 3 o 4. Se corrigen en la segunda iteración cambiando la cita, sin inventar | Una sola fuente de verdad: el anclaje (M5) y V23 deberían comparar contra el mismo texto. Se propone pasarle al validador el texto del documento estructurado; requiere aprobar un cambio en `validar_extraccion.py` (regla 2 de la especificación). |
| H8 | **Tablas mal separadas.** En Singh, MinerU pone valores de la Tabla 4 (imagen en la p. 9) dentro del bloque de la Tabla 3 (p. 8). El extractor lo detectó y lo anotó. | Singh, 1 tabla | El auditor y la revisión humana lo cubren. Medir la frecuencia en los 5 pilotos de F2. |
| H9 | **Escapes de Markdown.** MinerU escribe `\*\* p<.001` y `cr\_fdh` en tablas y notas. | Todas las notas con asteriscos | Quitar los escapes al normalizar. Ya lo hace `f0_extraccion.py`. |
| H10 | **El conciliador no recibe la regla correcta en los campos estructurales.** Para el número de filas recibe `trazabilidad_por_fila`, no `regla_para_abrir_una_fila_nueva`, y por eso responde PENDIENTE. | 1 caso en Kumar | En M4, asociar cada campo de trazabilidad con su sección del libro. |

## Tiempos de conversión (CPU)

Equipo: Intel Core i5-1240P (12 núcleos), **7,7 GB de RAM**, sin GPU. MinerU recomienda 16 GB.

| Archivo | Páginas | Medición 2026-09-30 | Medición 2026-10-05 |
| --- | --- | --- | --- |
| Kumar 2022 | 8 | 41,4 s/página | 21,2 s/página |
| Singh 2023 | 18 | 317,1 s/página | 11,2 s/página |

Interpretación:

- La salida de 2026-10-05 es **idéntica** a la de 2026-09-30 (`content_list.json` igual en ambos artículos). La
  conversión es determinista y los fixtures siguen siendo válidos.
- Los 317 s/página de la primera medición de Singh fueron una anomalía del equipo, no un problema de MinerU ni del
  OCR: ambos PDF se clasifican como `txt`. La causa probable es falta de memoria con intercambio a disco, o la
  suspensión del equipo. Durante la conversión quedan unos 580 MB de RAM libres.
- En la medición nueva, Kumar se convirtió primero e incluye la carga de los modelos. Por eso Singh resulta más rápido
  por página.
- Estimación para la biblioteca: 53 PDF únicos y 862 páginas. A entre 11 y 21 s por página, la conversión toma de
  **2,6 a 5 horas** en CPU, con una conversión a la vez y el equipo sin otro uso. Se recomienda convertir de noche y
  no subir la concurrencia de MinerU con 7,7 GB de RAM.

## Firma

Revisé las 20 imágenes de `docs/decisiones/0001/` y los rectángulos caen sobre su texto.

- Nombre: ______________________ Fecha: __________
- H5: decidido el 2026-10-05 (libro v2.2).

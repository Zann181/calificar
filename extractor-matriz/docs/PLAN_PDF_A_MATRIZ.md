# Plan: de «añadir un PDF» a matriz llena con el porqué de cada dato

Fecha: 2026-10-06. Basado en lectura del código; no se corrió ninguna extracción (cuesta ~2,6 USD por artículo).

## Estado al 2026-10-07

Hecho desde este plan: despachador dentro del servidor (convierte PDF nuevos solo, con barrido cada 15 s), arranque de
MinerU en el lanzador, cabecera con el estado de servidor, despachador, MinerU y Claude, panel de registro en vivo,
**lanzar extracciones desde la interfaz con avance en porcentaje** (`POST /extracciones`, `GET /extracciones/avance`,
cola en el proceso con una extracción a la vez) y la primera corrida real (Bibi 2022, ver `COMPARACION_BIBI_2022.md`).
Falta: Fase 4 (cobertura del «porqué»), aceptación de F2 con 5 pilotos y la decisión sobre la condición 9 de «Incluir».

## 1. Cómo debería funcionar (objetivo)

```
Añadir PDF ─► rechazo de duplicado (SHA-256) ─► MinerU (bloques + coordenadas) ─► texto etiquetado [pNN-bMM]
   ─► Extractor (54 columnas, cada una con evidencia o inferencia) ─► Validador (≤3 reintentos)
   ─► Anclaje (cita → bloque → rectángulo) ─► Auditor + Codificador ciego (en paralelo)
   ─► Conciliador ─► filas en la matriz (POR_REVISAR) ─► revisión humana en el visor ─► Excel
```

Por cada celda, el sistema ya guarda: **dónde** (página, bloque, rectángulo, cita literal, nivel de ancla),
**qué tipo de dato es** (LITERAL / CODIFICADO / INFERIDO / FALTANTE) y **por qué** (regla y razonamiento si es inferido;
guía de la columna del libro; confianza, discrepancias y advertencias de la fila). El panel «Por qué este valor»
(`PanelRazonamiento.tsx`) junta esas tres fuentes bajo el PDF.

## 2. Qué existe y funciona (verificado en el código)

| Pieza | Estado |
| --- | --- |
| Carga con deduplicación, estados, MinerU, documento estructurado | Hecho (F1) |
| Motor de extracción de 4 roles, validador, anclaje, conciliación, acuerdo con el ciego | Hecho (F2), con pruebas doradas Kumar/Singh |
| Escritura de filas en Matriz, revisión (aprobar/corregir/rechazar), exportación a Excel | Hecho |
| Grilla, visor PDF con resaltado, ficha de evidencia, panel de razonamiento | Hecho (parte sin commitear) |

## 3. Qué falta para que «solo añadir un PDF» baste

1. **No hay forma de lanzar la extracción desde la app.** Solo existe `python -m app.cli extraer <id> --documento N`
   (síncrono, ~4 min). No hay `POST /extracciones`; el botón «Extraer seleccionados» muestra «La cola llega en F3».
   El contexto `orquestacion/` está vacío (sin `Trabajo`, sin cola, sin progreso).
2. **La conversión y la escritura en la matriz dependen del despachador de la outbox**, y `main.py` no lo arranca.
   Al subir un PDF desde la interfaz el artículo queda en `NUEVO`; hay que correr `cli convertir-pendientes` /
   `cli despachar` a mano. Lo mismo con `ExtraccionCompletada` → filas en Matriz.
3. **MinerU es un servicio aparte (puerto 8001)** y `Extractor.ps1` no lo arranca. Sin él, ningún PDF nuevo se convierte.
4. **Datos que hoy escribe una persona:** `--documento` (obligatorio), `--covidence`, `--via`. Para «solo añadir PDF»
   el Documento debe asignarse solo (siguiente libre), y Covidence/vía quedar opcionales editables después.
   El Estudio ya es automático.
5. **La extracción real nunca se ha corrido dentro de la app.** `extraccion_extracciones` tiene 0 filas; Kumar y Singh
   salen de `demo_interfaz.py` con las salidas guardadas de F0. La aceptación de F2 (≥95 % de citas verificadas en
   5 artículos piloto) está pendiente y el ADR 0004 sigue «Propuesto».
6. **Cobertura del «porqué» sin medir.** Falta una comprobación automática de que toda columna con
   `requiere_evidencia` y valor distinto de faltante trae evidencia anclada, y que todo INFERIDO trae regla y
   razonamiento. Hoy el resaltado es el rectángulo del bloque, no las palabras exactas (H2 del ADR 0004).
7. **Sin progreso ni errores visibles:** un fallo (CLI sin sesión, validador con errores, MinerU caído) solo aparece en logs.
8. Pendientes de decisión del responsable del dominio: licencia AGPL de PyMuPDF si se publica en red; cambio del
   validador (H7); filas que el conciliador no puede abrir ni cerrar (queda hallazgo PENDIENTE).

## 4. Plan de implementación

Regla: no correr extracciones reales sin autorización explícita de costo (CLAUDE.md del proyecto).

### Fase 0 · Preparar el entorno (sin gasto)
- Confirmar `claude.exe` con sesión iniciada y fijar `CLAUDE_CLI=C:\Users\maleg\.local\bin\claude.exe` en `backend/.env`.
- Comprobar `pdftotext` y el entorno de `servicio-mineru`; arrancar MinerU y convertir un PDF de prueba.
- Correr `ruff`, `mypy`, `lint-imports`, `pytest -q` y dejar todo en verde.
- Commitear los cambios pendientes del front (`PanelRazonamiento`, `Divisor`, `Grilla`, `VisorPdf`, catálogo).
- **Hecho cuando:** MinerU responde en `/salud` y la suite pasa.

### Fase 1 · Primera corrida real controlada (pide autorización: ~2,6 USD)
- Elegir 1 artículo que no sea Kumar ni Singh. `cargar` → `convertir-pendientes` → `extraer --documento N`.
- Registrar: errores del validador, % de citas por nivel, acuerdo con el ciego, hallazgos, tokens y minutos.
- **Hecho cuando:** extracción COMPLETADA, filas en POR_REVISAR y cada celda abre su cita en el visor.

### Fase 2 · Automatizar el flujo en el backend
1. `Trabajo` mínimo en `orquestacion/` (tipo CONVERTIR/EXTRAER, estado, paso, progreso, error), tabla + migración Alembic.
2. Ejecutor en hilos dentro del propio proceso (sin Redis; ADR 0003): cola con `CONCURRENCIA_EXTRACCION`, cancelar y reintentar.
3. Arrancar el despachador en el `lifespan` de FastAPI, para que carga → conversión y completada → filas ocurran solos.
4. `POST /extracciones {articulos:[id], confirmar_reextraccion}`, `GET /trabajos`, `POST /trabajos/{id}/cancelar|reintentar`.
5. Encadenar: al terminar la conversión de un artículo marcado «extraer al cargar», encolar la extracción.
6. Documento automático (siguiente libre; editable después); Covidence y vía opcionales.
7. Lanzador: que `Extractor.ps1` arranque MinerU junto al servidor y lo apague al cerrar.
- **Hecho cuando:** una prueba de integración con `ModeloGrabado` y `ConversorFijo` sube un PDF por la API y termina con filas en la matriz sin llamadas manuales; 10 artículos simulados terminan con estados correctos.

### Fase 3 · Interfaz
- Quitar el aviso «llega en F3»; el diálogo llama a `POST /extracciones`.
- Estado por artículo con paso y porcentaje (consulta periódica a `/trabajos`; WebSocket después), errores legibles con botón Reintentar.
- Opción «Extraer al cargar» en «Añadir PDF».
- **Hecho cuando:** arrastrar un PDF lleva a la fila nueva en la grilla sin salir de la interfaz.

### Fase 4 · Cerrar el «porqué»
- Prueba automática de cobertura: toda columna con `requiere_evidencia` trae evidencia con ancla; todo INFERIDO trae regla y razonamiento; informe de excepciones por artículo.
- Si el validador no lo exige, proponer al responsable del dominio la regla (no se edita `validar_extraccion.py`).
- Visor: resaltar las palabras citadas con las líneas de `middle.json` (H2), no solo el bloque.
- Panel: mostrar siempre las tres fuentes (guía del libro, evidencia/razonamiento, contexto de la fila) y marcar claramente celdas sin evidencia.
- **Hecho cuando:** en los pilotos, ninguna celda con dato queda sin dónde ni por qué, salvo las marcadas como FALTANTE.

### Fase 5 · Aceptación de F2 y lote
- 5 artículos piloto elegidos por el responsable del dominio (~13 USD, ~20 min): meta ≥95 % de citas verificadas y 0 errores del validador.
- Aprobar o ajustar el ADR 0004; actualizar README y CLAUDE.md.
- Lote de los 48 PDF (~125 USD, ~3 h con concurrencia 2): con tope de gasto (`TOPE_TOKENS_MENSUAL`) y revisión de los de acuerdo < 0,80 primero.

## 5. Cómo correrlo hoy (manual, mientras se construye la Fase 2)

```bash
cd extractor-matriz/backend
.venv/Scripts/python -m app.cli cargar-carpeta <carpeta_con_el_pdf>
.venv/Scripts/python -m app.cli convertir-pendientes        # requiere servicio-mineru en :8001
.venv/Scripts/python -m app.cli extraer <articulo_id> --documento <N>   # ~4 min, ~2,6 USD
.venv/Scripts/python -m app.cli exportar ../datos/exportada.xlsx
```

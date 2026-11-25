# ADR 0010 · País por afiliación cuando el artículo no declara dónde se recolectaron los datos

- Estado: **Aprobado** por el responsable del dominio (Pablo Andrés Erazo Muñoz) el 2026-11-24, al revisar la auditoría de las columnas BC a BG. El libro v2.3 se editó y se publicó en la app ese mismo día (nueva versión activa; copia previa en `datos/extractor.antes-adr0010-20261124.db`).
- Fecha: 2026-11-24
- Se aparta de: `Pais`, `regla_de_decision` («País donde se recolectaron los datos, no el de afiliación de los autores») y `tratamiento_del_dato_faltante` («No indica si el artículo no lo informa»); y de `Cultura Hofstede`, `reglas_de_codificacion` («El país es el de la recolección de datos, no el de los autores»).
- Origen: `docs/AUDITORIA_columnas_BC_BG_vs_mineru.md`, secciones 2 y 4.

## Contexto

En tres filas el artículo no nombra el país de recolección y el extractor lo dedujo de la afiliación, dejando la inferencia anotada: Shanmugam 98 (Coimbatore, India), Chian-Fang 130 (Taipei, Taiwán) e Ilker Met 138 (Estambul, Turquía). Con la regla vigente la lectura estricta daría `No indica` y `Cultura Hofstede` = `No indica`; con la regla propuesta quedan como están. `Cultura Hofstede` se calcula desde `Pais`, así que cualquier cambio de país cambia el IDV.

## Decisión propuesta

Cuando el artículo no declare el país de recolección de datos, `Pais` toma el país de la afiliación de los autores (institución donde se hizo el estudio), y se anota en `trazabilidad.inferencias` que el país es inferido. Si el artículo sí lo declara, manda lo declarado. Multinacional y país fuera de la tabla IDV siguen dando `No indica` en `Cultura Hofstede`.

Texto propuesto para el libro:

- `Pais.instruccion_operativa.regla_de_decision`: «País donde se recolectaron los datos. Si el artículo no lo declara, el país de la afiliación de los autores, anotado en `inferencias`. Efectos separados por país abren filas.»
- `Cultura Hofstede.reglas_de_codificacion`: «El país es el de la recolección de datos (columna I); si no se declara, el de la afiliación (ADR 0010).»

## Consecuencias

- Filas 98, 130 y 138: sin cambio de valor; se documenta la regla que ya seguía el extractor.
- Un riesgo: la afiliación puede no coincidir con el lugar de recolección (autores en un país que estudian otro). Por eso debe quedar siempre marcada como inferencia, y el prompt del extractor debe decirlo.
- La fila 145 (derkinderen, revisión sistemática) no recolecta datos: se mantiene `No indica`. **Por confirmar.**
- Aplicación: se cambiaron en el libro `Pais.como_se_extrae`, `Pais.instruccion_operativa.regla_de_decision`, `Pais.tratamiento_del_dato_faltante` y `Cultura Hofstede.reglas_de_codificacion`, y se agregó la nota en `metadatos.cambios_respecto_a_version_2.2`. El extractor lee las instrucciones de cada columna del libro, así que no hizo falta tocar código ni el prompt general. Las 79 filas ya figuraban como desactualizadas por la publicación del 22 de noviembre; no cambió ningún valor de la matriz. Los artículos que se extraigan desde ahora usan la regla nueva.

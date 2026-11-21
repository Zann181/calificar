# ADR 0008 · Libro de códigos v2.3: cinco columnas nuevas

- Estado: **Aprobado por el responsable del dominio** (Pablo Andrés Erazo Muñoz) el 2026-11-21, con tres puntos por confirmar (abajo).
- Fecha: 2026-11-21
- Se aparta de: sección 0 («54 columnas»), `esquema_de_salida` del libro v2.2 y la V27 (conjunto sugerido de tres valores) solo en lo que dice abajo.
- Origen: `docs/PLAN_COLUMNAS_NUEVAS.md` (cruce del manual de codificación v1.0 con el libro v2.2).

## Contexto

El manual de codificación pide variables que el libro v2.2 no tiene como columnas de la hoja. Tres ya vivían en
`trazabilidad` (`id_muestra`, `metodo_obtencion_r`, `conjunto_sugerido`). La matriz pasa de 54 a 59 columnas, a la
derecha de BB.

## Decisión

| Col. | Letra | Columna | Quién la escribe |
|---|---|---|---|
| 55 | BC | `ID muestra` | El programa: refleja `trazabilidad.id_muestra`. En filas heredadas, `D<Documento>-M1` provisional. |
| 56 | BD | `Método obtención r` | El programa: refleja `trazabilidad.metodo_obtencion_r`. Sin dato en las heredadas. |
| 57 | BE | `Constructo desempeño` | **El extractor**, en `fila`. Lista cerrada de 13 valores + `Otro: …`. |
| 58 | BF | `Cultura Hofstede` | El programa: tabla país → IDV del libro; IDV > 50 Individualista. |
| 59 | BG | `Conjunto MA` | El programa: según el número de condición del árbol de `Incluir`. |

- **El libro es la norma.** Cada columna tiene su `instruccion_operativa`; las derivadas llevan además `derivada`, que dice
  cómo se calculan (`trazabilidad`, `tabla`, `por_condicion`). El código solo interpreta esa especificación
  (`matriz/dominio/derivadas.py`); la tabla IDV y la tabla de condiciones viven en el libro, no en el código.
- **Una sola fuente de verdad.** Las columnas 55 y 56 reflejan la trazabilidad; no se le pide al extractor escribirlas dos veces.
  Esto se aparta del plan original (que decía que el extractor llenaba 55, 56 y 57).
- **`Conjunto MA`** (5 valores): condición 6 → `Principal_*` según `Hedónica/eudaimónica`; condiciones 7 y 9 → `Sensibilidad`;
  1–5, 8, 10 y 11 → `Excluir`. Multinivel (5) y PLS (8) pasan de Sensibilidad (libro v2.2) a Excluir: **decisión del responsable**.
  `trazabilidad.conjunto_sugerido` y la V27 no cambian.
- **Aplicación.** `ImportarMatriz` calcula las derivadas (provisionales) al importar; `EscribirFilasDeExtraccion` las calcula al
  escribir una extracción; `AgregarColumnasDelLibro` (`python -m app.cli migrar-libro`) las agrega a filas ya guardadas
  (idempotente, sin modelo ni PDF). La exportación completa `fila` con las celdas guardadas, porque `escribir_matriz.py` lee
  todas las columnas del libro, y pone encabezado a las columnas nuevas.
- El Excel importado (54 columnas) sigue siendo válido: sus encabezados nuevos pueden venir vacíos (`agregada_en_version`).

## Por confirmar (responsable del dominio)

1. **Condición 10** (efecto no significativo sin valor): quedó en `Excluir`; el libro v2.2 la tenía en `Sensibilidad`.
2. **Los 7 IDV** (Australia 90, Emiratos Árabes Unidos 25, Malasia 26, Irán 41, Portugal 27, Francia 71, Taiwán 17) y el resto de
   la tabla (19 países) son los valores publicados de Hofstede según el asistente; no se contrastaron con el manual, que no
   está en el repositorio. España (51) queda `Individualista` por un punto: conviene confirmarlo (afecta 13 filas).
3. **`Constructo desempeño` sin evidencia obligatoria** por ahora (ver abajo).

## Propuestas al responsable (no se aplican: sección 0)

`recursos/validar_extraccion.py` y `recursos/escribir_matriz.py` **no se modificaron**. El primero sigue válido con el libro v2.3
(el esquema acepta `Constructo desempeño` como propiedad opcional). Quedan por implementar en el validador:

- **V30** (error): `Desempeño` y `Constructo desempeño` compatibles según `vocabularios_controlados`.
- **V31** (advertencia): r felicidad–desempeño > 0.80 en valor absoluto, verificar contra la tabla.
- **V32** (error): la hoja refleja la trazabilidad (columnas 55 y 56).
- Hacer `Constructo desempeño` **obligatorio** en el esquema y con `requiere_evidencia = true`. Hoy no se puede: V13 lee `fila[k]`
  de toda columna con evidencia y las grabaciones doradas (Kumar, Singh) no traen la columna. Se hace al re-grabar esos fixtures
  en la prueba del paso 5 del plan.
- Retirar a futuro `trazabilidad.conjunto_sugerido` y la V27 si el responsable prefiere un solo conjunto de valores.

## Consecuencias

- 59 columnas en la grilla, la API y la exportación; pruebas actualizadas (260 pasan) y nuevas: `test_derivadas.py` y la migración.
- Migración aplicada el 2026-11-21 a `datos/test/extractor.db` (71 filas heredadas: `ID muestra` y `Cultura Hofstede` calculados, 71 de 71;
  las otras tres, pendientes de leer los PDF) y a `datos/extractor.db` (79 filas extraídas: las cuatro derivadas calculadas
  desde su trazabilidad). Copias previas: `datos/*.antes-libro-v2.3.db`.
- Las filas extraídas con el libro v2.2 no traen `Constructo desempeño` (queda pendiente hasta una reextracción).
- **No se lanzó ninguna extracción.** El paso siguiente es la prueba con Kumar y Singh (cuesta dinero: se pregunta antes).

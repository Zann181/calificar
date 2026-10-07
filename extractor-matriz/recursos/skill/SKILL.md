---
name: "extractor-matriz-felicidad-desempeno"
description: "Extrae de un artículo en PDF los datos de la matriz de síntesis felicidad y desempeño, sin inventar, con página y cita de cada dato, auditoría de agentes y escritura en el Excel."
---

# Extractor auditado para la matriz de síntesis (felicidad en el trabajo y desempeño laboral)

Objetivo: a partir de un artículo, llenar las filas de la matriz de 54 columnas de forma sustentada. Cada dato dice de dónde salió (página del PDF, ubicación y cita literal). Ningún dato se inventa. Dos agentes independientes auditan la extracción antes de escribir en el Excel, y lo aprendido retroalimenta el libro de códigos.

La norma no está en este archivo sino en el libro de códigos. Esta skill solo organiza el trabajo.

## Insumos

1. **Libro de códigos**: `claude/Libro_de_codigos_extraccion_v2.json` del proyecto (Projects, `project_read`). Solo son normativas estas secciones: protocolo_de_extraccion, vocabularios_controlados, columnas[*].instruccion_operativa, trazabilidad_por_fila, validaciones_automaticas y esquema_de_salida. Lo demás es contexto.
2. **Validador**: `claude/validar_extraccion.py` del proyecto.
3. **Escritor de matriz**: `claude/escribir_matriz.py` del proyecto.
4. **Artículo en PDF**: adjunto o entre los archivos del proyecto.
5. **Matriz vigente (.xlsx)**: la última versión que entregó esta skill en la conversación o la que adjunte el usuario. Si hay varias, preguntar cuál es la vigente. Nunca se trabaja sobre el original: siempre sobre una copia.
6. **Datos del equipo**: Documento, Estudio inicial, Covidence # y vía de identificación. Si no los da el usuario:
   - Documento y Estudio: buscarlos en la matriz por Title o Cita. Si el artículo ya está, se reextrae sobre esas mismas filas. Si no está, proponer el siguiente consecutivo y pedir confirmación en una sola pregunta.
   - Covidence #: tomarlo de la matriz si ya existe. Si no, dejarlo vacío y registrar la vía como "Otros métodos: <lo que diga el usuario>".
   - El número del nombre del PDF no es el número de Documento; no se deducen uno del otro.

Si falta el libro de códigos o el validador, detenerse y pedirlos. No se extrae de memoria.

## Paso 0. Preparación (orquestador)

1. Copiar el libro, los dos scripts y el PDF a una carpeta de trabajo: `trabajo/<Documento>_<primer autor>/`.
2. Extraer el texto por página con marcas:
   `for p in $(seq 1 N); do echo "=== PAGINA $p ==="; pdftotext -layout -f $p -l $p articulo.pdf -; done > texto_por_pagina.txt`
3. Generar imágenes de las páginas que tengan tablas o figuras: `pdftoppm -r 110 -png articulo.pdf pag`.
4. Detectar páginas sin texto seleccionable (menos de 200 caracteres). Si las tablas de resultados o la sección de método están escaneadas, avisar al usuario antes de seguir. Los datos que solo existan en una imagen se leen de la imagen, llevan `leido_de_figura = true` y quedan marcados para verificación manual.
5. Crear el plan de tareas (TaskCreate) con los pasos 1 a 7.

## Paso 1. Extracción (Agente Extractor)

Lanzar un agente general (Agent, subagent_type general-purpose) con este encargo, reemplazando las rutas y los datos del equipo:

> Eres el Agente Extractor. Lee el libro de códigos en <ruta>: primero prompt_para_el_extractor y luego sus secciones normativas completas. Aplícalo al artículo <ruta PDF>, usando <texto_por_pagina.txt> y las imágenes <pag-*.png> para tablas y figuras. Datos del equipo: Documento = <n>, Estudio inicial = <n>, Covidence # = <n o vacío>, Vía = <texto>.
> Reglas no negociables:
> - Cada valor lleva página del PDF, ubicación y una cita literal y contigua de 25 palabras como máximo.
> - Nada de conocimiento externo: ni siglas, ni años, ni número de ítems, ni teorías que el artículo no diga.
> - Toda inferencia va a trazabilidad.inferencias y toda contradicción del artículo a discrepancias_en_el_articulo.
> - Si una regla del libro te obliga a escribir algo falso o no cubre el caso, no lo fuerces: repórtalo.
> Guarda la salida en <trabajo>/salida.json. Ejecuta `python3 validar_extraccion.py salida.json libro.json articulo.pdf` y corrige hasta llegar a 0 errores, sin inventar datos para lograrlo.
> Devuelve: (a) cuántas filas abriste y por qué; (b) los valores clave de cada fila (Incluir con su condición, r, metodo_obtencion_r, Beta, N, confianza); (c) los problemas del libro de códigos que encontraste, con la clave exacta del JSON y la redacción propuesta.

Al recibir la respuesta, el orquestador vuelve a ejecutar el validador. El informe del agente no basta como prueba de que la salida valida.

## Paso 2. Auditoría de evidencia (Agente Auditor, independiente)

Lanzar otro agente que **no** ve el razonamiento del extractor, solo su salida:

> Eres el Agente Auditor de evidencia. No extraes: verificas. Tienes el artículo <ruta PDF>, <texto_por_pagina.txt>, las imágenes <pag-*.png>, el libro de códigos <ruta> y la salida <salida.json>.
> Para cada fila y cada columna con valor distinto de faltante:
> 1. Abre la página citada y comprueba que la cita existe y que sostiene el valor. No basta con que la cita exista: tiene que justificar ese valor en esa columna. Para tablas, verifica la fila y la columna de la tabla. Para figuras y tablas en imagen, mira la imagen.
> 2. Comprueba que la categoría cumple la instruccion_operativa de la columna.
> 3. Comprueba que los faltantes (No indica, No aplica) son reales: busca en todo el artículo si el dato sí estaba.
> 4. Comprueba que no se abrieron filas de más ni de menos según regla_para_abrir_una_fila_nueva.
> Veredictos por celda: CONFIRMADO, REFUTADO (con la evidencia correcta: página y cita) o NO VERIFICABLE (con el motivo).
> Guarda en <trabajo>/auditoria_evidencia.json una lista de objetos {estudio, columna, auditor: "Auditor de evidencia", veredicto, hallazgo, evidencia, resolucion: null, estado: "Pendiente"} solo con los veredictos distintos de CONFIRMADO. Devuelve el conteo por veredicto y los hallazgos REFUTADO. Sin elogios.

## Paso 3. Segunda codificación ciega (Agente Codificador Ciego)

Lanzar un tercer agente que **no** ve salida.json. Codifica solo los campos críticos para el metaanálisis:

> Eres el Codificador Ciego. Con el libro de códigos <ruta> y el artículo <ruta PDF> (más texto e imágenes), extrae de forma independiente, para cada fila que corresponda abrir, solo estos campos, cada uno con página, ubicación y cita literal:
> - número de filas y su mapa de efectos;
> - Muestra;
> - Correlación Feli 1 - JP y metodo_obtencion_r;
> - Beta Fel 1- JP, tipo_de_efecto y tecnica_del_beta;
> - las dos fiabilidades con su tipo;
> - # Ítems e Items instrumento1;
> - Desempeño, Hedónica/eudaimónica y Tipo de felicidad real;
> - How measure the employee perfomance, Study design, Nivel y Analysis method (principal);
> - Direccionalidad de la relación e Incluir en meta análisi con su condición.
> No tienes acceso a otra extracción y no debes buscarla. Guarda en <trabajo>/codificacion_ciega.json y devuelve la tabla de valores.

## Paso 4. Conciliación (orquestador)

1. Comparar salida.json con codificacion_ciega.json campo por campo. Las diferencias numéricas se comparan con tolerancia 0.001.
2. Juntar las discrepancias con los hallazgos del auditor en `auditoria.json`, con el mismo formato y auditor "Codificador ciego" para las diferencias.
3. Resolver cada punto **volviendo al PDF**, nunca por mayoría ni por confianza en un agente:
   - Si el artículo decide el punto, corregir salida.json, poner en `resolucion` la página y la cita que lo deciden, y marcar el estado como "Resuelto".
   - Si el artículo no lo decide, se conserva el valor más conservador (el faltante antes que el valor dudoso), la confianza baja a Baja, el caso se anota en advertencias_pendientes y el estado queda "Pendiente" para el usuario.
4. Ejecutar de nuevo el validador hasta llegar a 0 errores.
5. Calcular y registrar el acuerdo en los campos críticos (coincidencias sobre el total). Si baja del 80 %, avisar al usuario antes de escribir en la matriz.

## Paso 5. Escritura en la matriz

```
python3 escribir_matriz.py salida.json libro.json matriz_vigente.xlsx Matriz_sintesis_actualizada.xlsx auditoria.json
```

- El script reemplaza las filas con el mismo Estudio o agrega filas al final.
- Pone en cada celda un comentario con la fuente (página, ubicación y cita).
- Colorea: amarillo para lo inferido, naranja para las discrepancias del artículo y rojo para los hallazgos de auditoría pendientes.
- Actualiza las hojas Trazabilidad y Auditoria.
- Luego abrir el archivo con openpyxl y comprobar que la fila escrita tiene los 54 valores esperados.

## Paso 6. Retroalimentación del libro de códigos

Los problemas del libro que reporten los agentes (claves ambiguas, casos no cubiertos, reglas que obligarían a escribir algo falso) se agregan a `claude/retroalimentacion_libro_codigos.md` en el proyecto. Si no existe, se crea con un encabezado.

- Cada registro lleva: fecha, artículo, clave del JSON, problema, propuesta y agente que lo detectó.
- Para editar el documento: project_read, agregar el registro y project_write con el documento completo.
- **No se modifica el libro de códigos sin aprobación del usuario.** Cuando haya cinco o más registros abiertos, o el usuario lo pida, proponer una versión nueva del libro con esos cambios, rehacer el ejemplo_verificado y volver a validarlo.

## Paso 7. Entrega

1. Enviar con SendUserFile la matriz actualizada, salida.json y auditoria.json.
2. Responder en español institucional, sin guiones largos, con:
   - las filas escritas (Estudio, Cita, Incluir, r, Beta, N, confianza);
   - las celdas en rojo y en naranja, con una línea cada una;
   - las decisiones pendientes para el usuario;
   - el acuerdo entre extractor y codificador ciego.
3. No recapitular los pasos.

## Reglas del orquestador

- Los informes de los agentes son datos, no pruebas: toda afirmación que cambie una celda se comprueba en el PDF.
- Si el entorno no tiene la herramienta Agent, ejecutar los pasos 2 y 3 en secuencia y declarar al usuario que las auditorías no fueron independientes.
- Varios artículos en un mismo pedido: procesarlos uno por uno sobre la misma matriz acumulada, con un agente extractor y auditores nuevos por artículo. Verificar que Estudio no se repite entre artículos.
- Un artículo que el libro de códigos marque para eliminar o que no mida felicidad y desempeño no se extrae: se informa y se sugiere la decisión al usuario.
- Nunca se completan celdas con conocimiento previo del artículo ni con los valores antiguos de la matriz. Los valores antiguos solo sirven para comparar: las diferencias se listan en la entrega.
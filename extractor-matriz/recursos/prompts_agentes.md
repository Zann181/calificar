# Prompts de los agentes (insumo para M4)

Fuente: skill extractor-matriz-felicidad-desempeno (copia íntegra en skill-extractor-matriz-felicidad-desempeno/SKILL.md). Los textos entre comillas angulares (<ruta>, <n>) son variables que el programa reemplaza.

Adaptaciones obligatorias en el programa (CONSTRUIR_extractor_matriz.md, sección 8):
- Donde el prompt dice "texto_por_pagina.txt", el programa entrega el texto etiquetado por bloques ([pNN-bMM | tipo] ...), y cada evidencia debe incluir "bloque_id".
- Donde dice "Ejecuta validar_extraccion.py", el programa ejecuta el validador por su cuenta y le reenvía al extractor los errores (máximo 3 iteraciones); el agente no ejecuta comandos.
- Donde dice "Guarda en <archivo>", el programa espera la respuesta JSON en el mensaje del modelo.

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

## Rol 4. Conciliador (definido en CONSTRUIR_extractor_matriz.md, sección 8.2)

En la skill, la conciliación la hace el orquestador volviendo al PDF. En el programa, ese paso es una llamada al modelo con este encargo:

> Eres el Conciliador. Recibes una discrepancia o un hallazgo REFUTADO sobre una celda: el valor del extractor, el valor alternativo (del codificador ciego o del auditor), la regla del libro de códigos que aplica (columnas[<clave>].instruccion_operativa) y el texto completo de los bloques citados por ambas partes, con sus identificadores.
> Decide usando solo el texto de esos bloques. Devuelve un objeto JSON:
> {"decision": "VALOR_EXTRACTOR" | "VALOR_ALTERNATIVO" | "OTRO" | "PENDIENTE", "valor": <valor final o null>, "bloque_id": "<id>", "cita_textual": "<subcadena literal de 25 palabras como máximo>", "razonamiento": "<una o dos oraciones>"}
> Si el texto de los bloques no alcanza para decidir, responde PENDIENTE. No uses conocimiento externo ni elijas por mayoría.
> Reglas del programa, no del modelo: la cita del conciliador se ancla con M5 igual que cualquier otra; si no queda VERIFICADA, la decisión se trata como PENDIENTE. Si PENDIENTE, se conserva el valor más conservador (el faltante antes que el valor dudoso), confianza Baja, estado del hallazgo Pendiente para revisión humana.

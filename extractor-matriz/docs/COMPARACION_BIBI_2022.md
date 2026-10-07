# Comparación: extracción vs. matriz original (Bibi et al., 2022)

Fecha: 2026-10-07. Original: `Constructor/Matriz_de_sintesis_con_notas (1).xlsx` (Documento 3, Estudios 4 y 5).
Extracción: corrida real `fa4204bb` (4 roles, 19 páginas, 6,82 USD equivalentes). Las columnas se emparejan por
posición (A a BB), no por nombre: el Excel repite encabezados (`cómo lo llaman`, `Fiabilidad Alfa - Omega`).

## Resultado global (108 celdas = 2 filas × 54 columnas)

| Categoría | Celdas | % |
| --- | --- | --- |
| Idéntica | 57 | 52,8 |
| Equivalente (mismo dato, otra forma) | 8 | 7,4 |
| Distinta | 32 | 29,6 |
| La extracción dice «No indica» y el original tiene dato | 7 | 6,5 |
| La extracción tiene dato y el original no | 4 | 3,7 |

Coincidencia literal o equivalente: **60,2 %**. Pero «distinta» mezcla tres cosas muy diferentes:

| Tipo de diferencia | Celdas | Qué es |
| --- | --- | --- |
| Forma, idioma o vocabulario | 23 | Mismo contenido: paráfrasis frente a copia literal, fechas ISO frente a texto, etiquetas libres (`SWB`, `CFA`) frente al vocabulario del libro |
| **De fondo, a verificar en el PDF** | **15** | 8 distintas (ítems, teorías) + 7 donde la extracción no encontró dato |
| La extracción mejora al original | 4 | Teoría 3 e Inclusion criteria que el original dejó vacíos |
| Error del original | 1 | Estudio 5, Definition Happiness: copia la definición de felicidad *hedónica* en la fila *eudaimónica* |

Sin contar la forma, **solo 15 de 108 celdas (14 %) requieren decidir quién acierta.**

## Lo que coincide exacto (lo crítico)

Muestra 311 · Correlación 0.77 y 0.787 · Beta 0.514 y 0.766 · fiabilidades 0.783, 0.738 y 0.871 · País China · Año 2022 ·
Sector Hoteles · Desempeño Innovador · Hedónica/eudaimónica · Nivel Individual · Study design · Direccionalidad HP ·
Analysis method (principal) CB-SEM · Software SPSS y AMOS · Tipo de muestreo · Instrumento CFA = Sí.
También coincide **Incluir en meta análisis = SI**, que es justo la celda que el auditor y el codificador ciego
discuten (proponen `SEM latente`, condición 9). El original y el extractor coinciden, y los dos podrían estar
equivocados: decisión del responsable del dominio.

## Diferencias de fondo (a verificar en el PDF)

| Columna | Original | Extracción | Nota |
| --- | --- | --- | --- |
| R `# Ítems` (E4 y E5) | 7 | 3 | La extracción cuenta los ítems de la escala de la fila |
| W `Items instrumento1` | 11 (E4) · 28 (E5) | 5 (E4) · 22 (E5) | El original parece sumar escalas; la extracción cuenta las de ese constructo |
| AM `Teoría 1` | Autodeterminación | Otra: Maslow | Orden y elección distintos |
| AN `Teoría 2` | Satisfacción de necesidades | Autodeterminación | Mismas teorías, otro orden |
| AJ, AK `Ejemplo ítem` (felicidad y desempeño) | Ítem citado | No indica | La extracción no halló los ítems (¿apéndice o tabla de medidas?) |
| AX `Método de aplicación` | on-site | No indica | Dato del original sin ubicación comprobada |
| AA `Adaptado al trabajo` (E5) | Sí | No indica | **La extracción es inconsistente**: en E4 sí puso Sí |

## A favor de la extracción
- Cada dato trae página, bloque y cita (137 citas verificadas, 0 sin ubicar). El original no.
- Fechas separadas correctamente (Start 2020-08-10, End 2020-08-20); el original repite el rango en ambas celdas y arrastra el texto «Recogida de datos».
- `Inclusion criteria` y `Teoria 3` completos donde el original dice «No indica» o vacío.
- Detecta que las correlaciones son latentes (Fornell-Larcker del AFC).

## En contra (qué mejorar)
- `No indica` donde el original sí tiene dato (7 celdas): revisar si el dato está en el PDF; si está, es una falla de la búsqueda del extractor.
- Inconsistencia entre filas hermanas (`Adaptado al trabajo`).
- Para comparar con el original sin ruido haría falta una columna «forma normalizada» (por ejemplo, vocabulario cerrado en `Tipo de felicidad real` y `Validez CFA`).

## Nota sobre esta comparación
Es **un solo artículo**. Sirve para ver el tipo de diferencias, no para medir la precisión del extractor. El original
también tiene errores (ver arriba), así que no es una verdad absoluta. Para una medida fiable: los 5 pilotos de la
aceptación de F2.

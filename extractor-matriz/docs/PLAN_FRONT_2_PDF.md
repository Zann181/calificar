# Plan: levantar el front con solo los 2 PDF de prueba (Kumar 2022 y Singh 2023)

## 1. Objetivo y alcance
- Demo funcional de la interfaz con **solo Kumar (2022) y Singh (2023)**, sin MinerU ni llamadas al modelo.
- Dos diseños sobre el mismo código: **iPhone** (tarjetas, navegación inferior, gestos) y **PC** (tablas densas, panel de evidencia, visor PDF lado a lado).
- Fuera de alcance: extracción en vivo, cola (F3), roles, los otros 46 PDF.

## 2. Estado actual (verificado)
- Front React/Vite/AG Grid ya corre: login, grilla de 71 filas x 54 columnas, visor PDF, ficha de evidencia, `Tarjetas.tsx` (105 líneas).
- Solo hay 11 `@media` en `estilos.css` (1342 líneas): el adaptativo es parcial.
- `herramientas/demo_interfaz.py` ya carga Kumar y Singh como filas EXTRAÍDAS con evidencia anclada, usando las salidas guardadas de MinerU en `recursos/fixtures/mineru`. No necesita MinerU ni modelo.
- La BD actual tiene los 53 PDF y 71 filas heredadas, lo que ensucia la demo.

## 3. Fases

### Fase A. Datos de demo limpios (30 min)
1. BD aparte para la demo: `datos/demo.db` y `datos/almacen_demo/` (nuevo `.env.demo`), para no tocar la BD completa.
2. Secuencia: `alembic upgrade head` → `semilla` → `importar-matriz` → `demo_interfaz.py`.
3. Cargar solo `kumar_2022.pdf` y `singh_2023.pdf` (no `cargar-carpeta`).
4. Filtro de proyecto "Demo": la grilla muestra solo las filas de esos 2 documentos (hoy "Solo extraídas" ya ayuda).
5. Aceptación: `GET /matriz/filas` devuelve solo filas de Kumar y Singh; los 2 PDF abren en el visor con la cita resaltada.

### Fase B. Sistema de diseño y adaptativo (1 día)
1. Tokens CSS: color, espaciado, radios y tipografía (SF Pro / system-ui), claro y oscuro (`prefers-color-scheme`).
2. Tres breakpoints: **<600 px** (iPhone), **600-1024 px** (tablet, 2 paneles) y **>1024 px** (PC, 3 paneles).
3. Un solo árbol de componentes; el layout cambia por CSS y un hook `useBreakpoint()`.

### Fase C. Diseño iPhone (1,5 días)
- **Navegación:** barra inferior con 3 pestañas: Artículos, Matriz, Revisión. Cabecera con título grande que se encoge al desplazar.
- **Artículos:** lista con tarjetas (autor-año, estado, # de filas, barra de progreso de celdas verificadas). Deslizar para excluir.
- **Matriz:** una **tarjeta por fila de efecto**, con campos agrupados en secciones plegables (Identificación, Muestra, Constructos, Instrumentos, Efectos, Método). Cada campo es un chip con color de estado. Reutilizar `Tarjetas.tsx`.
- **Evidencia:** al tocar un campo, abre una **hoja inferior** (bottom sheet) con la cita, la página y botones Aprobar / Corregir / Rechazar. Botón "Ver en PDF" abre el visor a pantalla completa con el bloque resaltado, y un gesto de retroceso.
- **Detalles iOS:** objetivos táctiles de 44 px, `safe-area-inset`, `viewport-fit=cover`, sin zoom al enfocar inputs (16 px), háptico visual, soporte PWA (`manifest`, ícono, "Añadir a pantalla de inicio").

### Fase D. Diseño PC (1,5 días)
- **Layout 3 paneles redimensionables:** Artículos (colapsable) | Tabla | Evidencia + PDF.
- **Tabla (AG Grid):**
  - columnas fijadas (Documento, Estudio, Cita), filas agrupables por artículo;
  - filtros por columna y búsqueda global;
  - selector de columnas con grupos de la matriz y presets "Esencial / Meta-análisis / Todas";
  - edición en celda con motivo obligatorio;
  - atajos de teclado: `A` aprobar, `C` corregir, `R` rechazar, flechas para moverse.
- **Panel derecho:** ficha de evidencia arriba, visor PDF abajo, resaltado sincronizado con la celda activa.
- **Barra superior:** contadores (Pendientes, Por confirmar, Aprobadas), botón Exportar Excel.

### Fase E. Verificación (0,5 día)
- Pruebas visuales con el navegador integrado en 375x812 (iPhone), 768x1024 y 1440x900, en claro y oscuro.
- Verificar: sin scroll horizontal en móvil, contraste AA, navegación completa solo con teclado en PC.
- Pruebas de componentes (Vitest) para `Tarjetas`, `FichaEvidencia` y `useBreakpoint`. Agregar un job de front al CI (hoy no existe).

## 4. Uso de `claude.exe` (`C:\Users\maleg\.local\bin\claude.exe`)
- Para esta demo **no se llama al modelo**; se usan las extracciones guardadas de F0.
- Para la extracción real más adelante: poner `CLAUDE_CLI=C:\Users\maleg\.local\bin\claude.exe` en `.env`. Hoy el valor es `claude` y depende del PATH.
- Requisito: sesión iniciada en esa CLI. Cada extracción cuesta unos 2,6 USD y 4 min por artículo.

## 5. Entregables
1. `.env.demo` y script `herramientas/levantar_demo.ps1` (BD demo + API + front en un paso).
2. Front adaptativo (iPhone / tablet / PC) y PWA básica.
3. Capturas de cada tamaño y reporte de verificación.

## 6. Riesgos
| Riesgo | Mitigación |
|---|---|
| El visor PDF resalta el rectángulo del bloque, no la línea (H2) | Aceptable en la demo; se mejora en F4 |
| AG Grid Community no tiene agrupación de filas | Agrupar con columna "Artículo" fija y filtro |
| Sin MinerU, solo funcionan los 2 PDF con salidas guardadas | Es el alcance pedido |
| pymupdf es AGPL | Solo importa si se ofrece como servicio en red |

## 7. Orden sugerido
A → B → C → D → E. Al terminar A y B ya se puede ver la demo en el navegador; C y D se pueden hacer en paralelo con dos agentes.

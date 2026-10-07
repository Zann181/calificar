# Extractor de matriz felicidad y desempeño

## Abrir y cerrar

Doble clic en **Extractor de matriz** (acceso directo del Escritorio). Arranca el servidor sin consola, abre la aplicación
en su propia ventana y, al cerrar esa ventana, apaga el servidor. Un segundo doble clic trae la ventana al frente.
El lanzador es `Extractor.ps1` (puerto 8765; registro en `datos/extractor.log`). Para crear el acceso directo y el ícono
(también `Extractor.vbs`, que lleva rutas de este equipo): `servicio-mineru/.venv/Scripts/python herramientas/crear_icono_y_acceso.py`.

Especificación: `docs/CONSTRUIR_extractor_matriz.md`. Decisiones: `docs/decisiones/`.

## Puesta en marcha sin Docker (ADR 0003)

Requisitos: Python 3.12 y `pdftotext` (para `validar_extraccion.py`).

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

En `.env` (copiado de `.env.example`) defina `DATABASE_URL=sqlite:///.../datos/extractor.db`, `ALMACEN_DIR=.../datos/almacen`,
`SESION_SECRETO` y `ADMIN_CLAVE` (mínimo 10 caracteres). Luego, desde `backend/`:

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli semilla
.venv/Scripts/python -m app.cli importar-matriz ../recursos/Matriz_de_sintesis_con_notas.xlsx
.venv/Scripts/python -m app.cli cargar-carpeta "../../Artículos revisión sistemática"
.venv/Scripts/python -m app.cli exportar ../datos/exportada.xlsx
.venv/Scripts/uvicorn app.main:app --reload
```

Convertir los PDF necesita `servicio-mineru` en marcha (su propio entorno virtual, puerto 8001) y luego
`python -m app.cli convertir-pendientes`. En CPU toma de 11 a 21 s por página (ADR 0001).

## Extracción (F2)

Necesita la CLI de Claude Code con sesión iniciada (`claude`; si no está en el PATH, defina `CLAUDE_CLI` en `.env`).
No usa clave de API (ADR 0002). Cada artículo toma unos 4 minutos y unos 2,6 USD equivalentes del límite de la
cuenta (F0). Desde `backend/`:

```bash
.venv/Scripts/python -m app.cli extraer <articulo_id> --documento 48 [--estudio 72] [--covidence 123] [--via "Covidence"]
```

El artículo debe estar convertido (LISTO). La extracción corre los cuatro roles, valida, ancla y concilia. Si
termina, escribe las filas en la matriz en POR_REVISAR. Si el validador mantiene errores, queda FALLIDA y no escribe
nada. Para volver a extraer un artículo ya extraído, agregue `--reextraer` (y `--motivo` si estaba aprobado).
Decisiones: ADR 0004.

## Calidad

```bash
cd backend
.venv/Scripts/ruff check app tests migrations
.venv/Scripts/mypy app
.venv/Scripts/lint-imports
.venv/Scripts/pytest -q                 # unitarias e integración (SQLite)
.venv/Scripts/pytest -q -m "not integracion"
```

## Herramientas de F0

`herramientas/`: conversión y tiempos de MinerU, rectángulos del ADR 0001, verificación automática de coordenadas,
validador con UTF-8 y arnés de extracción con los cuatro roles (`f0_extraccion.py`, Claude Code CLI, ADR 0002).

## Interfaz (adelanto de F4)

```bash
cd frontend && npm install && npm run dev      # http://localhost:5173, con la API en el puerto 8000
```

Para ver Kumar y Singh como filas extraídas, con citas ancladas y resaltadas en el PDF (datos de la prueba F0, no del
motor de F2): desde `backend/`, `.venv/Scripts/python ../herramientas/demo_interfaz.py`.

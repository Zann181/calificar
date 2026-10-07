# Extractor de matriz felicidad y desempeño

Programa extrae datos de artículos científicos PDF y llena matriz de síntesis de revisión sistemática sobre felicidad y desempeño laboral. Cada celda guarda evidencia: página, bloque, rectángulo, cita literal. Regla central: dato sin ubicación comprobable nunca entra como verificado; toda decisión técnica se subordina a ella.

Especificación en `docs/CONSTRUIR_extractor_matriz.md`. Decisiones se registran como ADR en `docs/decisiones/`. Responsable del dominio: Pablo Andrés Erazo Muñoz.

## Regla de ubicación (vigente desde 2026-10-06)

- La versión oficial y siempre actualizada es `calificar/extractor-matriz/`. Todo cambio se hace aquí.
- `extractor-matriz-master/` es una copia anterior: no se edita ni se usa para arrancar la app.
- El acceso directo `calificar/Extractor de matriz.lnk` (y `calificar/Extractor.vbs`) arranca esta carpeta y la actualiza
  sola al abrir (`Extractor.ps1`: git pull con autostash, dependencias, migraciones, recompilar interfaz).
- Uso local sin login por defecto (`SIN_LOGIN=true`); para un servidor en red, `SIN_LOGIN=false`.

## Datos: principal y de test

- Base principal (`datos/extractor.db`): solo los 2 artículos analizados, Kumar (Estudio 1) y Singh (Estudio 71).
- Conjunto de test (`datos/test/`): la matriz completa (71 filas, 53 PDF) tal como se importó. Para usarlo:
  `DATABASE_URL=sqlite:///<ruta>/datos/test/extractor.db` y `ALMACEN_DIR=<ruta>/datos/test/almacen` (las variables de entorno mandan sobre `.env`).
- Rehacer la principal: `alembic upgrade head`, `semilla`, `importar-matriz`, `cargar-carpeta ../recursos/fixtures`, `herramientas/demo_interfaz.py`,
  y borrar las filas con `origen != 'EXTRAIDA'`.

## Reglas de la especificación (sección 0)

- Libro de códigos `recursos/Libro_de_codigos_extraccion_v2.json` es la norma. Columnas, vocabularios y validaciones salen de él; no copiar reglas al código ni escribir 54 columnas a mano.
- No reescribir `recursos/validar_extraccion.py` ni `recursos/escribir_matriz.py`. Usar vía adaptadores; cualquier cambio se propone al responsable del dominio.
- Algo no definido en especificación → detenerse y preguntar al responsable del dominio. No tomar decisiones de dominio por cuenta propia.
- Resultado contradice especificación → registrar ADR nuevo en `docs/decisiones/` y consultar antes de seguir.
- Fase solo se cierra cuando pasan sus pruebas de aceptación (sección 12).
- Código usa lenguaje ubicuo en español (sección 3). Identificadores sin tildes (`Articulo`, `Extraccion`); textos de interfaz con tildes.

## Arquitectura

- Monolito modular con DDD en `backend/app/contextos/`: `biblioteca`, `normas`, `extraccion`, `matriz`, `orquestacion`, `exportacion`.
- Cada contexto tiene `dominio/`, `aplicacion/`, `puertos.py`, `adaptadores/`, más `eventos.py` con eventos públicos.
- Contexto nunca lee tablas de otro. Comunicación por casos de uso o eventos (outbox transaccional, `app/compartido/outbox.py`).
- `app/composicion.py` único módulo que conoce todos los contextos; ahí viven puentes entre ellos.
- `import-linter` hace cumplir capas: dominio no importa infraestructura, aplicación no importa adaptadores, ninguno importa `subprocess` ni `pymupdf`.
- Modelo de lenguaje se llama con CLI de Claude Code (`claude -p`), no con clave de API (ADR 0002). Pruebas usan `ModeloGrabado`, nunca modelo real.
- Sin Docker (ADR 0003): SQLite y archivos en disco. F3 necesita PostgreSQL.

## Comandos (desde `backend/`)

```bash
.venv/Scripts/ruff check app tests migrations
.venv/Scripts/mypy app
.venv/Scripts/lint-imports
.venv/Scripts/pytest -q
.venv/Scripts/alembic -x url=sqlite:///ci.db upgrade head && .venv/Scripts/alembic -x url=sqlite:///ci.db check
```

Correr todos antes de terminar cambio. Cada tabla nueva necesita migración Alembic en `migrations/versions/`.

## Estado (2026-10-06)

- F0 y F1 terminadas. F1 construida sin Docker.
- F2 (extracción y anclaje) construida; pruebas doradas pasan. Para aceptación faltan corridas reales sobre 5 artículos piloto elegidos por responsable del dominio. ADR 0004 propuesto.
- Extracción real cuesta ~2,6 USD equivalentes y 4 min por artículo. Preguntar antes de correr una.
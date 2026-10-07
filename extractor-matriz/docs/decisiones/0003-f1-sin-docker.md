# ADR 0003 · F1 sin Docker: SQLite y almacén en disco

- Estado: **Aceptado** (instrucción del responsable del dominio, 2026-10-06)
- Fecha: 2026-10-06
- Se aparta de: sección 2 (PostgreSQL 16, MinIO, pruebas con Testcontainers) y tarea de F1 "Docker Compose funcional"

## Contexto

El equipo de trabajo tiene 7,7 GB de RAM. Docker Desktop, PostgreSQL y MinIO compiten por esa memoria con MinerU,
que ya la deja casi agotada al convertir (ADR 0001). El responsable pidió avanzar F1 sin Docker.

## Decisión

1. **Base de datos.** `DATABASE_URL=sqlite:///.../datos/extractor.db`. El código ya era portable: `JsonB` cae a JSON
   en SQLite y el índice parcial `uq_libro_activo` declara `sqlite_where`. La migración de Alembic se genera y se
   prueba sobre SQLite (`render_as_batch`), y produce el mismo esquema en PostgreSQL (`alembic upgrade head --sql`
   con una URL de PostgreSQL).
2. **Archivos.** El adaptador nuevo `AlmacenEnDisco` (`ALMACEN_DIR`) reemplaza a MinIO. Rechaza claves que salgan de
   su carpeta. Como no emite URL firmadas, la API entrega el PDF directamente.
3. **Pruebas de integración.** Corren sobre SQLite, con la migración real, `AlmacenEnMemoria` y `ConversorFijo`
   (marcador `integracion`). No necesitan Docker ni red.
4. **MinerU.** `servicio-mineru` ya corría sin Docker, en su propio entorno virtual. No cambia.

## Consecuencias

- Queda **sin probar en PostgreSQL**:
  - `FOR UPDATE SKIP LOCKED` del despachador de la outbox;
  - la concurrencia real entre trabajadores;
  - JSONB.

  SQLite admite un solo escritor a la vez. Basta para un usuario y un despachador, no para `--scale trabajador=2`.
- **F3 necesita PostgreSQL.** La reserva atómica de números de Estudio y la prueba con 20 extracciones en paralelo
  (aceptación de F3) solo tienen sentido con PostgreSQL. Antes de F3 hay que elegir:
  - Docker en un equipo con más memoria;
  - PostgreSQL instalado sin Docker;
  - o un servidor del grupo.
- La tarea de F1 "Docker Compose funcional" queda **pendiente**. `docker-compose.dev.yml` no se tocó.
- El cambio de motor es solo de configuración: `DATABASE_URL` y `ALMACEN_DIR`. No hay ramas de código por motor,
  salvo el bloqueo de filas, que ya estaba condicionado al dialecto.

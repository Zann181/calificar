# ADR 0007 · Aplicación de escritorio para un solo usuario

- Estado: **Aceptado** (instrucción del responsable del dominio, 2026-10-12: «no quiero que tenga seguridad, solo
  quiero que sea una aplicación de escritorio»)
- Fecha: 2026-10-12
- Se aparta de: sección 2 (Dramatiq con Redis, WebSocket, PostgreSQL), sección 10 (autenticación y roles),
  sección 13 (etapas 2 y 3), aceptación de F3 y la prueba de F5 «un usuario `extractor` no puede aprobar»
- Completa: ADR 0003, que dejó F3 a la espera de elegir cómo tener PostgreSQL

## Contexto

La especificación preveía un servidor del grupo con varios usuarios y trabajadores en paralelo. En la práctica la
aplicación corre en el equipo del responsable: se abre con el acceso directo (`Extractor.ps1`), escucha solo en
127.0.0.1 y la usa una persona. El ADR 0003 dejó pendiente elegir PostgreSQL antes de F3.

## Decisión

1. **Sin PostgreSQL, Redis ni Dramatiq.** Se queda SQLite y la cola dentro del proceso
   (`extraccion/aplicacion/ejecutor.py`), guardada en la base para retomarla al abrir.
2. **Sin WebSocket.** La interfaz consulta el avance cada pocos segundos (`GET /extracciones/avance`).
3. **Sin login ni roles.** La API entra como el usuario local (`ADMIN_CORREO`), que firma las revisiones. Los roles
   `extractor` y `revisor` no se aplican. La tabla `usuarios` queda solo para la firma.
4. **Las etapas 2 y 3 de despliegue (sección 13) quedan fuera de alcance.**

## Aceptación de F3 que sigue vigente

- Un lote de 10 artículos termina con estados correctos (con `ModeloGrabado`).
- Cancelar una extracción en cola funciona.
- Un artículo en Error se puede volver a lanzar o restablecer (ADR 0006).
- Los números de Estudio no se repiten. Con una sola extracción a la vez (`EXTRACCIONES_EN_PARALELO=1`) basta la
  reserva dentro de la transacción; la prueba con 20 trabajadores en paralelo ya no aplica.

## Consecuencias

- `FOR UPDATE SKIP LOCKED` y la concurrencia entre trabajadores siguen sin probarse; no hacen falta.
- Si algún día se comparte en red, hay que volver a abrir esta decisión: sin login, cualquiera con acceso al puerto
  puede aprobar celdas.

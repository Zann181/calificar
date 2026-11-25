# ADR 0009 · Nube de solo lectura con sincronización unidireccional

- Estado: **Propuesto** (a la espera de la aprobación del responsable del dominio)
- Fecha: 2026-11-24
- Reabre: ADR 0007 punto 3 («sin login ni roles») **solo para el modo nube**; el uso local sigue sin login
- Se apoya en: ADR 0003 (SQLite y disco en local), ADR 0007 (escritorio, un usuario)
- Plan de ejecución: `docs/PLAN_NUBE_SINCRONIZACION.md`

## Contexto

El responsable quiere ver la matriz, los PDF y el visor desde la nube, sin Claude por ahora, y que cada cambio hecho en
el equipo local aparezca solo en la página. Más adelante quiere extraer con Claude directamente desde la nube. El ADR
0007 dejó escrito que, si algún día se comparte en red, hay que volver a abrir la decisión porque la API no tiene login.

Datos de hoy (base principal): 79 filas, 4 661 celdas, 53 PDF (35 MB), ~18 MB de JSON entre documentos estructurados,
extracciones y celdas. El volumen es pequeño: el problema es de arquitectura, no de tamaño.

## Decisión

1. **Un solo código, dos modos.** La misma imagen corre con `MODO=local` (hoy) o `MODO=nube`. En modo nube la API
   rechaza toda escritura de dominio, ofrece la ingesta `/api/v1/sync/*` y sirve la misma interfaz compilada.
2. **La nube es una réplica de solo lectura.** El equipo local es el único escritor (fuente de verdad). Sin fusión de
   conflictos, sin CRDT, sin escritura desde la nube.
3. **Sincronización «disparada por eventos, reconciliada por contenido».** Un agente dentro de la app local (contexto
   nuevo `sincronizacion`) se despierta con los eventos de la outbox y con un temporizador, calcula el hash canónico de
   cada agregado, lo compara con el manifiesto de la nube y envía solo la diferencia. Es idempotente y se repara sola.
4. **Los PDF viajan por contenido** (SHA-256, ya es su identidad), antes que los datos que los referencian.
5. **Nube = PostgreSQL + almacén de objetos compatible con S3 + un contenedor.** Ya existen `AlmacenS3`, `JsonB`,
   `psycopg` y la redirección a URL firmada del PDF. El visor en vivo es sondeo de `GET /api/v1/revision` (coherente con
   el ADR 0007: sin WebSocket).
6. **Seguridad que falla cerrada.** Lectores con inicio de sesión (lista de correos permitidos); el agente con un token
   de servicio de solo escritura en `/sync/*`. `MODO=nube` no arranca sin proveedor de identidad configurado. Los PDF
   nunca tienen URL pública.
7. **Panel de configuración** en la interfaz local para definir el destino (URL + token), qué se sube y cuándo, con
   estado, bitácora y botones de probar, sincronizar y verificar. El token vive en el almacén de credenciales del
   sistema, no en `.env` ni en la base.
8. **Nada de Claude en la nube en esta etapa.** Se dejan las «costuras» para después (sede por proyecto, cola en la base,
   API sin estado, blobs por contenido) sin construir lo que no se usa.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Instantáneas JSON estáticas en un bucket + visor estático | La más barata, pero es un callejón sin salida: no hay base ni API donde después corra Claude, y obliga a reimplementar en el visor lo que hoy calcula la API (`_celda_resumen`). |
| Subir el archivo SQLite entero (o Litestream) | Replica bytes, no significado; cada aprobación sube ~20 MB; ata la nube a SQLite; inservible cuando la nube escriba. |
| Que la interfaz de la nube lea la base directo (PostgREST/RLS) | Duplica la lógica de la API en otro lugar y la deja derivar. |
| Sincronización bidireccional desde el inicio | Introduce conflictos sin necesidad; se resuelve más tarde con «cambio de sede» explícito (fase 4). |
| Montar la carpeta `datos/` en OneDrive/Drive | Corrompe SQLite en uso y no da visor. Solo sirve como respaldo de exportaciones. |

## Consecuencias

- Hay que probar por primera vez el código en PostgreSQL (migraciones, JSONB, pool); es la fase 0 y el riesgo mayor.
- La nube y el equipo local deben mantener esquemas compatibles: se despliega primero la nube; si el local es más nuevo,
  la nube responde 426 y el panel avisa «la nube necesita actualizarse».
- Los PDF son artículos con derechos de terceros: la nube debe ser privada y con lista de acceso (ver plan, sección 7).
- Cuando se quiera Claude en la nube habrá que reabrir el ADR 0002 (la CLI con sesión iniciada no existe en un
  contenedor) y escribir el ADR de «cambio de sede».

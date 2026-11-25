# ADR 0009 · Réplica completa en la nube de solo lectura, gratuita, con sincronización unidireccional

- Estado: **Aceptado** (responsable del dominio, 2026-11-24: «Sí, Fase 0»)
- Fecha: 2026-11-24 (v2: extracción completa y alojamiento gratuito)
- Reabre: ADR 0007 punto 3 («sin login ni roles») **solo para el modo nube**; el uso local sigue sin login
- Se apoya en: ADR 0003 (SQLite y disco en local), ADR 0007 (escritorio, un usuario)
- Plan de ejecución: `docs/PLAN_NUBE_SINCRONIZACION.md`

## Contexto

El responsable quiere ver desde la nube la matriz, los PDF, el visor y la **extracción completa** de cada artículo, sin
Claude por ahora, con cada cambio local reflejado solo y **sin pagar**. Más adelante quiere extraer con Claude desde la
nube. El ADR 0007 dejó escrito que, si algún día se comparte en red, hay que volver a abrir la decisión porque la API no
tiene login.

Datos de hoy (base principal): 79 filas, 4 661 celdas, 59 extracciones (4,5 MB), 53 PDF (35 MB), 51 documentos
estructurados (8,9 MB), crudo de MinerU (24 MB). Total ≈ 80 MB: el problema es de arquitectura y de plan gratuito, no de
volumen.

## Decisión

1. **Un solo código, dos modos.** La misma imagen corre con `MODO=local` o `MODO=nube`. En la nube la API rechaza toda
   escritura de dominio (405), ofrece `/api/v1/sync/*` y sirve la misma interfaz compilada.
2. **La nube es una réplica de solo lectura; el equipo local es el único escritor.** Sin fusión de conflictos.
3. **La réplica es completa:** todas las columnas de cada extracción terminada (`COMPLETADA` o `FALLIDA`), documento
   estructurado, crudo de MinerU, PDF, matriz con sus evidencias e historial, libro de códigos y Excel base. No se
   replican cola, outbox, usuarios, registro, copias `.db` ni Excel exportados.
4. **Sincronización «disparada por eventos, reconciliada por contenido».** Un agente local (contexto `sincronizacion`)
   compara hashes canónicos con el manifiesto de la nube y envía solo la diferencia, de forma idempotente y
   autorreparable. Los archivos van primero, por SHA-256.
5. **Alojamiento a 0 USD:** Render Free (contenedor) + Neon Free (PostgreSQL) + UptimeRobot Free (keepalive a `/salud`
   sin tocar la base). Los archivos viven en PostgreSQL (`AlmacenEnBase`, `bytea`); el puerto `AlmacenDeArchivos`
   permite pasar a R2/S3 sin reescribir si superan ~400 MB.
6. **Seguridad que falla cerrada.** Lectores con Google y lista de correos (contingencia: GitHub OAuth); el agente con un
   token de servicio solo para `/sync/*`. `MODO=nube` no arranca sin esa configuración. PDF solo con sesión, sin enlaces
   públicos.
7. **Panel de configuración** local: destino (URL + token), qué se sube, cuándo, estado, bitácora, probar, sincronizar,
   verificar, reenviar todo. El token vive en el Administrador de credenciales de Windows.
8. **La extracción completa se hace legible** con endpoints nuevos en ambos modos y una sección «Extracción» en la
   ficha del artículo (hoy no existe ningún endpoint de lectura de esos datos).
9. **Nada de Claude en la nube en esta etapa.** Se dejan las costuras (sede por proyecto, cola en la base, API sin
   estado, archivos por contenido). La Fase 3 **deja de ser gratuita** (MinerU no cabe en ningún plan gratuito).

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Render Postgres gratuito | Caduca a los 30 días |
| Supabase Free (base + Storage) | Pausa el proyecto tras una semana con poca actividad; archivos de máx. 50 MB; más piezas |
| Oracle Always Free, Hugging Face Spaces, Fly.io, Koyeb | Recortes, restricciones o sin plan gratuito estable en 2026 |
| Cloud Run | Gratuito, pero exige cuenta de facturación con tarjeta |
| Instantáneas JSON estáticas en un bucket | Sin base ni API donde después corra Claude; duplica lógica del visor |
| Subir el archivo SQLite entero o Litestream | Replica bytes, no significado; ata la nube a SQLite; inservible cuando la nube escriba |
| Sincronización bidireccional desde el inicio | Conflictos innecesarios; el «cambio de sede» (fase 4) lo resuelve cuando haga falta |
| Resúmenes de extracción | Descartada por el responsable: se replica la extracción completa |

## Consecuencias

- Fase 0 con compuertas: PostgreSQL en el CI, memoria ≤ 350 MB en 512 MB de RAM, `AlmacenEnBase`, cliente OAuth de Google
  sin facturación y keepalive durante 48 h. Cada una tiene plan B definido.
- Los planes gratuitos cambian: las salidas están en la sección 3.4 del plan y la nube es **desechable** (se reconstruye
  con «Reenviar todo»). Desde la Fase 2 («Descargar proyecto desde la nube») la nube sí sirve de segundo resguardo; el respaldo de registro sigue siendo `datos/` local.
- Latencia: hasta ~1 min si Render durmió; ≤ 30 s de un cambio local al visor con la nube despierta.
- Esquemas: se despliega primero la nube; si el local es más nuevo, la nube responde 426 y el panel lo explica.
- Los PDF son artículos de terceros: la nube es privada y con lista cerrada de lectores.
- Para Claude en la nube habrá que reabrir el ADR 0002 y escribir el ADR de «cambio de sede».

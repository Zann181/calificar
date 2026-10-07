# ADR 0002 · Acceso al modelo de lenguaje mediante Claude Code CLI

- Estado: **Aceptado por el responsable del dominio el 2026-09-30**. Consecuencias medidas en F0, pendientes de revisión.
- Fecha: 2026-10-05
- Contradice: sección 2 (pila: "API de Claude mediante el SDK oficial `anthropic`") y sección 6 (adaptador `ClaudeApi`).

## Contexto

La especificación prevé el SDK `anthropic` con clave de API. El responsable del dominio decidió el 2026-09-30 no usar
clave de API y llamar al modelo con la sesión de Claude Code del equipo (`claude -p`).

## Decisión

El puerto `ModeloDeLenguaje` se implementa con un adaptador `ClaudeCli`, que ejecuta:

```
claude -p --output-format json --model <MODELO_ROL>
       --setting-sources "" --strict-mcp-config --no-session-persistence
       --system-prompt-file <libro.txt> --tools Read --allowedTools Read --add-dir <trabajo>
```

- El mensaje del usuario (texto etiquetado e instrucción del rol) entra por la entrada estándar.
- `--setting-sources ""` y `--strict-mcp-config` aíslan la llamada de los hooks, plugins, MCP y CLAUDE.md del equipo.
  Sin esto, la configuración personal del usuario se mezclaría en el comportamiento del extractor.
- Las imágenes de páginas no se adjuntan: el modelo las abre con la herramienta `Read`, limitada a la carpeta de trabajo.
- El JSON de resultado trae `usage` (entrada, escritura y lectura de caché, salida), `total_cost_usd`, `num_turns` y
  `duration_ms`. Con eso se registra el uso por rol, igual que con el SDK.
- El adaptador de prueba `ModeloGrabado` no cambia.

La implementación de referencia está en `herramientas/f0_extraccion.py` (función `llamar`).

## Consecuencias

1. **Autenticación.** La CLI usa el inicio de sesión guardado en el perfil del usuario (`~/.claude/.credentials.json`).
   Si vence, todas las extracciones fallan con `Failed to authenticate: OAuth session expired`, y eso ocurrió el
   2026-10-05. El adaptador no debe heredar las variables `CLAUDE_*` ni `ANTHROPIC_BASE_URL` del proceso anfitrión
   (por ejemplo, la aplicación de escritorio), porque apuntan a la sesión del anfitrión.
   Para el servidor del grupo (etapa 2) hace falta un token de larga duración (`claude setup-token`) en una variable
   de entorno del trabajador.
2. **Caché de instrucciones.** La CLI aplica la caché de forma automática. No se puede marcar a mano el bloque del
   libro como hace la sección 6 con el SDK. La caché real se mide en `uso.csv` (columnas `cache_escritura` y
   `cache_lectura`).
3. **Costo.** `total_cost_usd` es el equivalente a precios de API. Con suscripción no se factura por llamada, pero se
   consume el límite de uso de la cuenta. `TOPE_TOKENS_MENSUAL` debe contarse con `usage`, no con dólares.
4. **Concurrencia.** Cada llamada es un proceso aparte con algunos segundos de arranque. `CONCURRENCIA_EXTRACCION=2`
   es razonable; con más se alcanzan antes los límites de la suscripción.
5. **Salida estructurada.** No se usa `--json-schema`, porque el esquema del libro es grande. La salida se valida
   después con `validar_extraccion.py` y el ciclo de hasta 3 iteraciones.
6. **Prohibición en el dominio.** El contrato de import-linter que prohíbe `anthropic` en el dominio sigue vigente. Hay
   que agregar `subprocess` a los módulos prohibidos para `dominio/` y `aplicacion/`.

## Mediciones de F0 (2026-10-05)

Detalle en `docs/decisiones/f0/extraccion/*/` (`resumen.json`, `uso.csv`, salidas y validaciones). El costo es el
equivalente a precios de API que informa la CLI.

**Extracción completa de Kumar con los cuatro roles** (`kumar_2022__claude-opus-5-5`, libro v2.2):

| Rol | Modelo | Llamadas | Tokens de entrada (caché incluida) | Tokens de salida | Segundos | USD |
| --- | --- | --- | --- | --- | --- | --- |
| Extractor (2 iteraciones con el validador) | Opus 5.5 | 2 | 230 365 | 27 032 | 195 | 1,42 |
| Auditor | Opus 5.5 | 1 | 167 029 | 4 748 | 44 | 0,79 |
| Codificador ciego | Sonnet 5.5 | 1 | 143 967 | 3 016 | 23 | 0,33 |
| Conciliador | Opus 5.5 | 1 | 10 949 | 613 | 8 | 0,10 |
| **Total** | | 5 | 552 310 | 35 409 | unos 250 (auditor y ciego en paralelo) | **2,64** |

- La caché funciona sola: entre el 50 % y el 97 % de la entrada de cada llamada se leyó de la caché.
- Resultado: 0 errores del validador tras 2 iteraciones, `bloque_id` en las 49 evidencias, 22 de 22 campos críticos
  iguales al ejemplo verificado y acuerdo extractor-ciego de 1,00. El auditor dejó un hallazgo REFUTADO (la posible
  fila de satisfacción laboral) y el conciliador lo dejó PENDIENTE para el responsable del dominio.

**Comparación de modelos para el rol extractor** (22 campos críticos contra el ejemplo verificado):

| Artículo | Modelo | Acuerdo | Iteraciones | USD | Segundos |
| --- | --- | --- | --- | --- | --- |
| Kumar* | Opus 5.5 | 22/22 | 2 | 1,48 | 228 |
| Kumar* | Sonnet 5.5 | 22/22 | 2 | 0,63 | 103 |
| Singh | Opus 5.5 | 22/22 | 2 | 1,71 | 247 |
| Singh | Sonnet 5.5 | 21/22 | 2 | 0,78 | 157 |

\* Kumar es el `ejemplo_verificado` que el modelo recibe dentro del libro, así que su acuerdo no mide calidad. La
comparación válida es la de Singh. Ahí Sonnet clasificó Tipo de felicidad real como
`Otro: felicidad del empleado (...)` en lugar de `Índice compuesto (PHI, OHQ)`: es un error de categoría en un campo
crítico.

**Recomendación (la decide el responsable del dominio):**
- Opus para el extractor, el auditor y el conciliador.
- Sonnet para el codificador ciego: cuesta menos y, al ser un modelo distinto, la segunda codificación es más
  independiente.
- La muestra es pequeña (2 artículos, una fila cada uno). Hay que confirmarlo en los 5 pilotos de F2.

**Proyección para la biblioteca** (53 PDF únicos, con los cuatro roles):
- Unos 140 USD equivalentes.
- Unos 29 millones de tokens de entrada, en su mayoría leídos de la caché.
- Unas 3,5 horas de trabajo en serie (unos 4 minutos por artículo), o unas 2 horas con `CONCURRENCIA_EXTRACCION=2`.

Con suscripción, el límite real es la cuota de uso de la cuenta: conviene extraer por lotes.

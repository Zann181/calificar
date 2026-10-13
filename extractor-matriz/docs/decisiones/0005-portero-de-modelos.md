# ADR 0005 · Portero de modelos: Sonnet o Haiku por llamada, sin Opus

- Estado: **Propuesto**. Lo pidió el responsable del dominio el 2026-10-12; los umbrales quedan pendientes de los 5
  pilotos de F2.
- Fecha: 2026-10-12
- Se aparta de: sección 8.2 y sección 11 (un modelo fijo por rol con `MODELO_EXTRACTOR`, `MODELO_AUDITOR`,
  `MODELO_CIEGO` y `MODELO_CONCILIADOR`) y de la recomendación del ADR 0002 (Opus para extractor, auditor y
  conciliador).

## Contexto

El responsable del dominio pidió no usar Opus y poner porteros que decidan, en cada llamada, entre un modelo
especializado (Sonnet 5.5) y uno que gaste menos créditos (Haiku 5.5).

Precios por millón de tokens (entrada / salida, 2026-10): Opus 5.5 4 / 20; Sonnet 5.5 2 / 10; Haiku 5.5 0,10 / 0,50
hasta 100 mil tokens de entrada y 0,50 / 2,50 por encima. Cada llamada con el libro y el artículo pasa de 100 mil
tokens, así que Haiku cuesta unas 4 veces menos que Sonnet, no 20.

Lo que se sabe por F0 (ADR 0002): Sonnet como extractor tuvo 21 de 22 campos críticos en Singh. Clasificó mal Tipo
de felicidad real, una categoría en un artículo con SEM latente. Haiku no se ha medido en ningún rol.

## Prioridad

La regla central manda sobre el costo:

1. **Evidencia comprobable.** Los roles que producen o verifican la evidencia no bajan de nivel.
2. **Campos críticos** (sección 8.2). Se deciden con el modelo especializado.
3. **Costo.** El modelo ligero se usa solo donde un error se detecta después: el anclaje, el validador o la
   comparación con el extractor.

## Decisión

El portero está en `extraccion/dominio/portero.py`. Usa reglas fijas sobre el documento y el campo, no llama al
modelo y por eso no gasta créditos. El puerto `ModeloDeLenguaje.completar` recibe `nivel` (`especializado` o
`ligero`), y el adaptador lo traduce con `MODELO_ESPECIALIZADO` y `MODELO_LIGERO`. `ClaudeCli` rechaza cualquier
modelo Opus.

| Rol | Nivel | Por qué |
| --- | --- | --- |
| Extractor | Siempre especializado (Sonnet) | Escribe las 54 columnas con su evidencia; es el único rol que ya dio un error crítico con Sonnet |
| Auditor de evidencia | Siempre especializado (Sonnet) | Es quien protege la regla central: detecta un valor equivocado con una cita correcta, cosa que el anclaje no ve |
| Codificador ciego | Ligero (Haiku), salvo señales de complejidad → Sonnet | Su error no entra en la matriz: aparece como diferencia y va al conciliador. Con Haiku es además un modelo distinto del extractor, lo que hace la segunda codificación más independiente (ADR 0002) |
| Conciliador | Sonnet en campos críticos y en el número de filas; Haiku en los demás | Su cambio solo se aplica si su cita se ancla y el validador lo acepta (ADR 0004, decisión 6) |

**Señales de complejidad del codificador ciego** (cualquiera lleva a Sonnet; son provisionales):

- tablas o figuras en imagen;
- más de 300 000 caracteres de texto etiquetado;
- más de 4 tablas;
- términos de SEM latente, multinivel, mediación o moderación, varios estudios o muestras, o diseño longitudinal.

**Escalado.** Si una respuesta de Haiku no trae el JSON pedido, la misma llamada se repite con Sonnet. Si el
codificador ciego en Haiku da un acuerdo con el extractor menor que `UMBRAL_ACUERDO` (0,80), el ciego se repite con
Sonnet y cuenta esa codificación: un acuerdo bajo puede ser error de Haiku y no del extractor. Así se pierde la
independencia de modelo en ese artículo, pero no se manda al conciliador ni al responsable del dominio un falso
desacuerdo.

El uso de cada llamada guarda el modelo y el motivo del portero; `uso_tokens[rol].modelos` cuenta las llamadas de cada modelo.

## Consecuencias

- Costo estimado por artículo: unos 1,2 USD equivalentes, frente a 2,64 con Opus. Es una cuenta hecha con los tokens
  de F0 y hay que medirla.
- Si Haiku se equivoca más, el escalado por acuerdo bajo lo corrige al costo de una segunda llamada del ciego. En
  los pilotos hay que contar cuántos artículos escalan (`uso_tokens.ciego.modelos`): si son la mayoría, conviene
  dejar el ciego siempre en Sonnet, porque pagar Haiku y luego Sonnet sale más caro que Sonnet solo.
- `herramientas/f0_extraccion.py` no cambia: es el registro de F0.
- Las grabaciones de `ModeloGrabado` no cambian: el nivel no entra en la huella.

## Pendiente

- Medir en los 5 pilotos de F2 el acuerdo, las citas verificadas y el costo por rol, y ajustar los umbrales.
- Que el responsable del dominio confirme la tabla de roles.

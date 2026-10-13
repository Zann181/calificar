# ADR 0006 · Restablecer artículos en Error

- Estado: **Propuesto**. Lo pidió el responsable del dominio el 2026-10-12.
- Fecha: 2026-10-12
- Se aparta de: sección 5.1, que solo prevé `ERROR → estado del paso que falló (reintento)`.

## Contexto

El reintento de la sección 5.1 deja el artículo en el paso que falló (por ejemplo EXTRAYENDO). Si nadie retoma el
trabajo, el artículo queda en un estado intermedio que no corresponde a nada en curso. «Retomar» (`POST
/extracciones/retomar`) sí relanza la extracción, pero gasta créditos. El responsable del dominio pidió un reset que
limpie los errores y deje los artículos listos para seguir el trabajo.

## Decisión

`Articulo.restablecer()`: ERROR → el estado desde el que se pidió el trabajo, sin lanzar nada.

- Sin documento estructurado (falló la conversión) → NUEVO.
- Con documento y `estado_anterior` HEREDADO, POR_REVISAR o APROBADO → ese estado. Sus filas siguen en Matriz,
  porque una extracción fallida no escribe nada (sección 8.3, paso 3).
- En los demás casos → LISTO.
- Se borra el detalle del error del artículo. El intento fallido queda en `extraccion_extracciones`.

`POST /articulos/restablecer` recibe `{"articulos": [...]}`, o `null` para todos los que están en Error. En la
interfaz es el botón «Restablecer errores (N)» del panel de artículos, con confirmación.

## Consecuencias

- El 2026-10-12 se restablecieron los 3 artículos en Error de la base de trabajo (Villajos, Boivin, Wright y Staw):
  quedaron en LISTO. La copia previa de la base está en `datos/extractor.antes-de-restablecer-*.db`.
- Un artículo detenido en AUDITANDO o CONVIRTIENDO sin trabajo en curso no está en Error: el reset no lo toca.

## Continuar detenidos (botón aparte)

Un artículo **detenido** está en CONVIRTIENDO, EN_COLA, EXTRAYENDO o AUDITANDO sin trabajo activo en el ejecutor;
por ejemplo, porque la aplicación se cerró a mitad del trabajo. No está en Error, así que «Restablecer» no lo toca.
El responsable del dominio pidió que estos terminen, sin restablecerlos y con un botón propio.

`POST /extracciones/continuar` (botón «Continuar detenidos (N)», con confirmación):

- **Conversión cortada:** MinerU la termina en segundo plano, con el mismo candado que las demás conversiones, y
  el artículo queda Convertido. No gasta créditos.
- **Extracción cortada:**
  - el intento colgado se cierra como interrumpido y el artículo pasa a Error con el paso que falló;
  - la extracción se vuelve a encolar con los datos del equipo de su último intento, desde el principio, porque
    una llamada al modelo no se puede retomar a medias;
  - gasta créditos y respeta `TOPE_TOKENS_MENSUAL`.

`GET /extracciones/avance` devuelve `detenidos`, y la interfaz marca esos artículos con «· detenido».

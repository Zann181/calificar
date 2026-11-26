# ADR 0012 · La pestaña «Buscar» en la nube: se busca allí y lo encontrado vuelve al equipo

- Estado: **Aceptado** (responsable del dominio, 2026-11-25: pidió «deberia de estar integrado en la nube» y «deberia
  funcionar el buscador aqui»; ante las opciones, eligió **«Buscar desde la web»**)
- Fecha: 2026-11-25
- Modifica: ADR 0011, punto 10 («Solo local») y ADR 0009 (la nube deja de ser de solo lectura **solo para buscar**)

## Contexto

La pestaña «Buscar» (ADR 0011) se construyó solo para el equipo local. La nube (ADR 0009) es una réplica de solo lectura:
el equipo es el único que escribe y, en cada pasada, borra de la nube lo que él ya no tiene. Buscar desde la web exige que
la nube escriba, y esa regla de borrado destruiría lo escrito allí.

## Decisión

1. **Desde la web se puede** iniciar y cancelar una búsqueda y reactivar una fuente apagada. Exige sesión de un lector
   permitido y que el pedido venga de la propia página (403 si el navegador declara otro origen). El token del agente no
   sirve para esto.
2. **Todo lo demás sigue de solo lectura** (405): priorizar, descartar, reactivar candidatos, analizar texto, importar,
   perfiles de columnas y, por supuesto, la matriz. La vista previa y la exportación CSV/RIS se piden por `POST` pero no
   escriben nada.
3. **Una búsqueda a la vez** por proyecto en la web (el servidor gratuito es pequeño y hay varios lectores).
4. **Dueño de cada búsqueda** (columna `origen`, migración 0012). `nube`: lanzada en la web y sin recoger. No entra en
   el manifiesto, así que el equipo **no puede borrarla**. La web no modifica los candidatos que ya trajo el equipo.
5. **Buzón** (`GET /api/v1/sync/pendientes`, token del agente): antes de enviar, el equipo recibe las búsquedas web
   terminadas y las desduplica contra lo suyo con las mismas reglas de siempre (mismo identificador, DOI o título casi
   igual). Es repetible. Al enviarlas, la nube quita lo que solo existía por ellas y deja la versión del equipo.
6. **Réplica de ida** (equipo → nube), con tres tipos de sobre nuevos: `busqueda` (terminadas), `candidato` (con sus
   hallazgos y, si se leyó su texto, el análisis: frases cortas con su página, nunca el texto ni el PDF) y `perfil`.
   El formato pasa a **`esquema: 2`**: una nube sin actualizar responde 426.
7. «Qué se sube» gana la casilla **«Búsquedas de “Buscar”»**, activada. Apagada: ni se envían ni se recogen; no borra
   nada en ningún lado.
8. Una búsqueda que quedó «en curso» porque se cerró la aplicación o se reinició el servidor se cierra **con errores** al
   arrancar; conserva lo encontrado.
9. La web usa solo las fuentes abiertas. **Ninguna credencial institucional ni sesión** sale del equipo. El correo de
   contacto no viaja: la nube solo lo usa si alguien pone `CONTACTO_API` en sus variables.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Solo consultar en la web lo buscado en el equipo | El responsable quiere buscar allí |
| Que la web solo encargue la búsqueda y la corra el equipo | No funciona con el equipo apagado |
| Lo buscado en la web se queda en la web | No se podría importar ni analizar, que ocurre en el equipo |
| Sincronización general en los dos sentidos | Exige resolver conflictos en todo (matriz incluida), lo que el ADR 0009 evita. Aquí lo nuevo de la web solo **se añade** al equipo |
| Abrir todos los `POST` de la pestaña | Una ruta nueva quedaría abierta por descuido; la lista explícita falla cerrada |

## Consecuencias

- Lo buscado en la web aparece en el equipo en la siguiente pasada: al abrir la aplicación, cada 10 minutos o con
  «Sincronizar ahora». Hasta entonces la web lo rotula «aún no llega al equipo».
- La nube y el equipo deben tener la misma versión: Render despliega solo al subir a `main`; el equipo se actualiza al
  abrir la aplicación.
- Sin correo de contacto ni llave de OpenAlex, las fuentes pueden limitar antes a la nube que al equipo (comparte
  dirección con otros usuarios de Render). Cualquier fallo queda marcado en la búsqueda, como siempre.
- El plan gratuito se duerme sin tráfico y reinicia sin aviso: una búsqueda larga puede quedar cortada (punto 8).
- El tiempo de buscar y de ordenar muchos candidatos en el servidor gratuito **no está medido**.
- La pestaña sigue sin usar IA (ADR 0011, punto 2) y nada de ella escribe en la matriz.

# ADR 0013 · «Buscar» solo trae artículos que entregan su PDF gratis y legalmente

- Estado: **Aceptado** (responsable del dominio, 2026-11-25: «el buscador debe buscar solo sitios que entregen el articulo
  en formato pdf y que sea gratis y legal»)
- Fecha: 2026-11-25
- Modifica: ADR 0011, punto 8 (filtros de la búsqueda)
- Se apoya en: ADR 0011 (sin evasión, `robots.txt` firme), ADR 0012 (también se busca en la web)

## Contexto

Hasta ahora entraba cualquier registro que cumpliera la cadena y los filtros, tuviera o no texto accesible. En una muestra
de 17 enlaces de PDF «abierto» declarados por las fuentes (2026-11-25), cerca de la mitad **no entregaba el archivo**:
Europe PMC respondía 403 en los cuatro probados, dos de cuatro de Redalyc 404 y dos de cinco de OpenAlex 403. Declarar no
basta: hay que comprobar.

## Decisión

1. Un resultado **solo entra** si uno de sus enlaces de PDF gratuito se comprueba: se piden sus primeros 8 bytes y tienen
   que ser `%PDF`. No se descarga el artículo. Se prueban hasta 3 enlaces por resultado.
2. Qué enlaces cuentan como gratuitos y legales:
   - **OpenAlex:** `pdf_url` de ubicaciones de acceso abierto (y la consulta ya pide `open_access.is_oa`);
   - **Europe PMC:** enlaces PDF con disponibilidad abierta o gratuita (los de otros sitios antes que los propios);
   - **Crossref:** enlaces PDF **solo** si el trabajo tiene licencia Creative Commons ya vigente;
   - **Redalyc:** la dirección del PDF de la revista (acceso abierto).
3. La comprobación respeta `robots.txt`, no usa credenciales ni toca los sitios que las exigen, y deja de preguntar a un
   servidor que rechaza tres veces seguidas (401, 403, 429). **No se evade** ningún bloqueo.
4. Hasta 8 servidores a la vez; a cada uno, de uno en uno y con la pausa de siempre.
5. Lo descartado se **cuenta por fuente** en cada búsqueda («N sin PDF gratis»), para el flujo PRISMA.
6. El enlace comprobado se guarda (`url_pdf`, migración 0013) y es el que se ofrece, se exporta y se usa al importar o
   analizar.
7. La lista **oculta** los candidatos sin PDF comprobado que sigan «nuevos» (los de antes de esta decisión) y dice
   cuántos son; vuelven al repetir una búsqueda que los compruebe. Los priorizados, descartados o importados se siguen
   viendo: son decisiones de la persona. No se borra nada.
8. El formato de réplica pasa a **`esquema: 3`**.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Fiarse del enlace que declara la fuente | La muestra: cerca de la mitad no entregaba el PDF |
| Descargar cada PDF completo al buscar | Cientos de archivos por búsqueda, sin que la persona los haya elegido (ADR 0011) |
| Simular un navegador para que Europe PMC u otros entreguen | Es evasión; excluida |
| Sitios piratas | Ilegales |
| Mostrar todo con un filtro opcional «solo PDF» | El responsable pidió que sea la regla |

## Consecuencias

- **Sesgo de la revisión (hay que declararlo):** una búsqueda que solo admite texto gratuito **no es exhaustiva**. Quedan
  fuera artículos de suscripción —también los accesibles por las Bibliotecas UNAL— y los de sitios que niegan el PDF a
  programas aunque sean abiertos. Para la revisión sistemática, el número descartado por esta razón queda en cada
  búsqueda, y conviene complementar con las bases de la Biblioteca (exportaciones propias) y declarar el criterio.
- **Europe PMC casi no aporta:** en la prueba del 2026-11-25, 1 de 50 resultados entregó PDF (OpenAlex 33 de 50, Crossref
  9 de 26 evaluados, Redalyc 7 de 7).
- La búsqueda tarda más: la misma prueba, con 50 por fuente, tomó unos 2 minutos en el equipo. En el servidor gratuito de
  la nube **no está medido**; los sitios pueden además rechazar más desde allí.
- Un enlace puede dejar de funcionar después de comprobado; importar y analizar vuelven a validarlo.

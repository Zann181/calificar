# ADR 0011 · Descubrimiento de literatura: pestaña «Buscar», sin IA, con límites explícitos al acceso automatizado

- Estado: **Aceptado** (responsable del dominio, 2026-11-25, al responder las preguntas del plan: credenciales a cargo del
  usuario, límites aceptados, errores marcados, sin IA, años 2020 en adelante)
- Fecha: 2026-11-25
- Plan de ejecución: `docs/PLAN_BUSQUEDA_ARTICULOS.md`
- Se apoya en: regla de ubicación comprobable (CLAUDE.md), ADR 0002 (el modelo solo se usa por la CLI de Claude y no aquí),
  ADR 0009 (la nube es de solo lectura), ADR 0010 (país por afiliación)

## Contexto

El responsable quiere una pestaña para **encontrar artículos que contengan los datos de la matriz**, en fuentes gratuitas y
en las bases con suscripción de las Bibliotecas UNAL, elegir cuáles columnas le importan (y con qué prioridad), ver una
vista previa de cómo encaja cada candidato y llevar los elegidos al flujo de extracción existente, **sin gastar tokens**.

Observado el 2026-11-25 en el sitio público de la Biblioteca (sin iniciar sesión): el buscador Aluna es Ex Libris Primo VE;
hay 181 recursos electrónicos (entre ellos Scopus, Web of Science, ScienceDirect, Wiley, Springer-Nature Link, Sage,
Taylor & Francis, Emerald y colecciones EBSCO); el acceso pasa por un proxy `*.unalproxy.elogim.com` con entrada por Google
(`@unal.edu.co`) o por usuario y contraseña; el proxy **restringe 8 horas** a quien descargue más de 250 MB en 15 minutos
y 15 minutos a quien falle 5 inicios de sesión en 5 minutos.

## Decisión

1. **La pestaña nunca escribe en la matriz.** Lo que sale de un buscador (metadato o frase de un resumen) es un
   **indicio** con origen visible y rótulo «sin verificar». Solo el PDF, con página, bloque y cita literal, produce valores
   verificados. Importar un candidato entrega el PDF a `CargarPDF`; no lanza ninguna extracción.
2. **Sin IA.** Ningún caso de uso ni adaptador del contexto `descubrimiento` llama a un modelo. Todo es determinista (APIs,
   patrones, `pymupdf`). Una prueba lo impide.
3. **Columnas a elección y con prioridad** (imprescindible / importante / deseable), clasificadas por **detectabilidad**
   (M metadato, R resumen, T texto completo). Una columna T que la etapa A no puede juzgar es «pendiente de PDF», **no**
   «ausente».
4. **Scraping cortés, no sigiloso.** Orden de preferencia: API → OAI-PMH/RSS → HTML con `robots.txt` → navegador → sesión
   del usuario. **Excluido:** rotación de IP, suplantación de huella, «stealth», resolver CAPTCHA, reintentar inicios de
   sesión. Ante un reto, 403/429 repetidos o «tráfico inusual», el programa se detiene y lo dice.
5. **Credenciales de la UNAL: las escribe siempre el usuario.** El programa no las pide, no las guarda y no las repite. Lo
   único que puede conservar es la cookie de sesión del proxy, en el Administrador de credenciales de Windows, con botón
   para borrarla. El mecanismo de captura se valida en la compuerta 0.4; si no pasa, se trabaja con exportaciones
   (RIS/BibTeX/CSV) que baja el usuario.
6. **Presupuesto por el proxy:** ≤ 100 MB por ventana móvil de 15 minutos (40 % del límite publicado), un solo hilo, pausa
   ≥ 8 s, una descarga por decisión del usuario sobre un candidato seleccionado, nada de «bajar todo».
7. **Errores marcados:** todo fallo se registra como `ERROR` con origen `descubrimiento` en el registro existente (sin
   secretos), con insignia por fuente y contador global.
8. **Filtros por defecto:** 2020 hasta la fecha de la búsqueda; idiomas EN/ES/PT; artículos y preprints (marcados);
   revisiones marcadas «No aplica». Cadena inicial y regla de `Cita` en el plan, sección 11.
9. **Correo de contacto:** solo en `CONTACTO_API` del `.env` local y solo hacia fuentes abiertas que lo piden; nunca a la
   Biblioteca ni a editoriales; nunca en el repositorio.
10. **Solo local.** En `MODO=nube` la pestaña se oculta y sus rutas devuelven 405; los candidatos no se replican.
    *Modificado por el ADR 0012: en la nube también se busca, y las búsquedas van y vuelven entre la nube y el equipo.*

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Rellenar la matriz con los metadatos | Rompe la regla de ubicación comprobable |
| Cribado de candidatos con un modelo | El responsable pidió cero tokens; la clasificación determinista alcanza para ordenar y el PDF decide después |
| Iniciar sesión con Google dentro de un navegador controlado por automatización | Google lo rechaza; empujaría a técnicas de evasión excluidas |
| Guardar usuario y contraseña de la UNAL | El programa no debe poder filtrarlas; el usuario las escribe |
| Descarga masiva por el proxy | Riesgo de 8 horas de bloqueo (de la cuenta del usuario) y de violar licencias |
| Google Scholar | Sus términos prohíben el acceso automatizado |
| Leer SciELO (`search.scielo.org`) y Dialnet (`/buscar/`) | Sus `robots.txt` lo prohíben a los agentes automatizados (verificado el 2026-11-25). Se respeta y **no se busca otra forma de entrar**; sus artículos con DOI llegan por OpenAlex y Crossref |

## Consecuencias

- **`robots.txt` es una regla firme** para cualquier fuente que se lea como página o servicio sin API documentada: se lee antes,
  se respeta (con lector propio de comodines) y, si no se puede leer, se detiene. Una fuente de ese tipo (hoy, Redalyc) se
  **desactiva sola** tras tres fallos de estructura seguidos y se reactiva a mano. El canario manual
  (`herramientas/canario_fuentes.py`) detecta cuándo un sitio cambió.
- Nueva fase de **compuertas** antes de tocar credenciales: condiciones de uso de las editoriales, respuesta de la
  Biblioteca sobre minería de texto, y prueba de la cookie del proxy con `httpx` (plan, Fase 0).
- Puede que la Biblioteca o una editorial prohíba la descarga automatizada: entonces solo se usan sus exportaciones y la
  subida manual del PDF (ya existe en `POST /articulos`).
- Hay una laguna de cobertura conocida: PsycINFO/PsycArticles no figuran por nombre en la Biblioteca; se compensa con la
  colección EBSCO de psicología, Scopus, Web of Science y las fuentes abiertas, y el historial de búsquedas documenta qué
  se cubrió.
- La clasificación M/R/T se versiona en `recursos/detectabilidad_columnas.json` y una prueba la ata al libro de códigos.
- Nueva dependencia opcional (`playwright`, solo nivel 4); las demás ya están en el proyecto.

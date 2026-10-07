# ADR 0004 · Motor de extracción y anclaje (F2)

- Estado: **Propuesto**. Pendiente de revisión del responsable del dominio.
- Fecha: 2026-10-06
- Se aparta de: sección 6 (firma de `ModeloDeLenguaje`), sección 7, paso 1 de H1 y H3 en el ADR 0001 ("llevarlo a
  `normalizar()`"), y sección 8.3, paso 1 (reserva de Estudio).

## Contexto

F2 lleva al contexto Extracción lo que en F0 hacía el arnés `herramientas/f0_extraccion.py`: el texto etiquetado,
los cuatro roles, el ciclo con el validador, el anclaje y el comando `python -m app.cli extraer`. Durante la
construcción hubo que decidir lo siguiente.

## Decisiones

1. **Capa de texto del PDF al armar el texto etiquetado, no en `normalizar()`** (H1, H3). `normalizar()` recibe
   solo la salida de MinerU, no el PDF. El caso de uso pide al puerto `LectorPdf` el texto de los bloques vacíos o
   con LaTeX y lo usa en el texto etiquetado. El documento estructurado guardado no cambia. Con esto, el texto
   etiquetado de Kumar es idéntico al de F0.
2. **El anclaje busca en dos textos por bloque**: el que vio el modelo (capa del PDF y sin escapes, H9) y el de
   MinerU. Una cita copiada del texto etiquetado se encuentra siempre en el mismo texto que la produjo.
3. **`ModeloDeLenguaje.completar(rol, sistema, mensaje, imagenes)`**. Un mensaje de sistema y uno de usuario, con
   las páginas en PNG. El modelo de cada rol lo fija el adaptador con la configuración (ADR 0002).
4. **Número de Estudio.** Se usa el siguiente libre del proyecto (`matriz_secuencias` y el mayor Estudio
   existente), o el que indique el equipo con `--estudio`. La reserva atómica con bloqueo queda para F3, que
   necesita PostgreSQL (ADR 0003).
5. **`Documento`, `Covidence #` y la vía de identificación los indica el equipo** en cada extracción
   (`--documento`, `--covidence`, `--via`). El artículo cargado no los conoce.
6. **El conciliador solo cambia un valor si su cita se ancla** (nivel distinto de NO_VERIFICABLE). La salida
   corregida se vuelve a validar. Si el validador la rechaza, se conserva la salida anterior y el cambio queda como
   hallazgo PENDIENTE. Nunca abre ni cierra filas: el número de filas siempre queda para el responsable del dominio.
7. **Diferencias con el codificador ciego.** Se registran como hallazgos REFUTADO del CODIFICADOR_CIEGO, con la
   evidencia del ciego. El acuerdo final se calcula con la salida después de conciliar.
8. **`ModeloGrabado`.** Busca primero por la huella de la llamada y, si no la encuentra, usa la respuesta por rol.
   Así las pruebas doradas no se rompen cada vez que se ajusta el texto de las instrucciones. `Grabadora` crea
   grabaciones por huella a partir de llamadas reales.
9. **PyMuPDF pasa a ser dependencia de producción** (antes solo de desarrollo). **Licencia AGPL-3.0**: si el
   programa se ofrece como servicio en red (etapa 2), hay que revisar la obligación de publicar el código o comprar
   la licencia comercial. La alternativa es `pdftotext -bbox` (poppler, GPL), que ya usa el validador, más
   `pdftoppm` para las imágenes.
10. **`subprocess` y `pymupdf` quedan prohibidos en `dominio/` y `aplicacion/`** (import-linter), como pide la
    consecuencia 6 del ADR 0002.

## Pruebas doradas (sección 8.5)

Se usan las respuestas Opus de F0 como grabación, porque `ejemplo_verificado.salida` no trae `bloque_id`.

- **Kumar:** 0 errores del validador en la primera iteración, 22 de 22 campos críticos iguales al ejemplo
  verificado, y las 39 citas que no son de tabla ni de figura en VERIFICADA (el ejemplo verificado tiene 32). La
  fila llega a Matriz en POR_REVISAR, el artículo pasa a POR_REVISAR y la exportación lleva la hoja Auditoria con el
  hallazgo pendiente de la fila de satisfacción laboral.
- **Singh:** Incluir en meta análisi = SEM latente por la condición 9; confianza Baja; discrepancia registrada en
  Beta Fel 1- JP.

## Pendiente para cerrar F2

- Aceptación: **95 % o más de citas verificadas en 5 artículos piloto** que elija el responsable del dominio. Esto
  requiere corridas reales: unos 2,6 USD equivalentes y 4 minutos por artículo.
- H2: el rango resaltado sigue siendo el rectángulo del bloque. Usar las líneas de `middle.json` queda para F4,
  cuando el visor lo necesite.
- H7: el validador sigue comparando contra `pdftotext`. Cambiarlo requiere aprobar una modificación a
  `validar_extraccion.py`.

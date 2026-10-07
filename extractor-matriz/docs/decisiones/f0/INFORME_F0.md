# Informe de cierre de F0 · Prueba técnica

Fecha: 2026-10-05

## Tareas de la sección 12

| Tarea | Estado | Evidencia |
| --- | --- | --- |
| Levantar servicio-mineru y convertir Kumar y Singh | Hecha | `recursos/fixtures/mineru/*.zip` (salida determinista: dos corridas dan el mismo resultado) |
| Dibujar 20 rectángulos de bloque | Hecha | `docs/decisiones/0001/*.png`, `bloques.md`, más la verificación automática de los 213 bloques (`verificacion.csv`) |
| Escribir el ADR 0001 (coordenadas) | Escrito, **falta la firma** | `docs/decisiones/0001-coordenadas-mineru.md` |
| Medir el tiempo por página en CPU (y en GPU, si hay) | Hecha en CPU; no hay GPU | `docs/decisiones/0001/tiempos.csv`: de 11 a 21 s por página |
| Extracción completa de Kumar con los cuatro roles, con tokens y costo | Hecha | `f0/extraccion/kumar_2022__claude-opus-5-5/`: 2,64 USD, unos 4 minutos |
| Comparar dos modelos para el rol extractor en Kumar y Singh | Hecha | ADR 0002: Opus 22/22 y Sonnet 21/22 en Singh |

**Aceptación:** las mediciones de tiempo y costo están registradas. Falta la firma del responsable del dominio en el
ADR 0001 (revisión visual de los 20 rectángulos).

## Decisiones tomadas en F0

- ADR 0002: modelo de lenguaje por medio de la Claude Code CLI.
- El libro v2.1 prevalece sobre las instrucciones anteriores del 2026-09-29 (decisión del responsable, 2026-10-05).
- Libro v2.2: `bloque_id` en cada evidencia (hallazgo H5, decisión del responsable, 2026-10-05).

## Pendientes para el responsable del dominio

1. Firmar el ADR 0001.
2. Elegir el modelo de cada rol. La recomendación está en el ADR 0002.
3. **Kumar: ¿una fila o dos?** El libro clasifica la satisfacción laboral como indicador de felicidad y dice que se
   abre una fila nueva cuando cambia el indicador. Kumar trae JS–JP r = .71 (Tabla 1) y β = .127 (Figura 5). El
   auditor marcó que falta esa fila (REFUTADO) y el conciliador la dejó PENDIENTE. La matriz actual y el ejemplo
   verificado tienen una sola fila (SWB–JP). Si la satisfacción laboral que funciona como predictor también abre fila,
   el ejemplo verificado está incompleto. Si no, el libro tiene que decirlo en `regla_para_abrir_una_fila_nueva`.
4. Confirmar las 9 `decisiones_provisionales_para_confirmar_por_el_equipo` del libro antes de extraer en masa.
5. Erratas del libro, para una versión 2.3 si se aprueban:
   - el paso 7 del flujo menciona `tipo_de_beta`, que ya no existe (ahora son `tipo_de_efecto` y `tecnica_del_beta`);
   - `motivo_decision_inclusion` dice "1 a 6", pero el árbol tiene 11 condiciones.
6. H7: aprobar que el validador compare contra el mismo texto que usa el anclaje (requiere cambiar
   `validar_extraccion.py`).

## Entra en F2 (motor de extracción y anclaje)

- Llevar a `normalizar()` lo que el arnés de F0 ya resuelve:
  - texto de la capa del PDF en bloques vacíos o con LaTeX (H1 y H3);
  - leyendas y notas de tabla completas;
  - quitar los escapes de Markdown (H9).
- Adaptador del validador con UTF-8 (H4, `herramientas/validar_utf8.py`).
- Conciliador con la sección del libro que corresponde a cada campo (H10).
- Probar en los 5 pilotos que elija el responsable: Kumar no sirve para medir calidad, porque es el ejemplo verificado.

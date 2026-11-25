# Auditoría de las 5 columnas nuevas (libro v2.3)

Fecha: 2026-11-21. Base: la app abierta del usuario (`datos/extractor.db`, 79 filas extraídas, 39 artículos). Fuente: **solo el texto que ya extrajo MinerU** (ningún PDF se volvió a leer). Auditores: 15 subagentes de Claude; el resultado son **propuestas**, no cambios: no se escribió nada en la app.

## 1. Qué se auditó y cómo

- **Coherencia de las 5 columnas en las 79 filas** (por código, sin IA): `ID muestra`, `Método obtención r`, `Cultura Hofstede` y `Conjunto MA` coinciden con su fuente (trazabilidad, `Pais` y condición del árbol). Hallazgos: ver sección 2.
- **Lectura del texto de MinerU** para `Método obtención r` y `Constructo desempeño` (79 filas: 78 en esta ronda y Kumar en la anterior). Las 156 citas de esta ronda se comprobaron por código como subcadenas literales del texto (0 fallos).

## 2. Hallazgos de coherencia

- **`ID muestra` junta artículos distintos.** `D1-M1` reúne Kumar, Oswald, Santoso, Psychological Well-Being y derkinderen; `D47-M1` reúne Singh e Ilker Met. Causa: números de Documento repetidos (los asigna el equipo). Hay que corregir el Documento de esos artículos.
- **`Cultura Hofstede`:** Sri Lanka (Santoso, fila 144) no está en la tabla IDV; la fila 145 no tiene país. Ambas quedan «No indica».
- `Método obtención r` y `Conjunto MA`: sin incoherencias.

## 3. Decisiones tuyas: `Método obtención r` (de 79 filas, 73 correctas)

| Estudio | Artículo | Hoy | El auditor propone | Veredicto | Efecto |
|---|---|---|---|---|---|
| 1 | Kumar 2022 | Correlación entre compuestos PLS | mantener (duda) | DUDOSO | Si fuera Pearson observado: `Incluir` PLS→SI, `Conjunto MA` Excluir→Principal_Hedonico |
| 94 | 19 jianghua wu | No disponible | Pearson observado | DUDOSO | Si se asigna Pearson observado y se transcribe la r (SWB-JP = 0.739, fila 4 columna 3 de la Tabla II, pendiente de confirmar), Incluir pasa de No (cond. 11) a SI (cond. 6 |
| 129 | 36 magnier watanabe 2020 organizational  | No disponible | No disponible | DUDOSO | Si se mantiene No disponible, no cambia nada: Incluir queda SEM latente (cond. 9) y Conjunto MA Sensibilidad. Si el libro permitiera tomar r de las matrices de las Tablas |
| 4 | 3 bibi 2022 1 | Pearson observado | Correlación entre variables latentes CB-SEM | DUDOSO | Si es latente CB-SEM: se cae la cond. 6; r_imputado_desde_beta es null (y la beta 0.514 esta fuera de +-0.50), asi que no aplica cond. 7; cond. 9 da Incluir = SEM latente |
| 5 | 3 bibi 2022 1 | Pearson observado | Correlación entre variables latentes CB-SEM | DUDOSO | Igual que la fila 4: si es latente CB-SEM, cond. 6 no aplica, r_imputado_desde_beta es null y la beta 0.766 esta fuera de +-0.50 (no cond. 7); cond. 9 da Incluir = SEM la |
| 77 | 6 salas vallina 2020 | Correlación entre variables latentes CB-SEM | Pearson observado | INCORRECTO | Incluir pasaría de «SEM latente» (cond. 9) a «SI» (cond. 6: Correlación Feli 1 - JP con Pearson observado); Conjunto MA pasaría de Sensibilidad a Principal_Hedonico/Eudai |

Nota: el estudio 4 y 5 (Bibi) y los demás casos dependen de si la tabla de correlaciones es de puntajes observados o de variables latentes; el texto no siempre lo dice. La regla 1 del libro (tabla de descriptivos con correlaciones → Pearson observado aunque el modelo sea SEM) decide varios, pero requiere tu criterio cuando la tabla se titula «factor correlations» o trae raíz de AVE.

## 4. `Constructo desempeño` propuesto (hoy vacío en las 79 filas)

Todas las propuestas son compatibles con `Desempeño` según la tabla del libro. Confianza: Alta 33, Media 36, Baja 9 (+ Kumar: In-Role Behavior). Las de confianza Baja necesitan revisión humana.

| Estudio | Artículo | Desempeño | Constructo propuesto | Confianza |
|---|---|---|---|---|
| 1 | Kumar 2022 | In-rol | In-Role Behavior | Media |
| 4 | 3 bibi 2022 1 | Innovador | Innovation | Media |
| 5 | 3 bibi 2022 1 | Innovador | Innovation | Media |
| 6 | 4 ayala 2017 | Innovador | Innovation | Alta |
| 71 | singh 2023 | Extra-rol | Contextual Performance | Baja |
| 72 | 5 kozusznik 2019 | Extra-rol | Contextual Performance | Media |
| 73 | 5 kozusznik 2019 | Extra-rol | Contextual Performance | Media |
| 74 | 5 kozusznik 2019 | Extra-rol | Contextual Performance | Media |
| 75 | 2 sattar | In-rol | In-Role Behavior | Media |
| 76 | 2 sattar | Extra-rol | Contextual Performance | Media |
| 77 | 6 salas vallina 2020 | In-rol | Sales | Alta |
| 78 | 10 darvishmotevali 2020 | In-rol | Job Proficiency | Baja |
| 79 | 7 coo 2018 | General | Job Performance Global | Alta |
| 80 | 7 coo 2018 | In-rol | In-Role Behavior | Media |
| 81 | 7 coo 2018 | Extra-rol | Helping | Media |
| 82 | 7 coo 2018 | General | Job Performance Global | Alta |
| 83 | 7 coo 2018 | In-rol | In-Role Behavior | Media |
| 84 | 7 coo 2018 | Extra-rol | Helping | Media |
| 85 | 8 villajos 2 | Innovador | Creativity | Alta |
| 86 | 9 dagenais desmarais2017 1 | Extra-rol | Contextual Performance | Alta |
| 87 | 9 dagenais desmarais2017 1 | Extra-rol | Contextual Performance | Alta |
| 88 | 9 dagenais desmarais2017 1 | Extra-rol | Contextual Performance | Alta |
| 89 | 9 dagenais desmarais2017 1 | Extra-rol | Contextual Performance | Alta |
| 90 | 11 boivin 2019 1 | In-rol | Task Performance | Alta |
| 91 | 11 boivin 2019 1 | In-rol | Task Performance | Alta |
| 92 | 11 boivin 2019 1 | In-rol | Task Performance | Alta |
| 93 | 18 john m zelenski | General | Job Performance Global | Media |
| 94 | 19 jianghua wu | General | Job Performance Global | Media |
| 95 | 18 john m zelenski | General | Job Performance Global | Media |
| 96 | 18 john m zelenski | General | Job Performance Global | Media |
| 97 | 18 john m zelenski | General | Job Performance Global | Media |
| 98 | 20 shanmugam | General | Job Performance Global | Baja |
| 99 | 21 kundi employee psychological 1 | In-rol | In-Role Behavior | Media |
| 100 | 21 kundi employee psychological 1 | In-rol | In-Role Behavior | Media |
| 101 | 23 peir from happiness orientations to w | General | Job Performance Global | Alta |
| 102 | 23 peir from happiness orientations to w | General | Job Performance Global | Alta |
| 103 | 23 peir from happiness orientations to w | General | Job Performance Global | Alta |
| 104 | 23 peir from happiness orientations to w | General | Job Performance Global | Alta |
| 105 | 25 salgado | General | Job Performance Global | Alta |
| 106 | 25 salgado | General | Job Performance Global | Alta |
| 107 | 25 salgado | General | Job Performance Global | Alta |
| 108 | 27 wright y cropanzano 2007 | General | Job Performance Global | Media |
| 109 | 27 wright y cropanzano 2007 | General | Job Performance Global | Media |
| 110 | 26 taris | Organizacional | Otro: Costos de personal por hora (indicador organizacional) | Media |
| 111 | 26 taris | Organizacional | Otro: Productividad organizacional (horas de servicio sobre horas pagadas) | Media |
| 112 | 26 taris | Organizacional | Otro: Eficiencia organizacional (DEA) | Media |
| 113 | 26 taris | Organizacional | Otro: Satisfaccion de clientes con el servicio de la organizacion | Alta |
| 114 | 26 taris | Organizacional | Otro: Costos de personal por hora (indicador organizacional) | Media |
| 115 | 26 taris | Organizacional | Otro: Productividad organizacional (horas de servicio sobre horas pagadas) | Media |
| 116 | 29 wright 2002 | General | Job Performance Global | Alta |
| 117 | 29 wright 2002 | General | Job Performance Global | Alta |
| 118 | 29 wright 2002 | General | Job Performance Global | Alta |
| 119 | 29 wright 2002 | General | Job Performance Global | Alta |
| 120 | 32 wang2019 | Organizacional | Otro: Desempeño social de la empresa | Alta |
| 121 | 32 wang2019 | Organizacional | Otro: Desempeño social de la empresa | Alta |
| 122 | 34 alahbabi 2021 | General | Job Performance Global | Media |
| 123 | 33 awada 2020 | General | Job Performance Global | Media |
| 124 | 33 awada 2020 | General | Job Performance Global | Media |
| 125 | 33 awada 2020 | General | Job Performance Global | Media |
| 126 | 33 awada 2020 | General | Job Performance Global | Media |
| 127 | 33 awada 2020 | General | Job Performance Global | Media |
| 128 | 33 awada 2020 | General | Job Performance Global | Media |
| 129 | 36 magnier watanabe 2020 organizational  | General | Job Performance Global | Alta |
| 130 | 37 chian fang | General | Job Performance Global | Baja |
| 131 | 38 chunyan li | Organizacional | Otro: Desempeño de la empresa (organizacional) | Alta |
| 132 | 39 sarfraz | In-rol | In-Role Behavior | Media |
| 133 | 41 soyalin | General | Job Performance Global | Baja |
| 134 | 43 bellet 2020 | In-rol | Sales | Alta |
| 135 | 42 al shami | Extra-rol | OCB-Organization | Baja |
| 136 | 44 cao zhao 2022 | General | Job Performance Global | Media |
| 137 | 46 kara y eti nel | General | Job Performance Global | Baja |
| 138 | 47 ilker met 2023 | In-rol | Sales | Media |
| 139 | psychological well being | Extra-rol | Contextual Performance | Media |
| 140 | oswald | In-rol | Productivity | Alta |
| 141 | oswald | In-rol | Productivity | Alta |
| 142 | oswald | In-rol | Productivity | Alta |
| 143 | vatsa | In-rol | Productivity | Alta |
| 144 | santoso | General | Job Performance Global | Baja |
| 145 | derkinderen 2020 eudaimon a en el trabaj | General | Job Performance Global | Baja |

## 5. Casos que la lista cerrada no cubre bien

- **Taris (6 filas), Li, Wang (2):** desempeño organizacional → «Otro: …». La lista de 13 valores no tiene uno para eso.
- **Psychological Well-Being:** usa el OCB total (OCBI + OCBO); no hay valor para eso.
- **Zelenski (4 filas):** el rótulo «Productivity» solo es compatible con In-rol, pero `Desempeño` es General.
- **Coo:** estudio controlado no aleatorizado codificado como longitudinal; como RCT daría Experimental y Excluir. Su Tabla 3 vino desordenada en MinerU.
- Filas que faltan: Kumar (satisfacción laboral → desempeño), Santoso (desempeño por el supervisor, r = 0.478), Awada (PS, r = .656).

## 6. Aplicado en la app (2026-11-21)

Se aplicaron por la API de la app, con autor y motivo en el historial de cada celda, las propuestas de `Constructo desempeño` de confianza Alta o Media: **70 de 79 filas**. Quedan **vacías las 9 de confianza Baja** (estudios 71, 78, 98, 130, 133, 135, 137, 144 y 145) para decisión humana. Cada celda aplicada queda como `CORREGIDA` con el motivo «propuesta del agente auditor (IA), pendiente de verificación humana», la cita y el bloque. Copia previa de la base: `datos/extractor.antes-constructo-20261121.db`.

## 7. Arreglos de congruencia (2026-11-22)

Ver la adenda del ADR 0008. Resumen: Documentos duplicados reasignados (48 a 52) y `ID muestra` corregido; ID provisional por país y población en las
heredadas (Documentos 28 y 36 con dos muestras); Sri Lanka en la tabla IDV; Salas-Vallina (Estudio 77) pasa a Pearson observado / `SI` / `Principal_Mixto`.
Tras los cambios, la auditoría automática de las 5 columnas sobre las 79 filas queda con un solo aviso (fila 145, sin país: «No indica» es correcto).
Copias previas: `datos/extractor.antes-documentos-20261122.db` y `datos/extractor.antes-metodo-20261122.db`.

# calificar

Herramientas para llenar y auditar la matriz de síntesis de una revisión sistemática sobre **felicidad y desempeño**
en el trabajo. A partir de los PDF de los artículos se extraen las 54 columnas de datos de la matriz, y cada dato
conserva su evidencia: página, bloque, rectángulo y cita literal. **Un dato sin ubicación comprobable no entra como
verificado.**

Responsable del dominio: Pablo Andrés Erazo Muñoz, PhD.

## Qué hay en este repositorio

| Ruta | Qué es |
| --- | --- |
| [`extractor-matriz/`](extractor-matriz/) | Aplicación principal: carga PDF, los convierte con MinerU, extrae las columnas con Claude Code CLI, permite revisar cada celda en un visor PDF y exporta a Excel |
| `Artículos revisión sistemática/` | Corpus de 48 PDF de la revisión (entrada de la aplicación) |
| `Constructor/` | Insumos originales del proyecto: especificación, libro de códigos v2, matriz base con notas, piloto Singh 2023 y validador |
| `insumos_constructor/`, `insumos_constructor.zip` | Copia empaquetada de los insumos anteriores |

El código vive solo en `extractor-matriz/`. Las demás carpetas son datos de entrada y material de referencia.

## Cómo funciona

```
PDF ──► MinerU (texto, bloques, coordenadas) ──► agentes sobre Claude Code CLI ──► matriz de 54 columnas
                                                                                        │
                      Excel (comentarios de fuente, Trazabilidad, Auditoria) ◄── revisión humana en visor PDF
```

1. **Carga**: los PDF se registran y los duplicados se rechazan por huella SHA-256.
2. **Conversión**: MinerU entrega texto, bloques y coordenadas de cada página.
3. **Extracción**: cuatro roles de agente, orquestados sobre Claude Code CLI, llenan cada columna siguiendo el libro de
   códigos, que es la norma (columnas, vocabularios y validaciones se derivan de él).
4. **Revisión**: cada celda abre el PDF en el lugar exacto y resalta la cita; se puede aprobar, corregir (con motivo)
   o rechazar, con historial.
5. **Exportación**: Excel con comentarios de fuente, colores y hojas `Trazabilidad` y `Auditoria`.

## Estado

| Fase | Alcance | Estado |
| --- | --- | --- |
| F0 | Pruebas técnicas: MinerU, coordenadas, extracción con Claude CLI | Cerrada |
| F1 | Biblioteca, matriz, importación/exportación, CLI, API, sin Docker | Cerrada |
| F2 en adelante | Extracción orquestada, revisión completa, PostgreSQL/Redis | Pendiente |

La interfaz (adelanto de F4) ya funciona sobre los datos de F1.

## Inicio rápido

Doble clic en **Extractor de matriz** (acceso directo del Escritorio). Arranca el servidor sin consola, abre la
aplicación en su propia ventana y apaga el servidor al cerrarla. Si el acceso directo no existe, créelo con:

```bash
extractor-matriz/servicio-mineru/.venv/Scripts/python extractor-matriz/herramientas/crear_icono_y_acceso.py
```

Para instalar desde cero (backend, base SQLite, importación de la matriz, conversión de PDF e interfaz), siga la sección
"Puesta en marcha sin Docker" de [`extractor-matriz/README.md`](extractor-matriz/README.md).

## Pila técnica

- **Backend**: Python 3.12, FastAPI, SQLite (PostgreSQL y Redis llegan en F3), Alembic; monolito modular con DDD.
- **Frontend**: React 18, TypeScript, Vite, AG Grid, pdfjs-dist.
- **Conversión**: servicio HTTP propio que envuelve MinerU (CPU, de 11 a 21 s por página).
- **Extracción**: Claude Code CLI, no la API.
- **Calidad**: ruff, mypy, import-linter, pytest y CI en GitHub Actions.

## Documentación

- Detalle de uso, estructura, calidad y reglas: [`extractor-matriz/README.md`](extractor-matriz/README.md)
- Especificación: [`extractor-matriz/docs/CONSTRUIR_extractor_matriz.md`](extractor-matriz/docs/CONSTRUIR_extractor_matriz.md)
- Decisiones de arquitectura:
  - [0001 · Coordenadas de MinerU](extractor-matriz/docs/decisiones/0001-coordenadas-mineru.md)
  - [0002 · Modelo de lenguaje por Claude CLI](extractor-matriz/docs/decisiones/0002-modelo-de-lenguaje-por-claude-cli.md)
  - [0003 · F1 sin Docker](extractor-matriz/docs/decisiones/0003-f1-sin-docker.md)

## Reglas del proyecto

- Lenguaje ubicuo en español: identificadores sin tildes, textos de interfaz con tildes.
- Un contexto no lee las tablas de otro; se comunican por casos de uso o eventos.
- Si algo contradice la especificación, se registra un ADR antes de seguir.

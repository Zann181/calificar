# Instalar MinerU (servicio-mineru) — guía para una IA o una persona

Objetivo: dejar un servicio HTTP en `http://127.0.0.1:8001` que convierta PDF en bloques con coordenadas. El
extractor lo necesita para pasar un artículo de **Nuevo** a **Listo**. Sin él, la cabecera de la aplicación muestra
MinerU en rojo ("No está instalado").

## Camino corto (un comando)

Desde la raíz del repositorio, en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File extractor-matriz\servicio-mineru\instalar.ps1
```

El script es repetible: cada paso se salta si ya está hecho, y si se corta (red, espacio) se vuelve a ejecutar y
continúa. Dura entre 10 y 30 minutos según la conexión. Termina con una conversión real de `kumar_2022.pdf`; si
imprime **`Instalación verificada`**, está listo. No hay que hacer nada más: el acceso directo del Extractor arranca
MinerU solo.

## Qué hace el script (por si hay que hacerlo a mano)

| Paso | Qué | Comprobación |
| --- | --- | --- |
| 1 | Busca Python **3.10 a 3.12** con el lanzador `py` (usa 3.11). Python 3.13 y 3.9 no se usan | `py -3.11 --version` |
| 2 | Crea `servicio-mineru\.venv` | existe `.venv\Scripts\python.exe` |
| 3 | `pip install "mineru[pipeline]==3.4.5" huggingface_hub fastapi uvicorn python-multipart six` (PyTorch en CPU, unos 2 GB) | `.venv\Scripts\python -c "import mineru"` |
| 4 | `descargar_modelos.py`: baja los modelos del backend `pipeline` a `modelos\pipeline` (unos 3 GB) y escribe `mineru.json` | existe `mineru.json` |
| 5 | Arranca el servicio en el puerto 8011, convierte Kumar y lo apaga | imprime "Instalación verificada" |

## Reglas que no se deben cambiar

- **Versión 3.4.5 fija.** Es la que validó la Fase 0 (ADR 0001: coordenadas en escala 0 a 1000, ids de bloque
  estables). Otra versión puede cambiar bloques y coordenadas y romper el anclaje de citas. Si hay que subirla,
  repetir la verificación del ADR 0001.
- **Backend `pipeline`, en CPU.** El equipo tiene una RTX 2050 de 4 GB; no se usa. En CPU toma de 11 a 21 s por
  página (un artículo de 10 páginas, unos 2 a 4 minutos).
- **Modelos con `local_dir`, sin enlaces simbólicos.** En Windows sin modo desarrollador la caché de HuggingFace
  falla con `WinError 1314`. Por eso se usa `descargar_modelos.py` y no la descarga automática de MinerU.
- **Variables al arrancar** (las pone `Extractor.ps1`; hay que ponerlas si se arranca a mano):
  `MINERU_MODEL_SOURCE=local` y `MINERU_TOOLS_CONFIG_JSON=<ruta>\servicio-mineru\mineru.json`.
- No se versionan `.venv/`, `modelos/` ni `mineru.json` (ya están en `.gitignore`).

## Arrancar a mano (sin el acceso directo)

```powershell
cd extractor-matriz\servicio-mineru
$env:MINERU_MODEL_SOURCE = "local"
$env:MINERU_TOOLS_CONFIG_JSON = "$PWD\mineru.json"
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

Comprobar: `curl http://127.0.0.1:8001/salud` debe responder `{"mineru":"3.4.5","backend":"pipeline",...}`.

## Problemas conocidos

| Síntoma | Causa y arreglo |
| --- | --- |
| `No hay Python 3.10 a 3.12` | Instalar Python 3.11 desde python.org y repetir el script |
| `WinError 1314` al bajar modelos | Se bajó por la vía automática; usar `descargar_modelos.py` (el script ya lo hace) |
| Descarga de modelos cortada | Repetir el script: `snapshot_download` continúa donde quedó |
| `ModuleNotFoundError: No module named 'six'` al convertir (HTTP 500 «MinerU falló») | MinerU usa `six` sin declararlo: `.venv\Scripts\python -m pip install six`. Si aparece otro módulo faltante, instalarlo igual y anotarlo aquí y en `instalar.ps1` |
| `pip` falla compilando un paquete | Casi siempre es Python 3.13: borrar `.venv` y repetir con 3.11 |
| MinerU intenta descargar modelos al convertir | Faltan las dos variables de entorno de arriba |
| Puerto 8001 ocupado | Otro MinerU ya corre: la cabecera lo mostrará en verde y no hace falta otro |
| Cabecera en amarillo «Ocupado» | MinerU está convirtiendo un PDF; no hace falta hacer nada. Si dura más de lo normal (más de 30 s por página), revisar `datos\mineru.log.err` |
| Cabecera en rojo aunque está instalado | Nada escucha en el 8001: el servicio no arrancó o se cerró. Ver `datos\mineru.log.err` |
| La primera conversión tarda mucho | Carga de modelos en memoria; las siguientes son más rápidas |

## Resultado esperado de la verificación

En este equipo (CPU, Python 3.11): modelos 2,5 GB; Kumar (8 páginas) se convierte en **2 min 35 s** y el zip trae
`content_list.json`, `content_list_v2.json`, `middle.json` y `articulo.md`. El `content_list.json` es **idéntico**
(96 bloques) al guardado en `recursos/fixtures/mineru/kumar_2022.zip`, así que la instalación reproduce la Fase 0.

## Cómo comprobar desde la aplicación

La cabecera de la interfaz muestra **MinerU** con punto verde si responde. El panel de registro anota
"convirtiendo con MinerU…" y "convertido en N s" por cada PDF. Los artículos que quedaron en Nuevo mientras
MinerU estaba apagado se convierten solos (barrido cada 15 s) cuando responde.

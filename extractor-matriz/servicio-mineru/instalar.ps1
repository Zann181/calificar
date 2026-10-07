# Instala servicio-mineru (MinerU 3.4.5, backend pipeline, CPU) en esta carpeta. Se puede repetir sin daño:
# cada paso se salta si ya está hecho. Guía completa para una IA o una persona: INSTALAR.md
#
#   powershell -ExecutionPolicy Bypass -File servicio-mineru\instalar.ps1
#
# Resultado: .venv\ (entorno), modelos\pipeline\ (unos 3 GB), mineru.json. Termina con una conversión
# de prueba del PDF de Kumar; si imprime "Instalación verificada", MinerU quedó listo.

$ErrorActionPreference = "Stop"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$version = "3.4.5"   # la validada en la Fase 0 (ADR 0001); cambiarla exige repetir esa validación
$venv = Join-Path $aqui ".venv"
$py = Join-Path $venv "Scripts\python.exe"

function Paso($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

Paso "1/5 Python 3.10 a 3.12 (el instalador usa el lanzador 'py')"
$base = $null
foreach ($v in "3.11", "3.12", "3.10") {
    $ruta = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ruta) { $base = $ruta; break }
}
if (-not $base -and -not (Test-Path $py)) { throw "No hay Python 3.10 a 3.12. Instale Python 3.11 desde python.org y repita." }

Paso "2/5 Entorno virtual en $venv"
if (-not (Test-Path $py)) { & $base -m venv $venv; if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno" } }
& $py -m pip install -q --upgrade pip

Paso "3/5 Paquetes (MinerU $version y el servicio HTTP). Tarda varios minutos"
& $py -m pip install "mineru[pipeline]==$version" huggingface_hub fastapi uvicorn python-multipart six
if ($LASTEXITCODE -ne 0) { throw "pip falló. Revise el mensaje de arriba (red, espacio en disco)" }

Paso "4/5 Modelos del backend pipeline (unos 3 GB) y mineru.json"
if (-not (Test-Path (Join-Path $aqui "mineru.json"))) {
    $env:PYTHONIOENCODING = "utf-8"
    & $py (Join-Path $aqui "descargar_modelos.py")
    if ($LASTEXITCODE -ne 0) { throw "La descarga de modelos falló. Repita el script: continúa donde quedó" }
} else { Write-Host "mineru.json ya existe: modelos ya descargados" }

Paso "5/5 Verificación: convertir kumar_2022.pdf con el servicio"
$env:MINERU_MODEL_SOURCE = "local"
$env:MINERU_TOOLS_CONFIG_JSON = Join-Path $aqui "mineru.json"
$env:PYTHONIOENCODING = "utf-8"
$log = Join-Path $aqui "verificacion.log"
$srv = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8011" `
    -WorkingDirectory $aqui -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
try {
    $ok = $false
    for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
        Start-Sleep 1
        try { Invoke-RestMethod "http://127.0.0.1:8011/salud" -TimeoutSec 2 | Out-Null; $ok = $true } catch { }
    }
    if (-not $ok) { throw "El servicio no arrancó (ver $log.err)" }
    $pdf = Join-Path $aqui "..\recursos\fixtures\kumar_2022.pdf"
    $zip = Join-Path $aqui "verificacion.zip"
    $inicio = Get-Date
    & curl.exe -s -f -m 3600 -F "archivo=@$pdf;type=application/pdf" -o $zip "http://127.0.0.1:8011/convertir"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zip) -or (Get-Item $zip).Length -lt 1000) { throw "La conversión de prueba falló (ver $log.err)" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $nombres = [System.IO.Compression.ZipFile]::OpenRead($zip).Entries | ForEach-Object { $_.FullName }
    if (-not ($nombres -match "content_list")) { throw "El zip no trae content_list.json" }
    $seg = [int]((Get-Date) - $inicio).TotalSeconds
    Write-Host "Instalación verificada: Kumar convertido en $seg s ($($nombres.Count) archivos)." -ForegroundColor Green
} finally {
    if ($srv -and -not $srv.HasExited) { & taskkill.exe /PID $srv.Id /T /F | Out-Null }
    Remove-Item (Join-Path $aqui "verificacion.zip") -ErrorAction SilentlyContinue
}

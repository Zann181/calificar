# Lanzador del Extractor de matriz.
#   1. Arranca la API (que también sirve la interfaz) en http://127.0.0.1:8765, sin ventana de consola.
#   2. Abre la aplicación en una ventana propia de Edge.
#   3. Cuando esa ventana se cierra, apaga el servidor.
#   0. Antes de arrancar se actualiza solo: git pull --ff-only --autostash, dependencias si
#      cambiaron pyproject.toml / package-lock.json, migraciones de la base y recompilación de la interfaz.
# Si el extractor ya está abierto, el acceso directo trae su ventana al frente: no arranca otro servidor.
# Registro: datos\extractor.log

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $raiz "backend"
$frontend = Join-Path $raiz "frontend"
$datos = Join-Path $raiz "datos"
$puerto = if ($env:EXTRACTOR_PUERTO) { [int]$env:EXTRACTOR_PUERTO } else { 8765 }
$url = "http://127.0.0.1:$puerto/"
$perfil = Join-Path $env:LOCALAPPDATA "ExtractorMatriz\ventana"
New-Item -ItemType Directory -Force $datos, $perfil | Out-Null
$registro = Join-Path $datos "extractor.log"

Add-Type -AssemblyName System.Windows.Forms
function Avisar([string]$mensaje) {
    [System.Windows.Forms.MessageBox]::Show($mensaje, "Extractor de matriz", "OK", "Error") | Out-Null
}

function Buscar-Edge {
    foreach ($ruta in @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")) {
        if (Test-Path $ruta) { return $ruta }
    }
    return $null
}

function Abrir-Ventana {
    $edge = Buscar-Edge
    if (-not $edge) { Start-Process $url; return $null }
    # Perfil propio: la ventana es un proceso aparte que termina al cerrarla.
    return Start-Process -FilePath $edge -PassThru -ArgumentList @(
        "--app=$url", "--user-data-dir=`"$perfil`"", "--no-first-run", "--no-default-browser-check",
        "--window-size=1440,900")
}

function Traer-Al-Frente {
    # Segunda pulsación del acceso directo: se enfoca la ventana abierta en lugar de abrir otra.
    $ventana = Get-Process msedge -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq "Extractor de matriz" } | Select-Object -First 1
    if (-not $ventana) { return $false }
    Add-Type -Namespace Win32 -Name Ventana -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
"@
    [Win32.Ventana]::ShowWindow($ventana.MainWindowHandle, 9) | Out-Null  # 9 = restaurar si está minimizada
    [Win32.Ventana]::SetForegroundWindow($ventana.MainWindowHandle) | Out-Null
    return $true
}

function Puerto-Abierto {
    $cliente = New-Object System.Net.Sockets.TcpClient
    try { $cliente.Connect("127.0.0.1", $puerto); return $true } catch { return $false } finally { $cliente.Dispose() }
}

# --- una sola instancia ---
$creado = $false
$candado = New-Object System.Threading.Mutex($true, "Local\ExtractorMatriz", [ref]$creado)
if (-not $creado) {
    if (-not (Traer-Al-Frente)) { Abrir-Ventana | Out-Null }
    exit 0
}

function Ejecutar([string]$exe, [string[]]$argumentos, [string]$cwd, [int]$segundos = 180) {
    # Corre un comando oculto con límite de tiempo; devuelve su código de salida (-1 si venció).
    $p = Start-Process -FilePath $exe -ArgumentList $argumentos -WorkingDirectory $cwd -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$registro.act" -RedirectStandardError "$registro.act.err"
    $null = $p.Handle  # sin conservar el identificador, ExitCode puede llegar vacío en PowerShell 5.1
    if (-not $p.WaitForExit($segundos * 1000)) { & taskkill.exe /PID $p.Id /T /F | Out-Null; return -1 }
    $p.WaitForExit()  # sin esto ExitCode llega vacío tras un WaitForExit con tiempo límite
    return $p.ExitCode
}

function Huella([string[]]$rutas) {
    $partes = foreach ($r in $rutas) {
        if (Test-Path $r -PathType Container) { Get-ChildItem $r -Recurse -File | Sort-Object FullName | ForEach-Object { (Get-FileHash $_.FullName).Hash } }
        elseif (Test-Path $r) { (Get-FileHash $r).Hash }
    }
    return ($partes -join "")
}

function Actualizar {
    # Actualización automática al arrancar. Nunca impide abrir la app: si algo falla se anota y se sigue.
    $estadoRuta = Join-Path $datos "actualizacion.json"
    $registro = Join-Path $datos "actualizacion.log"  # registro propio: el del servidor se reescribe al arrancar
    try {
        # 1. Código nuevo del repositorio (solo si no hay cambios locales en archivos versionados).
        if (Get-Command git -ErrorAction SilentlyContinue) {
            $env:GIT_TERMINAL_PROMPT = "0"
            # --autostash: los cambios locales sin commit se guardan, se trae lo nuevo y se devuelven.
            $codigo = Ejecutar "git" @("-C", "`"$raiz`"", "pull", "--ff-only", "--autostash", "--quiet") $raiz 20
            if ($codigo -ne 0) {
                Add-Content $registro "$(Get-Date -Format s) Actualización: git pull no se pudo (sin red, rama sin remoto o conflicto); se sigue con la versión actual."
                Add-Content $registro (Get-Content "$registro.act.err" -Raw -ErrorAction SilentlyContinue)
            }
        }

        # 2. Dependencias solo si cambiaron sus archivos de definición.
        $viejo = if (Test-Path $estadoRuta) { Get-Content $estadoRuta -Raw | ConvertFrom-Json } else { $null }
        $hPy = Huella @((Join-Path $backend "pyproject.toml"))
        $hJs = Huella @((Join-Path $frontend "package-lock.json"))
        $python = Join-Path $backend ".venv\Scripts\python.exe"
        if (Test-Path $python) {
            if (-not $viejo -or $viejo.py -ne $hPy) {
                Add-Content $registro "$(Get-Date -Format s) Actualización: instalando dependencias de Python..."
                if ((Ejecutar $python @("-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", ".[dev]") $backend 600) -ne 0) { throw "pip install falló (ver $registro.act.err)" }
            }
            # 3. Migraciones de la base (no hace nada si ya está al día).
            if ((Ejecutar $python @("-m", "alembic", "upgrade", "head") $backend 120) -ne 0) { throw "alembic falló (ver $registro.act.err)" }
        }
        if ((-not $viejo -or $viejo.js -ne $hJs) -and (Test-Path (Join-Path $frontend "package.json"))) {
            Add-Content $registro "$(Get-Date -Format s) Actualización: instalando dependencias de la interfaz..."
            if ((Ejecutar "npm.cmd" @("install", "--no-audit", "--no-fund") $frontend 600) -ne 0) { throw "npm install falló (ver $registro.act.err)" }
        }
        @{ py = $hPy; js = $hJs } | ConvertTo-Json | Set-Content $estadoRuta -Encoding utf8
    } catch {
        Add-Content $registro "$(Get-Date -Format s) Actualización con error: $($_.Exception.Message)"
    }
}

$servidor = $null
try {
    # Si el puerto ya lo usa otro programa (p. ej. una copia vieja del extractor), se toma el siguiente libre:
    # la ventana debe abrir SIEMPRE el servidor de esta carpeta. Una segunda instancia nuestra ya salió por el candado.
    while (Puerto-Abierto) { $puerto++ }
    $url = "http://127.0.0.1:$puerto/"
    Actualizar

    # --- interfaz: compilar si falta o si el código cambió ---
    $indice = Join-Path $frontend "dist\index.html"
    $fuentes = Get-ChildItem (Join-Path $frontend "src") -Recurse -File
    $desactualizada = -not (Test-Path $indice) -or
        ($fuentes | Where-Object { $_.LastWriteTime -gt (Get-Item $indice).LastWriteTime } | Select-Object -First 1)
    if ($desactualizada) {
        Add-Content $registro "$(Get-Date -Format s) Compilando la interfaz..."
        $npm = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "build" -WorkingDirectory $frontend `
            -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput "$registro.npm"
        if ($npm.ExitCode -ne 0) { throw "No se pudo compilar la interfaz (ver $registro.npm)." }
    }

    # --- servidor ---
    if (-not (Puerto-Abierto)) {
        $python = Join-Path $backend ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) { throw "Falta el entorno de Python en $backend\.venv (ver README.md)." }
        $env:PYTHONIOENCODING = "utf-8"
        if (-not $env:SIN_LOGIN) { $env:SIN_LOGIN = "true" }  # escritorio: solo escucha en 127.0.0.1
        $servidor = Start-Process -FilePath $python -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
            -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$puerto" `
            -RedirectStandardOutput $registro -RedirectStandardError "$registro.err"
        $listo = $false
        for ($i = 0; $i -lt 60 -and -not $listo; $i++) {
            Start-Sleep -Milliseconds 500
            if ($servidor.HasExited) { throw "El servidor se detuvo al arrancar (ver $registro.err)." }
            try { Invoke-RestMethod "${url}api/v1/salud" -TimeoutSec 2 | Out-Null; $listo = $true } catch { }
        }
        if (-not $listo) { throw "El servidor no respondió en 30 segundos (ver $registro.err)." }
    }

    # --- ventana: el extractor vive mientras esté abierta ---
    $ventana = Abrir-Ventana
    if ($ventana) {
        $ventana.WaitForExit()
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "El extractor está abierto en su navegador. Pulse Aceptar para apagarlo.",
            "Extractor de matriz") | Out-Null
    }
} catch {
    Avisar $_.Exception.Message
} finally {
    # python.exe del entorno virtual lanza un proceso hijo: se termina todo el árbol.
    if ($servidor -and -not $servidor.HasExited) { & taskkill.exe /PID $servidor.Id /T /F | Out-Null }
    $candado.ReleaseMutex()
    $candado.Dispose()
}

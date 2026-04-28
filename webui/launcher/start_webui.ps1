#requires -Version 5.1
<#
.SYNOPSIS
    Start the local X-Amplicon Web UI on Windows.

.DESCRIPTION
    Production mode starts one FastAPI service. If webui/frontend/dist exists,
    FastAPI serves the built React application directly. If dist is missing,
    the launcher can build it from source when Node.js/npm are available.

    Development mode (-Dev) starts FastAPI plus the Vite dev server.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\webui\launcher\start_webui.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\webui\launcher\start_webui.ps1 -BuildFrontend

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\webui\launcher\start_webui.ps1 -Dev
#>

[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$FrontendPort = 5173,
    [switch]$Dev,
    [switch]$BuildFrontend,
    [switch]$NoBuild,
    [switch]$NoBrowser
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "..\.."))
$FrontendDir = Join-Path $ProjectRoot "webui\frontend"
$FrontendDist = Join-Path $FrontendDir "dist"
$StateDir = Join-Path $ProjectRoot ".xamplicon_webui"
$BackendLog = Join-Path $StateDir "webui_backend.err.log"
$FrontendLog = Join-Path $StateDir "webui_frontend.out.log"
Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Resolve-WebUIPython {
    $bundledPython = Join-Path $ProjectRoot ".tools\python-3.13.13-amd64\python.exe"
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

    if (Test-Path -LiteralPath $bundledPython) {
        return $bundledPython
    }
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    return "python"
}

function Resolve-Npm {
    $npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($npm) {
        return [string]$npm.Source
    }
    $npm = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($npm) {
        return [string]$npm.Source
    }
    return ""
}

function Test-PortAvailable {
    param(
        [string]$Address,
        [int]$CandidatePort
    )

    $listener = $null
    try {
        $ipAddress = [System.Net.IPAddress]::Parse($Address)
        $listener = [System.Net.Sockets.TcpListener]::new($ipAddress, $CandidatePort)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Resolve-AvailablePort {
    param(
        [string]$Address,
        [int]$StartPort
    )

    for ($candidate = $StartPort; $candidate -lt ($StartPort + 20); $candidate++) {
        if (Test-PortAvailable -Address $Address -CandidatePort $candidate) {
            return $candidate
        }
    }
    throw "No available local port found in range $StartPort-$($StartPort + 19)."
}

function Test-FrontendBuilt {
    return (Test-Path -LiteralPath (Join-Path $FrontendDist "index.html"))
}

function Invoke-FrontendBuild {
    $npm = Resolve-Npm
    if (-not $npm) {
        throw "Node.js/npm was not found. Install Node.js 20+ or use a release package that already includes webui\frontend\dist."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "package.json"))) {
        throw "webui\frontend\package.json was not found."
    }

    Write-Host ""
    Write-Host "Preparing frontend build" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies with npm.cmd install"
        & $npm "--prefix" $FrontendDir "install"
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed with exit code $LASTEXITCODE."
        }
    }

    Write-Host "Building frontend with npm.cmd run build"
    & $npm "--prefix" $FrontendDir "run" "build"
    if ($LASTEXITCODE -ne 0) {
        throw "npm run build failed with exit code $LASTEXITCODE."
    }
}

function Test-BackendImports {
    param([string]$PythonExe)

    & $PythonExe -c "import fastapi, uvicorn; print('webui backend dependencies available')" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Web UI backend dependencies are missing." -ForegroundColor Red
        Write-Host "Install them with one of these commands:"
        Write-Host "  & `"$PythonExe`" -m pip install -r requirements-webui.txt"
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps"
        exit 1
    }
}

$PythonExe = Resolve-WebUIPython
Write-Host "X-Amplicon Web UI launcher" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "Python: $PythonExe"
Test-BackendImports -PythonExe $PythonExe

if ($Dev) {
    $BackendPort = Resolve-AvailablePort -Address $BindHost -StartPort $Port
    $ResolvedFrontendPort = Resolve-AvailablePort -Address $BindHost -StartPort $FrontendPort
    $BackendUrl = "http://$BindHost`:$BackendPort"
    $FrontendUrl = "http://$BindHost`:$ResolvedFrontendPort"
    $npm = Resolve-Npm
    if (-not $npm) {
        throw "Node.js/npm was not found. Install Node.js 20+ to use -Dev mode."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies with npm.cmd install"
        & $npm "--prefix" $FrontendDir "install"
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed with exit code $LASTEXITCODE."
        }
    }

    Write-Host ""
    Write-Host "Starting backend: $BackendUrl" -ForegroundColor Green
    $backendProcess = Start-Process -FilePath $PythonExe -ArgumentList @(
        "-m", "uvicorn", "webui.backend.app:app", "--host", $BindHost, "--port", "$BackendPort"
    ) -WorkingDirectory $ProjectRoot -PassThru -RedirectStandardError $BackendLog -RedirectStandardOutput (Join-Path $StateDir "webui_backend.out.log")

    if (-not $NoBrowser) {
        Start-Process $FrontendUrl
    }

    try {
        Write-Host "Starting frontend dev server: $FrontendUrl" -ForegroundColor Green
        Write-Host "Backend log: $BackendLog"
        Write-Host "Press Ctrl+C to stop the Vite server; the launcher will stop the backend."
        & $npm "--prefix" $FrontendDir "run" "dev" "--" "--host" $BindHost "--port" "$ResolvedFrontendPort"
        exit $LASTEXITCODE
    }
    finally {
        if ($backendProcess -and -not $backendProcess.HasExited) {
            Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

if (($BuildFrontend -or -not (Test-FrontendBuilt)) -and -not $NoBuild) {
    Invoke-FrontendBuild
}

if (-not (Test-FrontendBuilt)) {
    Write-Host ""
    Write-Host "Frontend build was not found: $FrontendDist" -ForegroundColor Red
    Write-Host "Build it with:"
    Write-Host "  cd webui\frontend"
    Write-Host "  npm.cmd install"
    Write-Host "  npm.cmd run build"
    Write-Host "Then rerun this launcher, or start development mode with -Dev."
    exit 1
}

$ResolvedPort = Resolve-AvailablePort -Address $BindHost -StartPort $Port
$Url = "http://$BindHost`:$ResolvedPort"

Write-Host ""
Write-Host "Starting local Web UI: $Url" -ForegroundColor Green
Write-Host "Serving frontend build from: $FrontendDist"
Write-Host "Press Ctrl+C in this window to stop the server."

if (-not $NoBrowser) {
    Start-Process $Url
}

& $PythonExe -m uvicorn webui.backend.app:app --host $BindHost --port $ResolvedPort
exit $LASTEXITCODE

#requires -Version 5.1
<#
.SYNOPSIS
    Configure and start the bundled X-Amplicon Web UI release package.

.DESCRIPTION
    This script is intended for the GitHub Releases archive. It uses the
    bundled Python runtime under .tools, checks the small RDP database and
    Web UI frontend build, creates a local .env file if needed, then starts
    the local browser Web UI.
#>

[CmdletBinding()]
param(
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$RepairDeps,
    [switch]$UseChinaMirror
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$PythonExe = Join-Path $Root ".tools\python-3.13.13-amd64\python.exe"
$PythonZip = Join-Path $Root ".tools\python-3.13.13-amd64.zip"
$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"
$RdpDb = Join-Path $Root "database\rdp_16s_v18.fa"
$FrontendIndex = Join-Path $Root "webui\frontend\dist\index.html"
$Launcher = Join-Path $Root "start_webui.ps1"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Stop-Release {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host "Keep this window open and read the message above. Press Enter to exit."
    [void][System.Console]::ReadLine()
    exit 1
}

Write-Host "X-Amplicon local Web UI release launcher" -ForegroundColor Cyan
Write-Host "Package root: $Root"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    if (Test-Path -LiteralPath $PythonZip) {
        Write-Step "Expanding bundled Python runtime"
        Expand-Archive -LiteralPath $PythonZip -DestinationPath (Join-Path $Root ".tools") -Force
    }
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    Stop-Release "Bundled Python was not found: $PythonExe"
}
Write-Ok "Bundled Python found"

if (-not (Test-Path -LiteralPath $EnvFile) -and (Test-Path -LiteralPath $EnvExample)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile -Force
    Write-Ok "Created local .env from .env.example"
}

if (-not (Test-Path -LiteralPath $RdpDb)) {
    Stop-Release "Small RDP database was not found: $RdpDb"
}
Write-Ok "Small RDP database found"

if (-not (Test-Path -LiteralPath $FrontendIndex)) {
    Stop-Release "Prebuilt Web UI frontend was not found: $FrontendIndex"
}
Write-Ok "Prebuilt Web UI frontend found"

if (-not (Test-Path -LiteralPath $Launcher)) {
    Stop-Release "Web UI launcher was not found: $Launcher"
}

Write-Step "Checking bundled Python dependencies"
$checkCode = @'
import importlib
modules = [
    'click', 'pandas', 'numpy', 'scipy', 'skbio', 'yaml', 'Bio',
    'pydantic', 'plotly', 'rich', 'litellm', 'fastapi', 'uvicorn',
    'aiofiles', 'agent_cli', 'process'
]
missing = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(f'{name}: {exc}')
if missing:
    print('Missing or broken modules:')
    print('\n'.join(missing))
    raise SystemExit(1)
print('dependency check passed')
'@
& $PythonExe -c $checkCode
if ($LASTEXITCODE -ne 0) {
    if (-not $RepairDeps) {
        Stop-Release "Bundled dependencies are incomplete. Rerun this script with -RepairDeps if internet access is available."
    }

    Write-Step "Repairing dependencies with setup_windows.ps1"
    $setupArgs = @("-ExecutionPolicy", "Bypass", "-File", ".\setup_windows.ps1", "-InstallWebUIDeps", "-InstallStaticExport", "-SkipConfigCheck")
    if ($UseChinaMirror) {
        $setupArgs += "-UseChinaMirror"
    }
    & powershell @setupArgs
    if ($LASTEXITCODE -ne 0) {
        Stop-Release "Dependency repair failed."
    }
}
Write-Ok "Bundled Python dependencies passed"

Write-Step "Checking RDP database registration"
& $PythonExe process.py check-database rdp_16s_v18
if ($LASTEXITCODE -ne 0) {
    Stop-Release "RDP database check failed."
}

Write-Step "Starting Web UI"
Write-Host "The browser URL will be printed below. Default: http://127.0.0.1:$Port"
& $Launcher -Port $Port -NoBuild -NoBrowser:$NoBrowser
exit $LASTEXITCODE

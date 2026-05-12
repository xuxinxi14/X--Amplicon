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
    [switch]$ManagedApp,
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
$SplashScript = Join-Path $Root "Start_X-Amplicon_Splash.ps1"
$SplashStatusFile = ""

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
    Set-SplashStatus $Message
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Start-Splash {
    if (-not $ManagedApp) {
        return
    }
    if (-not (Test-Path -LiteralPath $SplashScript)) {
        return
    }
    try {
        $splashDir = Join-Path ([System.IO.Path]::GetTempPath()) "X-Amplicon"
        New-Item -ItemType Directory -Force -Path $splashDir | Out-Null
        $script:SplashStatusFile = Join-Path $splashDir ("splash_" + [System.Guid]::NewGuid().ToString("N") + ".txt")
        Set-Content -LiteralPath $script:SplashStatusFile -Value "STATUS|Starting X-Amplicon Web UI..." -Encoding UTF8
        $args = @(
            "-NoProfile",
            "-STA",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$SplashScript`"",
            "-StatusFile", "`"$script:SplashStatusFile`""
        )
        Start-Process -FilePath "powershell.exe" -ArgumentList $args | Out-Null
    }
    catch {
        $script:SplashStatusFile = ""
    }
}

function Set-SplashStatus {
    param([string]$Message)
    if (-not $script:SplashStatusFile) {
        return
    }
    Set-Content -LiteralPath $script:SplashStatusFile -Value "STATUS|$Message" -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Stop-Splash {
    if (-not $script:SplashStatusFile) {
        return
    }
    Set-Content -LiteralPath $script:SplashStatusFile -Value "CLOSE" -Encoding UTF8 -ErrorAction SilentlyContinue
}

trap {
    Stop-Splash
    throw $_
}

function Stop-Release {
    param([string]$Message)
    if ($ManagedApp) {
        Stop-Splash
        try {
            $shell = New-Object -ComObject WScript.Shell
            [void]$shell.Popup($Message, 0, "X-Amplicon Web UI", 16)
        }
        catch {
        }
        exit 1
    }
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host "Keep this window open and read the message above. Press Enter to exit."
    [void][System.Console]::ReadLine()
    exit 1
}

Start-Splash
Set-SplashStatus "Checking release package..."

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
Set-SplashStatus "Bundled Python found"
Write-Ok "Bundled Python found"

if (-not (Test-Path -LiteralPath $EnvFile) -and (Test-Path -LiteralPath $EnvExample)) {
    Set-SplashStatus "Preparing local configuration..."
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile -Force
    Write-Ok "Created local .env from .env.example"
}

Set-SplashStatus "Checking bundled database..."
if (-not (Test-Path -LiteralPath $RdpDb)) {
    Stop-Release "Small RDP database was not found: $RdpDb"
}
Write-Ok "Small RDP database found"

Set-SplashStatus "Checking Web UI files..."
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
try {
    & $Launcher -Port $Port -NoBuild -NoBrowser:$NoBrowser -ManagedApp:$ManagedApp -SplashStatusFile $SplashStatusFile
    $exitCode = $LASTEXITCODE
}
catch {
    Stop-Splash
    throw
}
if ($exitCode -ne 0) {
    Stop-Splash
}
exit $exitCode

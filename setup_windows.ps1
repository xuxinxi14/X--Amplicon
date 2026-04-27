#requires -Version 5.1
<#
.SYNOPSIS
    Prepare a Windows checkout of X-Amplicon for local CLI/Agent use.

.DESCRIPTION
    This script is intended for source-distribution installs on Windows.
    Run it from the project root after cloning or extracting the repository.

    It will:
      - prefer the bundled .tools Python if present;
      - otherwise create and use a local .venv from an existing Python 3.10+;
      - install Python dependencies;
      - optionally install Agent skill dependencies;
      - copy .env.example to .env when .env is missing;
      - check external binaries and reference databases;
      - create simple run_agent.bat and run_process.bat launchers.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallStaticExport

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
#>

[CmdletBinding()]
param(
    [switch]$UseChinaMirror,
    [string]$PipIndexUrl = "",
    [switch]$SkipDependencyInstall,
    [switch]$InstallStaticExport,
    [switch]$InstallSkillDeps,
    [switch]$SkipConfigCheck,
    [switch]$NoLauncher
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
Set-Location -LiteralPath $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "WARN $Message" -ForegroundColor Yellow
}

function Stop-Setup {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR $Message" -ForegroundColor Red
    exit 1
}

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PythonVersion {
    param([string]$PythonExe)
    $versionText = @(& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $versionText) {
        throw "Unable to run Python at $PythonExe"
    }
    return [version]([string]$versionText[0])
}

function Get-SystemPython {
    if (Test-CommandAvailable "py") {
        $pyPath = @(& py -3 -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $pyPath) {
            return [string]$pyPath[0]
        }
    }

    $pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidate = [string]$pythonCommand.Source
        $probe = @(& $candidate -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $probe) {
            return [string]$probe[0]
        }
    }

    return ""
}

function Resolve-ProjectPython {
    $bundledPython = Join-Path $ProjectRoot ".tools\python-3.13.13-amd64\python.exe"
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $venvDir = Join-Path $ProjectRoot ".venv"

    if (Test-Path -LiteralPath $bundledPython) {
        return @{
            Python = $bundledPython
            Kind = "bundled"
        }
    }

    if (Test-Path -LiteralPath $venvPython) {
        return @{
            Python = $venvPython
            Kind = "venv"
        }
    }

    $systemPython = Get-SystemPython
    if (-not $systemPython) {
        Stop-Setup "Python 3.10+ was not found. Install Python from https://www.python.org/downloads/windows/ and rerun this script."
    }

    $systemVersion = Get-PythonVersion $systemPython
    if ($systemVersion -lt [version]"3.10.0") {
        Stop-Setup "Python $systemVersion found at $systemPython, but X-Amplicon requires Python 3.10+."
    }

    Write-Step "Creating local virtual environment"
    & $systemPython -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "Failed to create .venv with $systemPython."
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Stop-Setup ".venv was created, but .venv\Scripts\python.exe was not found."
    }

    return @{
        Python = $venvPython
        Kind = "venv"
    }
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "$FailureMessage Exit code: $LASTEXITCODE"
    }
}

function Get-PipIndexArgs {
    if (-not $PipIndexUrl -and $UseChinaMirror) {
        $script:PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple"
    }

    if ($PipIndexUrl) {
        return @("-i", $PipIndexUrl)
    }
    return @()
}

function Install-Dependencies {
    param([string]$PythonExe)

    Write-Step "Checking pip"
    & $PythonExe -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "pip is missing; trying ensurepip."
        Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "ensurepip", "--upgrade") -FailureMessage "Failed to bootstrap pip."
    }

    $indexArgs = Get-PipIndexArgs
    $upgradeArgs = @("-m", "pip", "install", "--upgrade") + $indexArgs + @("pip", "setuptools", "wheel")
    Invoke-Checked -FilePath $PythonExe -Arguments $upgradeArgs -FailureMessage "Failed to upgrade pip tooling."

    $requirementsPath = Join-Path $ProjectRoot "requirements.txt"
    if (Test-Path -LiteralPath $requirementsPath) {
        Write-Step "Installing dependencies from requirements.txt"
        $installArgs = @("-m", "pip", "install") + $indexArgs + @("-r", $requirementsPath)
        Invoke-Checked -FilePath $PythonExe -Arguments $installArgs -FailureMessage "Dependency installation failed."
        if ($InstallStaticExport) {
            Write-Step "Installing optional static Plotly export dependency"
            $staticInstallArgs = @("-m", "pip", "install") + $indexArgs + @("kaleido>=0.2.1")
            Invoke-Checked -FilePath $PythonExe -Arguments $staticInstallArgs -FailureMessage "Optional static export dependency installation failed."
        }
        if ($InstallSkillDeps) {
            $skillRequirementsPath = Join-Path $ProjectRoot "requirements-skills.txt"
            if (Test-Path -LiteralPath $skillRequirementsPath) {
                Write-Step "Installing optional Agent skill dependencies from requirements-skills.txt"
                $skillInstallArgs = @("-m", "pip", "install") + $indexArgs + @("-r", $skillRequirementsPath)
                Invoke-Checked -FilePath $PythonExe -Arguments $skillInstallArgs -FailureMessage "Optional Agent skill dependency installation failed."
            }
            else {
                Write-Warn "requirements-skills.txt was not found; skipping optional Agent skill dependencies."
            }
        }
        return
    }

    Write-Step "Installing core Python dependencies"
    $packages = @(
        "numpy",
        "pandas",
        "scipy",
        "scikit-bio",
        "pyyaml",
        "click",
        "biopython",
        "pydantic>=2.0",
        "plotly>=5.15",
        "rich",
        "litellm"
    )

    if ($InstallStaticExport) {
        $packages += "kaleido>=0.2.1"
    }

    if ($InstallSkillDeps) {
        $packages += @(
            "llama-index",
            "deepeval",
            "ragas",
            "opentelemetry-api",
            "opentelemetry-sdk"
        )
    }

    $installArgs = @("-m", "pip", "install") + $indexArgs + $packages
    Invoke-Checked -FilePath $PythonExe -Arguments $installArgs -FailureMessage "Dependency installation failed."
}

function Test-PythonImports {
    param([string]$PythonExe)

    Write-Step "Running Python import smoke test"
$code = @"
import importlib
import importlib.util
modules = [
    'click', 'pandas', 'numpy', 'scipy', 'skbio', 'yaml', 'Bio',
    'pydantic', 'plotly', 'rich', 'agent_cli', 'process'
]
spec_modules = ['litellm']
missing = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append('{}: {}'.format(name, exc))
for name in spec_modules:
    if importlib.util.find_spec(name) is None:
        missing.append('{}: package not found'.format(name))
if missing:
    raise SystemExit('\n'.join(missing))
print('import smoke test passed')
"@
    Invoke-Checked -FilePath $PythonExe -Arguments @("-c", $code) -FailureMessage "Python import smoke test failed."
}

function Initialize-EnvFile {
    $envPath = Join-Path $ProjectRoot ".env"
    $examplePath = Join-Path $ProjectRoot ".env.example"

    Write-Step "Checking .env"
    if (Test-Path -LiteralPath $envPath) {
        Write-Ok ".env already exists."
        return
    }

    if (Test-Path -LiteralPath $examplePath) {
        Copy-Item -LiteralPath $examplePath -Destination $envPath
        Write-Warn ".env was created from .env.example. Edit it and set LLM_API_KEY before starting the Agent."
    }
    else {
        Write-Warn ".env.example was not found. Create .env manually before using the Agent."
    }
}

function Test-ProjectAssets {
    Write-Step "Checking external binaries and databases"

    $usearchPath = Join-Path $ProjectRoot "bin\windows\usearch.exe"
    $vsearchPath = Join-Path $ProjectRoot "bin\windows\vsearch.exe"
    $rdpPath = Join-Path $ProjectRoot "databas\rdp_16s_v18.fa"
    $silvaPath = Join-Path $ProjectRoot "databas\silva_16s_v123.fa"

    if (Test-Path -LiteralPath $usearchPath) {
        Write-Ok "USEARCH found: $usearchPath"
    }
    else {
        Write-Warn "USEARCH not found at bin\windows\usearch.exe. If its license does not allow redistribution, users must place it there manually or set usearch_path in pipeline_params.yaml."
    }

    if (Test-Path -LiteralPath $vsearchPath) {
        Write-Ok "VSEARCH found: $vsearchPath"
    }
    else {
        Write-Warn "VSEARCH not found at bin\windows\vsearch.exe. Install it or set vsearch_path in pipeline_params.yaml."
    }

    if (Test-Path -LiteralPath $rdpPath) {
        Write-Ok "RDP database found: $rdpPath"
    }
    else {
        Write-Warn "RDP database not found at databas\rdp_16s_v18.fa."
    }

    if (Test-Path -LiteralPath $silvaPath) {
        Write-Ok "SILVA database found: $silvaPath"
    }
    else {
        Write-Warn "SILVA database not found at databas\silva_16s_v123.fa. This is optional unless selected in pipeline_params.yaml."
    }
}

function Invoke-ConfigCheck {
    param([string]$PythonExe)

    $paramsPath = Join-Path $ProjectRoot "pipeline_params.yaml"
    if (-not (Test-Path -LiteralPath $paramsPath)) {
        Write-Warn "pipeline_params.yaml was not found; skipping pipeline config check."
        return
    }

    Write-Step "Running pipeline configuration check"
    & $PythonExe (Join-Path $ProjectRoot "process.py") check-pipeline-config --params $paramsPath
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Pipeline configuration check reported issues. Setup can still finish; fix pipeline_params.yaml before running analysis."
    }
    else {
        Write-Ok "Pipeline configuration check passed."
    }
}

function Write-Launchers {
    Write-Step "Writing launcher scripts"

    $runAgent = @'
@echo off
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%.tools\python-3.13.13-amd64\python.exe" (
  set "PY=%ROOT%.tools\python-3.13.13-amd64\python.exe"
) else if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PY=%ROOT%.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" "%ROOT%agent_cli.py" %*
exit /b %ERRORLEVEL%
'@

    $runProcess = @'
@echo off
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%.tools\python-3.13.13-amd64\python.exe" (
  set "PY=%ROOT%.tools\python-3.13.13-amd64\python.exe"
) else if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PY=%ROOT%.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" "%ROOT%process.py" %*
exit /b %ERRORLEVEL%
'@

    Set-Content -LiteralPath (Join-Path $ProjectRoot "run_agent.bat") -Value $runAgent -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $ProjectRoot "run_process.bat") -Value $runProcess -Encoding ASCII
    Write-Ok "Created run_agent.bat and run_process.bat."
}

if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) {
    Stop-Setup "This setup script is intended for Windows only."
}

Write-Host "X-Amplicon Windows setup" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

$pythonInfo = Resolve-ProjectPython
$pythonExe = [string]$pythonInfo.Python
$pythonKind = [string]$pythonInfo.Kind
$pythonVersion = Get-PythonVersion $pythonExe

Write-Step "Using Python"
Write-Ok "$pythonExe"
Write-Ok "Python $pythonVersion ($pythonKind)"

if ($pythonVersion -lt [version]"3.10.0") {
    Stop-Setup "Python $pythonVersion is too old. X-Amplicon requires Python 3.10+."
}

if (-not $SkipDependencyInstall) {
    Install-Dependencies $pythonExe
}
else {
    Write-Warn "Skipping dependency installation."
}

Test-PythonImports $pythonExe
Initialize-EnvFile
Test-ProjectAssets

if (-not $SkipConfigCheck) {
    Invoke-ConfigCheck $pythonExe
}
else {
    Write-Warn "Skipping pipeline configuration check."
}

if (-not $NoLauncher) {
    Write-Launchers
}

Write-Host ""
Write-Host "Setup finished." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Edit .env and set LLM_API_KEY / DEFAULT_MODEL if you want to use the Agent."
if ($NoLauncher) {
    Write-Host "  2. Start the Agent: & `"$pythonExe`" agent_cli.py"
    Write-Host "  3. Run CLI commands: & `"$pythonExe`" process.py --help"
}
else {
    Write-Host "  2. Start the Agent: .\run_agent.bat"
    Write-Host "  3. Run CLI commands: .\run_process.bat --help"
}
Write-Host ""

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
      - optionally install local Web UI dependencies;
      - copy .env.example to .env when .env is missing;
      - check external binaries and reference databases;
      - create simple run_agent.bat and run_process.bat launchers;
      - write a machine-readable Windows setup diagnostics report.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallStaticExport

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -CreateDesktopShortcuts
#>

[CmdletBinding()]
param(
    [switch]$UseChinaMirror,
    [string]$PipIndexUrl = "",
    [switch]$SkipDependencyInstall,
    [switch]$InstallStaticExport,
    [switch]$InstallSkillDeps,
    [switch]$InstallWebUIDeps,
    [switch]$SkipConfigCheck,
    [switch]$NoLauncher,
    [switch]$DiagnosticsOnly,
    [string]$DiagnosticReportPath = "run_logs\windows_setup_diagnostics.json",
    [switch]$CreateDesktopShortcuts
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
Set-Location -LiteralPath $ProjectRoot

$script:Diagnostics = [ordered]@{
    schema_version = "1.0"
    generated_at = (Get-Date).ToString("o")
    project_root = $ProjectRoot
    powershell = [ordered]@{
        version = $PSVersionTable.PSVersion.ToString()
        edition = $PSVersionTable.PSEdition
    }
    options = [ordered]@{
        use_china_mirror = [bool]$UseChinaMirror
        pip_index_url = $PipIndexUrl
        skip_dependency_install = [bool]$SkipDependencyInstall
        install_static_export = [bool]$InstallStaticExport
        install_skill_deps = [bool]$InstallSkillDeps
        install_webui_deps = [bool]$InstallWebUIDeps
        skip_config_check = [bool]$SkipConfigCheck
        no_launcher = [bool]$NoLauncher
        diagnostics_only = [bool]$DiagnosticsOnly
        create_desktop_shortcuts = [bool]$CreateDesktopShortcuts
    }
    python = $null
    checks = @()
}

function Add-DiagnosticCheck {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message,
        [hashtable]$Details = @{}
    )

    $script:Diagnostics.checks += [ordered]@{
        name = $Name
        status = $Status
        message = $Message
        details = $Details
    }
}

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
    Add-DiagnosticCheck -Name "setup" -Status "failed" -Message $Message
    Write-DiagnosticReport -Path $DiagnosticReportPath
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

    if ($DiagnosticsOnly) {
        return @{
            Python = $systemPython
            Kind = "system"
        }
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

function Write-DiagnosticReport {
    param([string]$Path)

    if (-not $Path) {
        return
    }

    $resolvedPath = $Path
    if (-not [System.IO.Path]::IsPathRooted($resolvedPath)) {
        $resolvedPath = Join-Path $ProjectRoot $resolvedPath
    }
    $resolvedPath = [System.IO.Path]::GetFullPath($resolvedPath)
    $parentDir = Split-Path -Parent $resolvedPath
    if ($parentDir -and -not (Test-Path -LiteralPath $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    $script:Diagnostics.generated_at = (Get-Date).ToString("o")
    $script:Diagnostics | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resolvedPath -Encoding UTF8
    Write-Ok "Diagnostic report: $resolvedPath"
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
        if ($InstallWebUIDeps) {
            $webuiRequirementsPath = Join-Path $ProjectRoot "requirements-webui.txt"
            if (Test-Path -LiteralPath $webuiRequirementsPath) {
                Write-Step "Installing optional Web UI dependencies from requirements-webui.txt"
                $webuiInstallArgs = @("-m", "pip", "install") + $indexArgs + @("-r", $webuiRequirementsPath)
                Invoke-Checked -FilePath $PythonExe -Arguments $webuiInstallArgs -FailureMessage "Optional Web UI dependency installation failed."
            }
            else {
                Write-Warn "requirements-webui.txt was not found; skipping optional Web UI dependencies."
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

    if ($InstallWebUIDeps) {
        $packages += @(
            "fastapi",
            "uvicorn[standard]",
            "python-multipart",
            "aiofiles"
        )
    }

    $installArgs = @("-m", "pip", "install") + $indexArgs + $packages
    Invoke-Checked -FilePath $PythonExe -Arguments $installArgs -FailureMessage "Dependency installation failed."
}

function Test-PythonImports {
    param(
        [string]$PythonExe,
        [switch]$NonFatal
    )

    Write-Step "Running Python import smoke test"
    $webuiImportModules = ""
    if ($InstallWebUIDeps) {
        $webuiImportModules = ", 'fastapi', 'uvicorn'"
    }
$code = @"
import importlib
import importlib.util
modules = [
    'click', 'pandas', 'numpy', 'scipy', 'skbio', 'yaml', 'Bio',
    'pydantic', 'plotly', 'rich'$webuiImportModules, 'agent_cli', 'process'
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
    & $PythonExe -c $code
    if ($LASTEXITCODE -ne 0) {
        $message = "Python import smoke test failed. Exit code: $LASTEXITCODE"
        Add-DiagnosticCheck -Name "python_imports" -Status "failed" -Message $message
        if ($NonFatal) {
            Write-Warn $message
            return
        }
        Stop-Setup $message
    }
    Add-DiagnosticCheck -Name "python_imports" -Status "passed" -Message "Required Python modules import successfully."
}

function Initialize-EnvFile {
    $envPath = Join-Path $ProjectRoot ".env"
    $examplePath = Join-Path $ProjectRoot ".env.example"

    Write-Step "Checking .env"
    if (Test-Path -LiteralPath $envPath) {
        Write-Ok ".env already exists."
        Add-DiagnosticCheck -Name "env_file" -Status "passed" -Message ".env already exists." -Details @{ path = $envPath }
        return
    }

    if (Test-Path -LiteralPath $examplePath) {
        Copy-Item -LiteralPath $examplePath -Destination $envPath
        Write-Warn ".env was created from .env.example. Edit it and set LLM_API_KEY before starting the Agent."
        Add-DiagnosticCheck -Name "env_file" -Status "warning" -Message ".env was created from .env.example." -Details @{ path = $envPath }
    }
    else {
        Write-Warn ".env.example was not found. Create .env manually before using the Agent."
        Add-DiagnosticCheck -Name "env_file" -Status "warning" -Message ".env.example was not found."
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
        Add-DiagnosticCheck -Name "usearch_executable" -Status "passed" -Message "USEARCH executable found." -Details @{ path = $usearchPath }
    }
    else {
        $message = "USEARCH not found at bin\windows\usearch.exe. If its license does not allow redistribution, users must place it there manually or set usearch_path in pipeline_params.yaml."
        Write-Warn $message
        Add-DiagnosticCheck -Name "usearch_executable" -Status "warning" -Message $message -Details @{ path = $usearchPath }
    }

    if (Test-Path -LiteralPath $vsearchPath) {
        Write-Ok "VSEARCH found: $vsearchPath"
        Add-DiagnosticCheck -Name "vsearch_executable" -Status "passed" -Message "VSEARCH executable found." -Details @{ path = $vsearchPath }
    }
    else {
        $message = "VSEARCH not found at bin\windows\vsearch.exe. Install it or set vsearch_path in pipeline_params.yaml."
        Write-Warn $message
        Add-DiagnosticCheck -Name "vsearch_executable" -Status "warning" -Message $message -Details @{ path = $vsearchPath }
    }

    if (Test-Path -LiteralPath $rdpPath) {
        Write-Ok "RDP database found: $rdpPath"
        Add-DiagnosticCheck -Name "rdp_database" -Status "passed" -Message "RDP database found." -Details @{ path = $rdpPath }
    }
    else {
        $message = "RDP database not found at databas\rdp_16s_v18.fa."
        Write-Warn $message
        Add-DiagnosticCheck -Name "rdp_database" -Status "warning" -Message $message -Details @{ path = $rdpPath }
    }

    if (Test-Path -LiteralPath $silvaPath) {
        Write-Ok "SILVA database found: $silvaPath"
        Add-DiagnosticCheck -Name "silva_database" -Status "passed" -Message "SILVA database found." -Details @{ path = $silvaPath }
    }
    else {
        $message = "SILVA database not found at databas\silva_16s_v123.fa. This is optional unless selected in pipeline_params.yaml."
        Write-Warn $message
        Add-DiagnosticCheck -Name "silva_database" -Status "warning" -Message $message -Details @{ path = $silvaPath }
    }
}

function Invoke-ConfigCheck {
    param([string]$PythonExe)

    $paramsPath = Join-Path $ProjectRoot "pipeline_params.yaml"
    if (-not (Test-Path -LiteralPath $paramsPath)) {
        Write-Warn "pipeline_params.yaml was not found; skipping pipeline config check."
        Add-DiagnosticCheck -Name "pipeline_config" -Status "skipped" -Message "pipeline_params.yaml was not found." -Details @{ path = $paramsPath }
        return
    }

    Write-Step "Running pipeline configuration check"
    & $PythonExe (Join-Path $ProjectRoot "process.py") check-pipeline-config --params $paramsPath
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Pipeline configuration check reported issues. Setup can still finish; fix pipeline_params.yaml before running analysis."
        Add-DiagnosticCheck -Name "pipeline_config" -Status "warning" -Message "Pipeline configuration check reported issues." -Details @{ path = $paramsPath; exit_code = $LASTEXITCODE }
    }
    else {
        Write-Ok "Pipeline configuration check passed."
        Add-DiagnosticCheck -Name "pipeline_config" -Status "passed" -Message "Pipeline configuration check passed." -Details @{ path = $paramsPath }
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
    Add-DiagnosticCheck -Name "launchers" -Status "passed" -Message "Created command-line launcher scripts." -Details @{
        agent = (Join-Path $ProjectRoot "run_agent.bat")
        process = (Join-Path $ProjectRoot "run_process.bat")
    }
}

function Write-DesktopShortcuts {
    Write-Step "Writing desktop shortcuts"

    $desktopPath = [Environment]::GetFolderPath("Desktop")
    if (-not $desktopPath) {
        Write-Warn "Desktop folder could not be resolved; skipping shortcuts."
        Add-DiagnosticCheck -Name "desktop_shortcuts" -Status "warning" -Message "Desktop folder could not be resolved."
        return
    }

    $agentLauncher = Join-Path $ProjectRoot "run_agent.bat"
    $processLauncher = Join-Path $ProjectRoot "run_process.bat"
    if (-not (Test-Path -LiteralPath $agentLauncher) -or -not (Test-Path -LiteralPath $processLauncher)) {
        Write-Warn "Launcher .bat files are missing; skipping desktop shortcuts."
        Add-DiagnosticCheck -Name "desktop_shortcuts" -Status "warning" -Message "Launcher .bat files are missing."
        return
    }

    $shell = New-Object -ComObject WScript.Shell
    $agentShortcut = $shell.CreateShortcut((Join-Path $desktopPath "X-Amplicon Agent.lnk"))
    $agentShortcut.TargetPath = $agentLauncher
    $agentShortcut.WorkingDirectory = $ProjectRoot
    $agentShortcut.Description = "Start the X-Amplicon Agent CLI"
    $agentShortcut.Save()

    $processShortcut = $shell.CreateShortcut((Join-Path $desktopPath "X-Amplicon CLI Help.lnk"))
    $processShortcut.TargetPath = $processLauncher
    $processShortcut.Arguments = "--help"
    $processShortcut.WorkingDirectory = $ProjectRoot
    $processShortcut.Description = "Show X-Amplicon process.py CLI help"
    $processShortcut.Save()

    Write-Ok "Created desktop shortcuts."
    Add-DiagnosticCheck -Name "desktop_shortcuts" -Status "passed" -Message "Created desktop shortcuts." -Details @{ desktop = $desktopPath }
}

if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) {
    Stop-Setup "This setup script is intended for Windows only."
}

Write-Host "X-Amplicon Windows setup" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

if ($DiagnosticsOnly) {
    Write-Warn "Diagnostics-only mode: no dependencies, .env file, launchers, or shortcuts will be created."
}

$pythonInfo = Resolve-ProjectPython
$pythonExe = [string]$pythonInfo.Python
$pythonKind = [string]$pythonInfo.Kind
$pythonVersion = Get-PythonVersion $pythonExe

Write-Step "Using Python"
Write-Ok "$pythonExe"
Write-Ok "Python $pythonVersion ($pythonKind)"
$script:Diagnostics.python = [ordered]@{
    executable = $pythonExe
    version = $pythonVersion.ToString()
    kind = $pythonKind
}
Add-DiagnosticCheck -Name "python" -Status "passed" -Message "Python resolved successfully." -Details @{
    executable = $pythonExe
    version = $pythonVersion.ToString()
    kind = $pythonKind
}

if ($pythonVersion -lt [version]"3.10.0") {
    Stop-Setup "Python $pythonVersion is too old. X-Amplicon requires Python 3.10+."
}

if ($DiagnosticsOnly) {
    Add-DiagnosticCheck -Name "dependency_install" -Status "skipped" -Message "Skipped because DiagnosticsOnly was set."
}
elseif (-not $SkipDependencyInstall) {
    Install-Dependencies $pythonExe
    Add-DiagnosticCheck -Name "dependency_install" -Status "passed" -Message "Dependency installation completed or requirements were already satisfied."
}
else {
    Write-Warn "Skipping dependency installation."
    Add-DiagnosticCheck -Name "dependency_install" -Status "skipped" -Message "Skipped because SkipDependencyInstall was set."
}

Test-PythonImports $pythonExe -NonFatal:$DiagnosticsOnly
if (-not $DiagnosticsOnly) {
    Initialize-EnvFile
}
else {
    $envPath = Join-Path $ProjectRoot ".env"
    $status = if (Test-Path -LiteralPath $envPath) { "passed" } else { "warning" }
    $message = if (Test-Path -LiteralPath $envPath) { ".env exists." } else { ".env is missing; copy .env.example to .env before using natural-language Agent mode." }
    Add-DiagnosticCheck -Name "env_file" -Status $status -Message $message -Details @{ path = $envPath }
}
Test-ProjectAssets

if (-not $SkipConfigCheck) {
    Invoke-ConfigCheck $pythonExe
}
else {
    Write-Warn "Skipping pipeline configuration check."
    Add-DiagnosticCheck -Name "pipeline_config" -Status "skipped" -Message "Skipped because SkipConfigCheck was set."
}

if ($DiagnosticsOnly) {
    Add-DiagnosticCheck -Name "launchers" -Status "skipped" -Message "Skipped because DiagnosticsOnly was set."
}
elseif (-not $NoLauncher) {
    Write-Launchers
}
else {
    Add-DiagnosticCheck -Name "launchers" -Status "skipped" -Message "Skipped because NoLauncher was set."
}

if ($CreateDesktopShortcuts -and -not $DiagnosticsOnly) {
    Write-DesktopShortcuts
}
elseif ($CreateDesktopShortcuts -and $DiagnosticsOnly) {
    Add-DiagnosticCheck -Name "desktop_shortcuts" -Status "skipped" -Message "Skipped because DiagnosticsOnly was set."
}

Write-DiagnosticReport -Path $DiagnosticReportPath

Write-Host ""
if ($DiagnosticsOnly) {
    Write-Host "Diagnostics finished." -ForegroundColor Green
}
else {
    Write-Host "Setup finished." -ForegroundColor Green
}
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

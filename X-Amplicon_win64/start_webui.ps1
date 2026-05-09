#requires -Version 5.1
<#
.SYNOPSIS
    Root-level shortcut for starting the X-Amplicon Web UI.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
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

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "webui\launcher\start_webui.ps1"

if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Error "Web UI launcher was not found: $Launcher"
    exit 1
}

& $Launcher `
    -BindHost $BindHost `
    -Port $Port `
    -FrontendPort $FrontendPort `
    -Dev:$Dev `
    -BuildFrontend:$BuildFrontend `
    -NoBuild:$NoBuild `
    -NoBrowser:$NoBrowser
exit $LASTEXITCODE

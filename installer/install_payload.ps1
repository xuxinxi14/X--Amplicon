#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$Destination
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "Payload zip was not found: $ZipPath"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$backupDir = Join-Path $Destination ".tools.local_backup"
if (Test-Path -LiteralPath $backupDir) {
    Remove-Item -LiteralPath $backupDir -Recurse -Force
}

$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if ($tar) {
    & $tar.Source -xf $ZipPath -C $Destination
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "tar.exe failed with exit code $exitCode"
    }
}
else {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
}

$legacyRoots = @(
    (Join-Path $Destination "X-Amplicon_main"),
    (Join-Path $Destination "X-Amplicon_win64")
)

$launcher = Join-Path $Destination "Start_X-Amplicon_WebUI.cmd"
foreach ($nestedRoot in $legacyRoots) {
    $nestedLauncher = Join-Path $nestedRoot "Start_X-Amplicon_WebUI.cmd"
    if ((-not (Test-Path -LiteralPath $launcher)) -and (Test-Path -LiteralPath $nestedLauncher)) {
        $nestedBackup = Join-Path $nestedRoot ".tools.local_backup"
        if (Test-Path -LiteralPath $nestedBackup) {
            Remove-Item -LiteralPath $nestedBackup -Recurse -Force
        }
        $robocopy = Join-Path $env:SystemRoot "System32\robocopy.exe"
        & $robocopy $nestedRoot $Destination /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1
        $exitCode = $LASTEXITCODE
        if ($exitCode -gt 7) {
            throw "robocopy failed with exit code $exitCode"
        }
        Remove-Item -LiteralPath $nestedRoot -Recurse -Force
    }
}

if (Test-Path -LiteralPath $backupDir) {
    Remove-Item -LiteralPath $backupDir -Recurse -Force
}

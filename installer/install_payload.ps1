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

$extractRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("xamplicon_payload_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null

try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $extractRoot -Force

    $nestedRoot = Join-Path $extractRoot "X-Amplicon_main"
    if (Test-Path -LiteralPath $nestedRoot) {
        $sourceRoot = $nestedRoot
    }
    else {
        $sourceRoot = $extractRoot
    }

    $robocopy = Join-Path $env:SystemRoot "System32\robocopy.exe"
    & $robocopy $sourceRoot $Destination /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1
    $exitCode = $LASTEXITCODE
    if ($exitCode -gt 7) {
        throw "robocopy failed with exit code $exitCode"
    }
}
finally {
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

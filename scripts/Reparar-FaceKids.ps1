#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python do FaceKids ausente.' }
Push-Location $root
try {
    & $python -m facekids.repair
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

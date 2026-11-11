#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$resultFile = Join-Path $env:ProgramData 'SafePCKids\deployment_result.json'
try {
    & (Join-Path $PSScriptRoot 'Preparar-Ambiente-SafePCKids.ps1')
    $root = Join-Path $env:ProgramFiles 'SafePCKids'
    Push-Location $root
    try {
        & (Join-Path $root '.venv\Scripts\python.exe') -m safepckids.repair
        if ($LASTEXITCODE -ne 0) { throw 'O reparo da integracao com Windows nao foi concluido.' }
    } finally {
        Pop-Location
    }
    $result = @{ ok = $true; install_root = $root; message = 'SafePCKids instalado e reparado.' }
} catch {
    $result = @{ ok = $false; message = $_.Exception.Message }
}
$null = New-Item -ItemType Directory -Path (Split-Path $resultFile) -Force
$result | ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding UTF8
if (-not $result.ok) { exit 1 }

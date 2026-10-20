#Requires -Version 5.1
<#
.SYNOPSIS
  One-command, opt-in Win+L camera capability diagnostic.
.NOTES
  Safe for the family PC: never installs services, credential providers,
  modifies registry or changes Windows passwords. Video stays in memory.
  It may create a local Python venv and install dependencies if missing.
  The program only measures frame availability in Win+L and cannot unlock.
#>
[CmdletBinding()]
param(
    [ValidateRange(10,600)][int]$Duration=120,
    [ValidateRange(0,10)][int]$CameraIndex=0
)
$ErrorActionPreference='Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'O teste precisa ser executado no Windows.'
}
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$branch=(& git -C $root branch --show-current)
$allowedBranches = @('main','feature/parent-face-pilot','feature/windows-native-unlock-poc')
if ($LASTEXITCODE -ne 0 -or $branch.Trim() -notin $allowedBranches) {
    throw "Branch nao validada para diagnostico Win+L: $branch"
}
$python=Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Preparando ambiente Python privado do projeto...'
    $launcher=Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Python Launcher (py.exe) nao encontrado. Instale Python 3.11.' }
    & py.exe -3.11 -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente Python 3.11.' }
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Python do projeto ausente.' }
& $python -c 'import cv2, numpy'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Instalando dependencias no ambiente virtual, sem modificar o Windows...'
    & $python -m pip install -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias.' }
}
Push-Location $root
try {
    Write-Host 'Testando estado WTS e regras sinteticas, sem capturar imagens...'
    & $python -m unittest discover -s tests -p 'test_hardware_camera_probe.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Teste de pre-condicao falhou.' }
    Write-Host ''
    Write-Host 'Agora voce pode pressionar Win+L e aguardar o teste.' -ForegroundColor Cyan
    Write-Host 'Nao feche o terminal antes do termino. Desbloqueie com sua senha usual.'
    Write-Host 'Nenhuma imagem, foto, modelo facial ou video sera salvo.'
    & $python -m facekids.hardware_camera_probe --duration $Duration --camera-index $CameraIndex
    if ($LASTEXITCODE -ne 0) { throw "Diagnostico encerrado com codigo $LASTEXITCODE." }
    Write-Host 'IMPORTANTE: apenas FRAMES_DURING_WIN_L_PRELIMINARY_ONLY evidencia frames no bloqueio.' -ForegroundColor Yellow
    Write-Host 'Nem esse resultado prova acesso confiavel ao LogonUI ou desbloqueio facial.' -ForegroundColor Yellow
} finally {
    Pop-Location
}
Write-Host 'PASS: diagnostico concluido. Nao houve alteracao de login.' -ForegroundColor Green

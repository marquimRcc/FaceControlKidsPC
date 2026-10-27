#Requires -Version 5.1
<#
  Adult self-enrollment and opt-in Win+L observation under the shared "Filhos"
  Windows account, WITHOUT installing providers/services or touching family DB.
  All facial data stays within THIS Windows user's LOCALAPPDATA lab directory.
#>
[CmdletBinding()]
param(
    [ValidateRange(0,10)][int]$CameraIndex = 0,
    [ValidateRange(10,300)][int]$VerifySeconds = 60,
    [ValidateRange(20,300)][int]$LockedSeconds = 90,
    [switch]$WinL,
    [switch]$ReEnroll
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Execute no Windows 10/11.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$branch = (& git -C $root branch --show-current)
if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne 'fix/facekids-ipc-security-hardening-20261024') {
    throw 'Use exclusivamente a branch de seguranca fix/facekids-ipc-security-hardening-20261024.'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$account = ($identity.Name -split '\\')[-1]
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($account -ine 'Filhos' -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Este piloto so pode rodar em PowerShell NORMAL, na conta Windows Filhos.'
}
if (-not $env:LOCALAPPDATA) {
    throw 'LOCALAPPDATA ausente: nao foi possivel separar os dados do laboratorio.'
}
$lab = Join-Path $env:LOCALAPPDATA 'FaceKids\laboratorio-adulto-filhos'
$db = Join-Path $lab 'adulto-teste.sqlite3'
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $created = $false
    foreach ($version in @('-3.11','-3.12','-3.13')) {
        if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) { break }
        & py.exe $version -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        & py.exe $version -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente Python isolado.' }
        $created = $true
        break
    }
    if (-not $created) { throw 'Python 3.11, 3.12 ou 3.13 necessario (py.exe).' }
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Python do projeto ausente.' }
& $python -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Ambiente Python incompativel (esperado 3.11-3.13).' }
& $python -c 'import cv2,numpy'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Preparando apenas dependencias do projeto, sem instalar componentes de login...'
    & $python -m pip install -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar bibliotecas no ambiente do projeto.' }
}
Push-Location $root
try {
    & $python -m unittest discover -s tests -p 'test_parent_face_pilot.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Pre-teste do reconhecimento facial falhou.' }
    if ($WinL) {
        & $python -m unittest discover -s tests -p 'test_locked_face_probe.py' -q
        if ($LASTEXITCODE -ne 0) { throw 'Pre-teste Win+L falhou.' }
    }
    $models = Join-Path $root 'models'
    if (-not (Test-Path -LiteralPath (Join-Path $models 'face_detection_yunet_2023mar.onnx')) -or
        -not (Test-Path -LiteralPath (Join-Path $models 'face_recognition_sface_2021dec.onnx'))) {
        & $python -m facekids.cli download-models
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar modelos de reconhecimento.' }
    }
    Write-Host 'TESTE FACIAL REAL - APENAS ROSTO DO RESPONSAVEL, USADO COMO PERFIL FICTICIO' -ForegroundColor Cyan
    Write-Host 'Conta Windows: Filhos. Nenhuma senha, login, servico, tarefa ou quota familiar sera alterada.'
    Write-Host 'O cadastro e guardado somente em LOCALAPPDATA\FaceKids\laboratorio-adulto-filhos.'
    $argsPilot = @('-m','facekids.parent_face_pilot',
        '--database',$db,'--models',$models,
        '--camera-index',"$CameraIndex",'--verify-seconds',"$VerifySeconds")
    if ($ReEnroll) { $argsPilot += '--re-enroll' }
    & $python @argsPilot
    if ($LASTEXITCODE -ne 0) { throw 'Cadastro/verificacao inconclusivos. Nao iniciar teste Win+L.' }
    Write-Host 'PASS: rosto adulto reconhecido ao vivo na conta Filhos (apenas diagnostico).' -ForegroundColor Green
    if ($WinL) {
        Write-Host 'Em seguida pressione Win+L manualmente, observe a camera por 40-60 segundos.' -ForegroundColor Yellow
        Write-Host 'Desbloqueie com seu PIN/senha habituais. Este diagnostico NAO desbloqueia o Windows.'
        & $python -m facekids.locked_face_probe --database $db --models $models --camera-index $CameraIndex --duration $LockedSeconds
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'Resultado Win+L inconclusivo. Leia o resumo; isto NAO reprova o login normal.'
            exit 4
        }
        Write-Host 'PASS: correspondencia facial observada durante Win+L (nao prova liveness/LogonUI).' -ForegroundColor Green
    }
} finally {
    Pop-Location
}
Write-Host 'Fim do piloto. Nao houve instalacao de componentes Windows.' -ForegroundColor Green

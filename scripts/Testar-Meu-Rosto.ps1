#Requires -Version 5.1
<#
  Piloto real de rosto do responsavel; sem alterar login ou instalar
  servicos. Executar com PowerShell NORMAL, sem elevar privilegios.
  Base: C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC
#>
[CmdletBinding()]
param(
    [ValidateRange(0,10)][int]$CameraIndex = 0,
    [ValidateRange(10,300)][int]$VerifySeconds = 60,
    [switch]$ReEnroll
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Este piloto requer Windows 10/11.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    $branch = (& git branch --show-current)
    if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne 'feature/parent-face-pilot') {
        throw "Branch incorreta: $branch. Selecione feature/parent-face-pilot."
    }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $candidates = @(
            @{Exe='py.exe'; Prefix=@('-3.11')},
            @{Exe='py.exe'; Prefix=@('-3.12')},
            @{Exe='py.exe'; Prefix=@('-3.13')},
            @{Exe='python.exe'; Prefix=@()}
        )
        $found = $false
        foreach ($option in $candidates) {
            if (-not (Get-Command $option.Exe -ErrorAction SilentlyContinue)) { continue }
            try {
                $prefix = @($option.Prefix)
                & $option.Exe @prefix -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
                if ($LASTEXITCODE -ne 0) { continue }
                Write-Host 'Preparando ambiente virtual Python local...'
                & $option.Exe @prefix -m venv (Join-Path $root '.venv')
                if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar o ambiente Python.' }
                $found = $true
                break
            } catch {
                Write-Warning "Python indisponivel nesta opcao: $($option.Exe) $($option.Prefix)"
            }
        }
        if (-not $found) {
            throw 'Nao foi encontrado Python 3.11, 3.12 ou 3.13. Instale Python e tente novamente.'
        }
    }
    & $python -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)'
    if ($LASTEXITCODE -ne 0) {
        throw 'O .venv existente tem Python incompativel; precisa ser 3.11 a 3.13.'
    }
    & $python -c 'import cv2,numpy'
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Instalando OpenCV e numpy APENAS no ambiente virtual do projeto...'
        & $python -m pip install -r (Join-Path $root 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias Python.' }
    }
    Write-Host 'Validando reconhecimento e estado do piloto...'
    & $python -m unittest discover -s tests -p 'test_parent_face_pilot.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Os autotestes do piloto falharam.' }
    $modelDir = Join-Path $root 'models'
    $det = Join-Path $modelDir 'face_detection_yunet_2023mar.onnx'
    $rec = Join-Path $modelDir 'face_recognition_sface_2021dec.onnx'
    if (-not ((Test-Path -LiteralPath $det) -and (Test-Path -LiteralPath $rec))) {
        Write-Host 'Baixando os modelos publicos YuNet e SFace para a pasta models...'
        & $python -m facekids.cli download-models
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar modelos de reconhecimento.' }
    }
    Write-Host ''
    Write-Host 'CADASTRO REAL DO SEU ROSTO - AMBIENTE DE TESTE' -ForegroundColor Cyan
    Write-Host 'Sem foto em disco, sem envio de biometria, sem mudar login, sem bloquear Windows.'
    Write-Host 'Os vetores faciais ficarao em LOCALAPPDATA\FaceKids\piloto-responsavel.'
    $arguments = @('-m','facekids.parent_face_pilot','--camera-index',"$CameraIndex",
                   '--verify-seconds',"$VerifySeconds")
    if ($ReEnroll) { $arguments += '--re-enroll' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Piloto finalizado sem sucesso (codigo $LASTEXITCODE)." }
    Write-Host 'PILOTO CONCLUIDO: agora compartilhe apenas as linhas VALIDACAO.' -ForegroundColor Green
} finally {
    Pop-Location
}

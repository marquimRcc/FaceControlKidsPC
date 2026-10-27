#Requires -Version 5.1
<#
 FaceKids: pilot for one or more configured profiles.
 Does NOT install services, edit logon, register scheduled tasks or
 automatically lock the Windows administrator.
 This script runs in the CURRENT Windows user's local data directory.
#>
[CmdletBinding()]
param([ValidateRange(0,10)][int]$CameraIndex=0)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Este piloto requer Windows 10/11.'
    }
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne 'developer') {
        throw "Branch incorreta: $branch; use exclusivamente a developer neste laboratorio."
    }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $launcher) { throw 'Python 3.11+ nao localizado; instale Python antes.' }
        & py.exe -3.11 -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar ambiente Python.' }
    }
    & $python -c 'import cv2,numpy'
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install -r (Join-Path $root 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias.' }
    }
    & $python -m unittest discover -s tests -p 'test_child*_pilot.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Autotestes do piloto falharam; interrompido.' }
    $models = Join-Path $root 'models'
    if (-not (Test-Path (Join-Path $models 'face_detection_yunet_2023mar.onnx')) -or
        -not (Test-Path (Join-Path $models 'face_recognition_sface_2021dec.onnx'))) {
        & $python -m facekids.cli download-models
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar modelos ONNX.' }
    }
    $currentUser=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    Write-Host ''
    Write-Host "FaceKids Piloto Infantil - usuario $currentUser" -ForegroundColor Cyan
    Write-Host 'Nenhum bloqueio Windows sera executado neste menu.'
    Write-Host 'Cadastro facial e quotas sao LOCAIS desta conta e ainda nao antiviolacao.'
    Write-Host 'Acompanhe pessoalmente cada cadastro e confirme consentimento dos responsaveis.'
    Write-Host 'A conta MarcosMiniPC mantem seu login normal.'
    while ($true) {
        Write-Host ''
        Write-Host '[1] Adicionar perfil'
        Write-Host '[2] Cadastrar rosto de um perfil existente'
        Write-Host '[3] Testar reconhecimento e cronometro por 90 segundos (SEM Win+L)'
        Write-Host '[4] Consultar cadastro e saldos'
        Write-Host '[5] Apagar dados faciais de um perfil (nao apaga quota)'
        Write-Host '[0] Sair'
        $choice=(Read-Host 'Selecione uma opcao').Trim()
        $arguments=@('--camera',"$CameraIndex")
        if ($choice -eq '1') {
            $alias=(Read-Host 'Apelido do novo perfil').Trim()
            $minutes=(Read-Host 'Limite diario em minutos (1..1440)').Trim()
            if ($alias.Length -lt 1 -or $alias.Length -gt 50 -or $minutes -notmatch '^\d+$' -or
                [int]$minutes -lt 1 -or [int]$minutes -gt 1440) {
                Write-Warning 'Apelido ou limite invalido'; continue
            }
            $arguments += @('add-profile',$alias,'--minutes',$minutes)
        } elseif ($choice -eq '2') {
            $idx=(Read-Host 'ID positivo do perfil').Trim()
            if ($idx -notmatch '^[1-9]\d*$') { Write-Warning 'Perfil invalido'; continue }
            $confirm = (Read-Host "O responsavel autorizou o cadastro do perfil $idx? Digite SIM").Trim()
            if ($confirm -cne 'SIM') { Write-Host 'Cadastro cancelado.'; continue }
            $arguments += @('enroll', $idx)
        } elseif ($choice -eq '3') {
            $arguments += @('monitor','--seconds','90')
        } elseif ($choice -eq '4') {
            $arguments += @('status')
        } elseif ($choice -eq '5') {
            $idx=(Read-Host 'ID positivo do perfil').Trim()
            if ($idx -notmatch '^[1-9]\d*$') { Write-Warning 'Perfil invalido'; continue }
            $confirm=(Read-Host "Para apagar os modelos do perfil $idx, digite APAGAR").Trim()
            if ($confirm -cne 'APAGAR') { continue }
            $arguments += @('erase',$idx)
        } elseif ($choice -eq '0') { break }
        else { Write-Warning 'Opcao invalida'; continue }
        & $python -m facekids.children_pilot @arguments
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Acao encerrada com codigo $LASTEXITCODE. Leia a mensagem acima."
        }
    }
} finally {
    Pop-Location
}

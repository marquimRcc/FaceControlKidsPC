#Requires -Version 5.1
<#
 FaceKids: pilot for 3 children, 120 minutes each.
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
    if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne 'feature/filhos-face-quota-pilot') {
        throw "Branch incorreta: $branch; atualize para feature/filhos-face-quota-pilot."
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
    Write-Host "FaceKids Piloto Infantil — usuario $currentUser" -ForegroundColor Cyan
    Write-Host 'Nenhum bloqueio Windows sera executado neste menu.'
    Write-Host 'Cadastro facial e quotas sao LOCAIS desta conta e ainda nao antiviolacao.'
    Write-Host 'Acompanhe pessoalmente cada cadastro e confirme consentimento dos responsaveis.'
    Write-Host 'A conta MarcosMiniPC mantem seu login normal.'
    while ($true) {
        Write-Host ''
        Write-Host '[1] Cadastrar rosto Crianca 1'
        Write-Host '[2] Cadastrar rosto Crianca 2'
        Write-Host '[3] Cadastrar rosto Crianca 3'
        Write-Host '[4] Testar reconhecimento e cronometro por 90 segundos (SEM Win+L)'
        Write-Host '[5] Consultar cadastro e saldos'
        Write-Host '[6] Apagar dados faciais de uma crianca (nao apaga quota)'
        Write-Host '[0] Sair'
        $choice=(Read-Host 'Selecione uma opcao').Trim()
        $arguments=@('--camera',"$CameraIndex")
        if ($choice -in @('1','2','3')) {
            $confirm = (Read-Host "O responsavel autorizou o cadastro da Crianca $choice? Digite SIM").Trim()
            if ($confirm -cne 'SIM') { Write-Host 'Cadastro cancelado.'; continue }
            $arguments += @('enroll', $choice)
        } elseif ($choice -eq '4') {
            $arguments += @('monitor','--seconds','90')
        } elseif ($choice -eq '5') {
            $arguments += @('status')
        } elseif ($choice -eq '6') {
            $idx=(Read-Host 'Numero do perfil (1/2/3)').Trim()
            if ($idx -notin @('1','2','3')) { Write-Warning 'Perfil invalido'; continue }
            $confirm=(Read-Host "Para apagar modelos da Crianca $idx, digite APAGAR").Trim()
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

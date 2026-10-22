#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Inicia o autenticador facial como SYSTEM ao ligar o PC, antes do logon.
.DESCRIPTION
  Usa o Credential Provider ja instalado, sem alterar senha, SID, quotas ou
  firewall. Mantem a tarefa interativa como contingencia. Nao reinicia o PC.
#>
[CmdletBinding()]
param([switch]$Desativar)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskName = 'FaceKidsBootAuth'

if ($Desativar) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Write-Host 'Boot facial desativado. A inicializacao interativa continua intacta.'
    return
}

$python = Join-Path $root '.venv\Scripts\python.exe'
$models = Join-Path $root 'models'
$dataDir = 'C:\ProgramData\FaceKids'
$required = @(
    $python,
    (Join-Path $root 'facekids\boot_auth.py'),
    (Join-Path $models 'face_detection_yunet_2023mar.onnx'),
    (Join-Path $models 'face_recognition_sface_2021dec.onnx'),
    (Join-Path $dataDir 'criancas.sqlite3'),
    (Join-Path $dataDir 'FaceKidsCredentialProvider.dll')
)
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo necessario ausente: $file. Instale/cadastre o FaceKids primeiro."
    }
}
$installedDll = [Text.Encoding]::ASCII.GetString(
    [IO.File]::ReadAllBytes((Join-Path $dataDir 'FaceKidsCredentialProvider.dll')))
if (-not $installedDll.Contains('FACEKIDS_IPC_V1') -or
    -not $installedDll.Contains('FACEKIDS_BOOT_RETRY_V1')) {
    throw 'Atualize o Credential Provider com Instalar-FaceKids-Nativo.ps1 antes de ativar o boot.'
}
if (-not (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{FAC0D042-3DD0-4A8C-9F18-440C44330C20}')) {
    throw 'Credential Provider FaceKids nao esta registrado. Execute o instalador principal primeiro.'
}

# Import check only: no webcam acquisition and no writes to the biometric DB.
Push-Location $root
try {
    & $python -c 'import cv2; import facekids.auth_service; import facekids.boot_auth'
    if ($LASTEXITCODE -ne 0) { throw 'Python/dependencias do autenticador indisponiveis.' }
} finally { Pop-Location }

$action = New-ScheduledTaskAction -Execute $python -WorkingDirectory $root -Argument '-m facekids.boot_auth'
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
$registered = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ([string]$registered.Principal.LogonType -ne 'ServiceAccount' -or
    $registered.Principal.UserId -notin @('SYSTEM', 'NT AUTHORITY\SYSTEM', 'S-1-5-18')) {
    throw 'Principal da tarefa de boot diferente de SYSTEM/ServiceAccount.'
}
Start-ScheduledTask -TaskName $taskName
Write-Host 'FaceKidsBootAuth configurado para iniciar ANTES do logon.' -ForegroundColor Green
Write-Host 'Reinicie quando desejar, aguarde a webcam e teste sem entrar no administrador.'
Write-Host 'Diagnostico: C:\ProgramData\FaceKids\boot_status.json e boot_events.jsonl'
Write-Host 'Se a camera for bloqueada pelo driver em Sessao 0, o log informara; nao ha garantia antes do teste real.'
Write-Host 'Para voltar: execute este script com -Desativar. Login normal nao foi alterado.'

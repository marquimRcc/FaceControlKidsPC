#Requires -Version 5.1
<#
 One-command VM-only developer refresh + interactive auth + IPC + face test.
 Does NOT register Windows Credential Provider, SCM, tasks or login policy.
#>
[CmdletBinding()]
param([switch]$SkipFaceProbe)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Somente Windows convidado VirtualBox.'
}
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$signature = [string]$computer.Manufacturer + ' ' + [string]$computer.Model
if ($signature -notmatch '(?i)VirtualBox|innotek') {
    throw 'Recusado: teste exclusivo da VM VirtualBox.'
}
$who = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($who.Split('\')[-1] -ieq 'Filhos') {
    throw 'Execute na conta administrativa da VM.'
}
$workspace = Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab'
$scriptDir = Join-Path $workspace 'scripts'
New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null
$bootstrap = Join-Path $scriptDir 'Iniciar-FaceKids-VM-Developer.ps1'
$stage = Join-Path $scriptDir 'FaceKids-VM-Autenticacao.ps1'
$base = 'https://raw.githubusercontent.com/marquimRcc/FaceControlKidsPC/developer/scripts/'
Write-Host '[1/4] Atualizando bootstrap e integracao a partir da developer...' -ForegroundColor Cyan
Invoke-WebRequest -UseBasicParsing -Uri ($base+'Iniciar-FaceKids-VM-Developer.ps1') -OutFile $bootstrap
Invoke-WebRequest -UseBasicParsing -Uri ($base+'FaceKids-VM-Autenticacao.ps1') -OutFile $stage
Write-Host '[2/4] Sincronizando codigo e Python VM (sem abrir painel)...' -ForegroundColor Cyan
& $bootstrap -SkipTests -NoCameraProbe -NoDashboard
Write-Host '[3/4] Iniciando autenticador INTERATIVO de laboratorio...' -ForegroundColor Cyan
& $stage -Action StartAuth
Write-Host '[4/4] Verificando comunicacao IPC...' -ForegroundColor Cyan
& $stage -Action Ping
if (-not $SkipFaceProbe) {
    Write-Host 'Olhe para a webcam. Um unico rosto cadastrado deve estar visivel.' -ForegroundColor Yellow
    & $stage -Action FaceProbe
}
Write-Host ''
Write-Host 'FASE DE DIAGNOSTICO CONCLUIDA. CP e SCM NAO foram instalados.' -ForegroundColor Green
Write-Host ('Script salvo em: '+$stage)
Write-Host 'Nao feche a sessao administrativa antes de testar o comportamento da camera.'

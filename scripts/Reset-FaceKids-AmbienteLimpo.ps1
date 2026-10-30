<#
.SYNOPSIS
  Script de Reset Completo do FaceKids para simulacao de Maquina Formatada.
#>
[CmdletBinding()]
param(
    [switch]$SkipProgramDataClean
)

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FaceKids - Reset Completo para Simulacao de Maquina Limpa" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Parar processos Python do FaceKids (excluindo este processo)
Write-Host "1. Parando processos Python do FaceKids em execucao..." -ForegroundColor Yellow
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.Name -match "^python" -and
    ($_.CommandLine -match "facekids" -or $_.CommandLine -match "auth_service" -or $_.CommandLine -match "filhos_agent" -or $_.CommandLine -match "boot_auth")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 2. Desregistrar e deletar tarefas agendadas
Write-Host "2. Removendo tarefas agendadas do Windows..." -ForegroundColor Yellow
@('FaceKidsAuthService', 'FaceKidsFilhosAgent', 'FaceKidsBootAuth') | ForEach-Object {
    Stop-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $_ -Confirm:$false -ErrorAction SilentlyContinue
    & schtasks.exe /delete /tn $_ /f 2>&1 | Out-Null
}

# 3. Desregistrar DLL do Credential Provider
Write-Host "3. Desregistrando DLL do LogonUI via regsvr32..." -ForegroundColor Yellow
$dllPath = "C:\ProgramData\FaceKids\FaceKidsCredentialProvider.dll"
if (Test-Path -LiteralPath $dllPath) {
    Start-Process -FilePath "regsvr32.exe" -ArgumentList "/u /s `"$dllPath`"" -Wait
}

# 4. Limpar chaves de Registro
Write-Host "4. Limpando chaves do Registro HKLM..." -ForegroundColor Yellow
$clsid = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\FaceControlKidsPC" -Recurse -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "FaceKidsAuthService" -Force -ErrorAction SilentlyContinue

# 5. Limpar Startup scripts
Write-Host "5. Removendo scripts dos Startups..." -ForegroundColor Yellow
$userStartupVbs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\FaceKidsAuthService.vbs"
$globalStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\FaceKidsAuthService.vbs'
$agentStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\FaceKidsFilhosAgent.vbs'
@($userStartupVbs, $globalStartupVbs, $agentStartupVbs) | ForEach-Object {
    if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force -ErrorAction SilentlyContinue }
}

# 6. Limpar pasta C:\ProgramData\FaceKids
if (-not $SkipProgramDataClean) {
    Write-Host "6. Limpando arquivos residuais de C:\ProgramData\FaceKids..." -ForegroundColor Yellow
    if (Test-Path "C:\ProgramData\FaceKids") {
        Get-ChildItem "C:\ProgramData\FaceKids" | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "Reset concluido com sucesso!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

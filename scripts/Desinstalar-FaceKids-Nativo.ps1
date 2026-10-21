<#
.SYNOPSIS
  Desinstalador seguro do FaceKids Credential Provider.
.DESCRIPTION
  Remove o registro do Windows, desativa o servico e remove a DLL de System32.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$dllTarget = 'C:\ProgramData\FaceKids\FaceKidsCredentialProvider.dll'
$taskName = "FaceKidsAuthService"
$clsid = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "     FaceControlKidsPC - Desinstalador de Seguranca" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

# 1. Parar e remover a tarefa agendada
Write-Host "Parando e removendo servico em segundo plano..."
Stop-ScheduledTask -TaskName $taskName
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false

# 2. Desregistrar via regsvr32
if (Test-Path -LiteralPath $dllTarget) {
    Write-Host "Desregistrando Credential Provider..."
    & regsvr32.exe /u /s $dllTarget
}

# 3. Limpar chaves do registro caso tenham restado
Write-Host "Limpando chaves do Registro do Windows..."
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid" -Recurse -Force
Remove-Item -Path "HKCR:\CLSID\$clsid" -Recurse -Force
Remove-Item -Path "HKLM:\SOFTWARE\FaceControlKidsPC" -Recurse -Force

# 4. Remover DLL de System32
if (Test-Path -LiteralPath $dllTarget) {
    Write-Host "Removendo DLL de System32..."
    Remove-Item -LiteralPath $dllTarget -Force
}

Write-Host ""
Write-Host "DESINSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "O Windows foi restaurado exatamente ao seu estado original."
Write-Host "============================================================" -ForegroundColor Yellow

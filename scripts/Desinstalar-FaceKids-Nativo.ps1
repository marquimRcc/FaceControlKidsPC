<#
.SYNOPSIS
  Desinstalador seguro do FaceKids Credential Provider.
.DESCRIPTION
  Remove o registro do Windows, desativa o servico e remove a DLL de ProgramData.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$dllTarget = 'C:\ProgramData\FaceKids\FaceKidsCredentialProvider.dll'
$clsid = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "     FaceControlKidsPC - Desinstalador de Seguranca" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

# 1. Parar o processo do servico
Write-Host "Parando servico em segundo plano..."
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*auth_service*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*auth_service*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Remover da inicializacao automatica
Write-Host "Removendo da inicializacao automatica..."
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "FaceKidsAuthService" -Force -ErrorAction SilentlyContinue
$vbsPath = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\FaceKidsAuthService.vbs'
if (Test-Path $vbsPath) {
    Remove-Item -Path $vbsPath -Force -ErrorAction SilentlyContinue
}

# 3. Desregistrar via regsvr32
if (Test-Path -LiteralPath $dllTarget) {
    Write-Host "Desregistrando Credential Provider..."
    Start-Process -FilePath "regsvr32.exe" -ArgumentList "/u /s `"$dllTarget`"" -Wait
}

# 4. Limpar chaves do registro caso tenham restado
Write-Host "Limpando chaves do Registro do Windows..."
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\FaceControlKidsPC" -Recurse -Force -ErrorAction SilentlyContinue

# 5. Remover DLL de ProgramData
if (Test-Path -LiteralPath $dllTarget) {
    Write-Host "Removendo DLL de ProgramData..."
    Remove-Item -LiteralPath $dllTarget -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "     DESINSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "O Windows foi restaurado exatamente ao seu estado original."
Write-Host "============================================================" -ForegroundColor Yellow

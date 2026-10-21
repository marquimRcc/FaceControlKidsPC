<#
.SYNOPSIS
  Desinstalador seguro e completo do FaceKids Credential Provider e servicos associados.
.DESCRIPTION
  Remove o registro do Windows, desativa servicos e tarefas agendadas, e limpa arquivos de execucao.
  Preserva intactos os bancos de dados biometricos e cadastros dos filhos.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$dllTarget = 'C:\ProgramData\FaceKids\FaceKidsCredentialProvider.dll'
$clsid = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "     FaceControlKidsPC - Desinstalador de Seguranca" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

$checklist = [ordered]@{}

# 1. Parar processos do FaceKids (auth_service e filhos_agent)
Write-Host "1. Parando processos em segundo plano..." -ForegroundColor Cyan
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { 
    $_.CommandLine -like "*auth_service*" -or $_.CommandLine -like "*filhos_agent*" 
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Milliseconds 500
$remainingProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { 
    $_.CommandLine -like "*auth_service*" -or $_.CommandLine -like "*filhos_agent*" 
})
$checklist["Processos em segundo plano encerrados"] = ($remainingProcs.Count -eq 0)

# 2. Remover tarefas agendadas do Windows (schtasks)
Write-Host "2. Removendo tarefas agendadas..." -ForegroundColor Cyan
& schtasks.exe /delete /tn "FaceKidsAuthService" /f 2>&1 | Out-Null
& schtasks.exe /delete /tn "FaceKidsFilhosAgent" /f 2>&1 | Out-Null
$tasksOutput = & schtasks.exe /query /fo csv 2>&1 | Out-String
$checklist["Tarefa FaceKidsAuthService removida"] = ($tasksOutput -notmatch "FaceKidsAuthService")
$checklist["Tarefa FaceKidsFilhosAgent removida"] = ($tasksOutput -notmatch "FaceKidsFilhosAgent")

# 3. Remover entradas de inicializacao automatica (Startup / Run)
Write-Host "3. Removendo scripts de inicializacao..." -ForegroundColor Cyan
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "FaceKidsAuthService" -Force -ErrorAction SilentlyContinue

$userStartupVbs = Join-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" "FaceKidsAuthService.vbs"
if (Test-Path -LiteralPath $userStartupVbs) {
    Remove-Item -LiteralPath $userStartupVbs -Force -ErrorAction SilentlyContinue
}
$checklist["VBS do Startup do usuario removido"] = (-not (Test-Path -LiteralPath $userStartupVbs))

$globalStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\FaceKidsAuthService.vbs'
if (Test-Path -LiteralPath $globalStartupVbs) {
    Remove-Item -LiteralPath $globalStartupVbs -Force -ErrorAction SilentlyContinue
}
$checklist["VBS do Startup global removido"] = (-not (Test-Path -LiteralPath $globalStartupVbs))

# 4. Desregistrar via regsvr32
if (Test-Path -LiteralPath $dllTarget) {
    Write-Host "4. Desregistrando Credential Provider..." -ForegroundColor Cyan
    Start-Process -FilePath "regsvr32.exe" -ArgumentList "/u /s `"$dllTarget`"" -Wait
}

# 5. Limpar chaves do Registro do Windows
Write-Host "5. Limpando chaves do Registro..." -ForegroundColor Cyan
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\FaceControlKidsPC" -Recurse -Force -ErrorAction SilentlyContinue

$regCp = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
$regClsid = Test-Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid"
$checklist["Chave Credential Provider no registro removida"] = (-not $regCp)
$checklist["Chave CLSID COM no registro removida"] = (-not $regClsid)

# 6. Remover scripts batch e DLL de ProgramData (preservando banco de dados/fotos)
Write-Host "6. Limpando arquivos de execucao de ProgramData..." -ForegroundColor Cyan
if (Test-Path -LiteralPath $dllTarget) {
    Remove-Item -LiteralPath $dllTarget -Force -ErrorAction SilentlyContinue
}
$checklist["DLL FaceKidsCredentialProvider.dll removida"] = (-not (Test-Path -LiteralPath $dllTarget))

$filesToClean = @(
    "C:\ProgramData\FaceKids\iniciar-filhos-agent.bat",
    "C:\ProgramData\FaceKids\iniciar-auth-service.bat",
    "C:\ProgramData\FaceKids\last_unlock.json",
    "C:\ProgramData\FaceKids\auth_service.pid"
)
foreach ($f in $filesToClean) {
    if (Test-Path -LiteralPath $f) {
        Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "              RELATORIO DE DESINSTALACAO" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
$allPassed = $true
foreach ($item in $checklist.Keys) {
    $ok = $checklist[$item]
    if ($ok) {
        Write-Host " [OK]    $item" -ForegroundColor Green
    } else {
        Write-Host " [AVISO] $item (requer verificacao manual)" -ForegroundColor Red
        $allPassed = $false
    }
}
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host " [PRESERVADO] Banco de dados e fotos em C:\ProgramData\FaceKids" -ForegroundColor Cyan
Write-Host " [PRESERVADO] Contas Windows (MarcosMiniPC e Filhos) intactas" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Yellow

if ($allPassed) {
    Write-Host "DESINSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
    Write-Host "O logon convencional do Windows continua 100% disponivel." -ForegroundColor Green
} else {
    Write-Host "DESINSTALACAO CONCLUIDA COM AVISOS PONTUAIS." -ForegroundColor Yellow
}

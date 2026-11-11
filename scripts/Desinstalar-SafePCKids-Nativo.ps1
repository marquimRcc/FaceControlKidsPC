<#
.SYNOPSIS
  Desinstalador seguro e completo do SafePCKids Credential Provider e servicos associados.
.DESCRIPTION
  Remove o registro do Windows, desativa servicos e tarefas agendadas, e limpa arquivos de execucao.
  Preserva intactos os bancos de dados biometricos e cadastros dos filhos.
#>
[CmdletBinding()]
param(
    [switch]$RemoveData,
    [switch]$RemoveWindowsUser
)

$ErrorActionPreference = 'SilentlyContinue'
$dllTarget = 'C:\ProgramData\SafePCKids\SafePCKidsCredentialProvider.dll'
$clsid = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "     SafePCKids - Desinstalador de Seguranca" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

$checklist = [ordered]@{}

# Stop the supervisor BEFORE its workers, otherwise it would recreate them.
Stop-ScheduledTask -TaskName 'SafePCKidsBootAuth' -ErrorAction SilentlyContinue
& schtasks.exe /delete /tn "SafePCKidsBootAuth" /f 2>&1 | Out-Null

# 1. Parar processos do SafePCKids (auth_service e filhos_agent)
Write-Host "1. Parando processos em segundo plano..." -ForegroundColor Cyan
& taskkill.exe /F /IM SafePCKids-Instalador.exe /T 2>&1 | Out-Null
& taskkill.exe /F /IM pythonw.exe /T 2>&1 | Out-Null
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { 
    $_.CommandLine -like "*auth_service*" -or $_.CommandLine -like "*filhos_agent*" -or $_.CommandLine -like "*-m safepckids.boot_auth*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Milliseconds 500
$remainingProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { 
    $_.CommandLine -like "*auth_service*" -or $_.CommandLine -like "*filhos_agent*" -or $_.CommandLine -like "*-m safepckids.boot_auth*"
})
$checklist["Processos em segundo plano encerrados"] = ($remainingProcs.Count -eq 0)

# 2. Remover tarefas agendadas do Windows (schtasks)
Write-Host "2. Removendo tarefas agendadas..." -ForegroundColor Cyan
& schtasks.exe /delete /tn "SafePCKidsAuthService" /f 2>&1 | Out-Null
& schtasks.exe /delete /tn "SafePCKidsFilhosAgent" /f 2>&1 | Out-Null
$tasksOutput = & schtasks.exe /query /fo csv 2>&1 | Out-String
$checklist["Tarefa SafePCKidsAuthService removida"] = ($tasksOutput -notmatch "SafePCKidsAuthService")
$checklist["Tarefa SafePCKidsFilhosAgent removida"] = ($tasksOutput -notmatch "SafePCKidsFilhosAgent")
$checklist["Tarefa SafePCKidsBootAuth removida"] = ($tasksOutput -notmatch "SafePCKidsBootAuth")

# 3. Remover entradas de inicializacao automatica (Startup / Run)
Write-Host "3. Removendo scripts de inicializacao..." -ForegroundColor Cyan
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "SafePCKidsAuthService" -Force -ErrorAction SilentlyContinue

$userStartupVbs = Join-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" "SafePCKidsAuthService.vbs"
if (Test-Path -LiteralPath $userStartupVbs) {
    Remove-Item -LiteralPath $userStartupVbs -Force -ErrorAction SilentlyContinue
}
$checklist["VBS do Startup do usuario removido"] = (-not (Test-Path -LiteralPath $userStartupVbs))

$globalStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\SafePCKidsAuthService.vbs'
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
Remove-Item -Path "HKLM:\SOFTWARE\SafePCKids" -Recurse -Force -ErrorAction SilentlyContinue

$regCp = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
$regClsid = Test-Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid"
$checklist["Chave Credential Provider no registro removida"] = (-not $regCp)
$checklist["Chave CLSID COM no registro removida"] = (-not $regClsid)

# 6. Remover scripts batch e DLL de ProgramData (preservando banco de dados/fotos)
Write-Host "6. Limpando arquivos de execucao de ProgramData..." -ForegroundColor Cyan
if (Test-Path -LiteralPath $dllTarget) {
    Remove-Item -LiteralPath $dllTarget -Force -ErrorAction SilentlyContinue
}
$checklist["DLL SafePCKidsCredentialProvider.dll removida"] = (-not (Test-Path -LiteralPath $dllTarget))

$filesToClean = @(
    "C:\ProgramData\SafePCKids\iniciar-filhos-agent.bat",
    "C:\ProgramData\SafePCKids\iniciar-auth-service.bat",
    "C:\ProgramData\SafePCKids\last_unlock.json",
    "C:\ProgramData\SafePCKids\auth_service.pid"
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
if ($RemoveData) {
    Write-Host "Removendo todos os dados em C:\ProgramData\SafePCKids..." -ForegroundColor Cyan
    cmd.exe /c "rd /s /q C:\ProgramData\SafePCKids" 2>&1 | Out-Null
    Remove-Item -LiteralPath "C:\ProgramData\SafePCKids" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host " [REMOVIDO] Banco de dados e fotos em C:\ProgramData\SafePCKids" -ForegroundColor Yellow
} else {
    Write-Host " [PRESERVADO] Banco de dados e fotos em C:\ProgramData\SafePCKids" -ForegroundColor Cyan
}
if ($RemoveWindowsUser) {
    Write-Host "Removendo conta Windows 'Filhos'..." -ForegroundColor Cyan
    & net user Filhos /delete 2>&1 | Out-Null
    Write-Host " [REMOVIDO] Conta Windows Filhos excluida" -ForegroundColor Yellow
} else {
    Write-Host " [PRESERVADO] Contas Windows (MarcosMiniPC e Filhos) intactas" -ForegroundColor Cyan
}
Write-Host "============================================================" -ForegroundColor Yellow

if ($allPassed) {
    Write-Host "DESINSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
    Write-Host "O logon convencional do Windows continua 100% disponivel." -ForegroundColor Green
} else {
    Write-Host "DESINSTALACAO CONCLUIDA COM AVISOS PONTUAIS." -ForegroundColor Yellow
}

<#
.SYNOPSIS
  Instalador do FaceKids Credential Provider nativo e Agente de Boas-Vindas.
.DESCRIPTION
  1. Copia FaceKidsCredentialProvider.dll para C:\ProgramData\FaceKids\
  2. Registra o CLSID com regsvr32.
  3. Configura o servico de autenticacao facial (Named Pipe).
  4. Configura o Agente de Sessao da conta Filhos (Tela de Boas-Vindas com Foto).
  5. Inicia os servicos em segundo plano.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dllSource = Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll'
$programDataDir = 'C:\ProgramData\FaceKids'
$dllTarget = Join-Path $programDataDir 'FaceKidsCredentialProvider.dll'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$requiredProtocolMarker = 'FACEKIDS_IPC_V1'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     FaceControlKidsPC - Instalador de Desbloqueio Facial" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Verificar se a DLL existe e corresponde ao contrato IPC atual.
# O repositorio distribui uma DLL pronta, mas nunca devemos instalar um binario
# antigo junto com um auth_service novo e incompatível.
$dllNeedsBuild = -not (Test-Path -LiteralPath $dllSource)
if (-not $dllNeedsBuild) {
    try {
        $dllAscii = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($dllSource))
        $dllNeedsBuild = -not $dllAscii.Contains($requiredProtocolMarker)
    } catch {
        $dllNeedsBuild = $true
    }
}

if ($dllNeedsBuild) {
    Write-Host "Compilando FaceKidsCredentialProvider.dll..." -ForegroundColor Yellow
    $buildScript = Join-Path $root 'native\credential_provider_facekids\build.ps1'
    & powershell -ExecutionPolicy Bypass -File $buildScript
    if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao da DLL." }

    $rebuiltDllAscii = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($dllSource))
    if (-not $rebuiltDllAscii.Contains($requiredProtocolMarker)) {
        throw "DLL compilada nao contem o marcador de protocolo $requiredProtocolMarker. Instalacao interrompida."
    }
}

# 2. Copiar DLL para ProgramData\FaceKids
Write-Host "Copiando DLL para $programDataDir..." -ForegroundColor Yellow
if (-not (Test-Path $programDataDir)) {
    New-Item -ItemType Directory -Path $programDataDir -Force | Out-Null
}
Copy-Item -LiteralPath $dllSource -Destination $dllTarget -Force

# 3. Registrar DLL via regsvr32 com Start-Process para aguardar a conclusao
Write-Host "Registrando Credential Provider no Windows..." -ForegroundColor Yellow
$regProc = Start-Process -FilePath "regsvr32.exe" -ArgumentList "/s `"$dllTarget`"" -Wait -PassThru
if ($regProc.ExitCode -ne 0) {
    throw "Falha ao registrar a DLL com regsvr32 (codigo $($regProc.ExitCode))."
}
Write-Host "DLL registrada no sistema com sucesso!" -ForegroundColor Green

# 4. Configurar SID da conta Filhos no registro
try {
    $filhosUser = Get-LocalUser -Name "Filhos" -ErrorAction SilentlyContinue
    if ($filhosUser) {
        $regPath = "HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider"
        if (-not (Test-Path $regPath)) {
            New-Item -Path $regPath -Force -ErrorAction SilentlyContinue | Out-Null
        }
        Set-ItemProperty -Path $regPath -Name "TargetUserSid" -Value $filhosUser.SID.Value -Force -ErrorAction SilentlyContinue
        Write-Host "SID da conta Filhos configurado: $($filhosUser.SID.Value)" -ForegroundColor Green
    }
} catch {
    Write-Host "SID sera resolvido dinamicamente pela DLL." -ForegroundColor DarkGray
}

# 5. Configurar inicializacao automatica do servico (Named Pipe)
Write-Host "Configurando servico em segundo plano (Named Pipe)..." -ForegroundColor Yellow

# Limpeza: Remover qualquer script legado do Startup global
$globalStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\FaceKidsAuthService.vbs'
if (Test-Path -LiteralPath $globalStartupVbs) {
    Remove-Item -LiteralPath $globalStartupVbs -Force -ErrorAction SilentlyContinue
    Write-Host "Script legado removido do Startup global." -ForegroundColor Green
}

# Limpeza: Remover chave de Run global HKLM
try {
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "FaceKidsAuthService" -Force -ErrorAction SilentlyContinue
} catch {}

# Criar script de execucao do servico e tarefa vinculada ao usuario/sessao
# interativa que executa este instalador. Isso preserva acesso DirectShow a
# webcam e evita a ambiguidade de /sc onlogon sem principal explicito.
$serviceBat = "C:\ProgramData\FaceKids\iniciar-auth-service.bat"
$serviceContent = @"
@echo off
cd /d "$root"
set PYTHONPATH=$root
start "" "$pythonw" -m facekids.auth_service
"@
Set-Content -Path $serviceBat -Value $serviceContent -Encoding ASCII -Force

try {
    $authServiceUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $authAction = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$serviceBat`""
    $authTrigger = New-ScheduledTaskTrigger -AtLogOn -User $authServiceUser
    $authPrincipal = New-ScheduledTaskPrincipal -UserId $authServiceUser -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName 'FaceKidsAuthService' -Action $authAction -Trigger $authTrigger -Principal $authPrincipal -Force | Out-Null

    $registeredTask = Get-ScheduledTask -TaskName 'FaceKidsAuthService' -ErrorAction Stop
    $regUser = if ($registeredTask.Principal.UserId) { $registeredTask.Principal.UserId.Split('\')[-1] } else { '' }
    $expectedUser = $authServiceUser.Split('\')[-1]
    if ($regUser -ne $expectedUser -or
        [string]$registeredTask.Principal.LogonType -ne 'Interactive') {
        throw "A tarefa FaceKidsAuthService nao ficou vinculada ao usuario/sessao interativa esperada."
    }
    Write-Host "Tarefa FaceKidsAuthService vinculada a sessao interativa de $authServiceUser (privilegios elevados)." -ForegroundColor Green
} catch {
    throw "Falha ao configurar FaceKidsAuthService na sessao interativa: $($_.Exception.Message)"
}

# Configurar script VBS de contingencia no Startup
$userStartup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$root"
WshShell.Run """$pythonw"" -m facekids.auth_service", 0, False
"@

try {
    $userVbs = Join-Path $userStartup 'FaceKidsAuthService.vbs'
    Set-Content -Path $userVbs -Value $vbsContent -Encoding ASCII -Force
    Write-Host "Inicializacao de contingencia configurada ($userVbs)." -ForegroundColor Green
} catch {
    Write-Host "Aviso ao salvar no Startup do usuario: $($_.Exception.Message)" -ForegroundColor DarkGray
}

# 6. Configurar Agente de Sessao da conta Filhos (Tela de Boas-Vindas e Quota)
Write-Host "Configurando Agente de Sessao da conta Filhos..." -ForegroundColor Yellow

# Garantir permissoes NTFS para que a conta Filhos possa executar o Python e o agente
try {
    & icacls "$env:USERPROFILE" /grant "Filhos:(RX)" 2>&1 | Out-Null
    & icacls "$env:LOCALAPPDATA\Programs\Python" /grant "Filhos:(OI)(CI)(RX)" /T 2>&1 | Out-Null
    & icacls (Split-Path $root -Parent) /grant "Filhos:(RX)" 2>&1 | Out-Null
    & icacls $root /grant "Filhos:(OI)(CI)(RX)" /T 2>&1 | Out-Null
    & icacls $programDataDir /grant "Filhos:(OI)(CI)(M)" /T 2>&1 | Out-Null
} catch {}
$agentBat = "C:\ProgramData\FaceKids\iniciar-filhos-agent.bat"
$agentContent = @"
@echo off
if /i "%USERNAME%" neq "Filhos" exit /b
cd /d "C:\ProgramData\FaceKids"
set PYTHONPATH=$root
start "" "$pythonw" -m facekids.filhos_agent
"@
Set-Content -Path $agentBat -Value $agentContent -Encoding ASCII -Force

# Agendar somente o agente da conta Filhos, sem senha nos argumentos.
# A tarefa usa o token interativo depois que Filhos ja estiver logada.
# Validar na VM antes de atualizar o PC familiar.
try {
    $childAccount = Get-LocalUser -Name 'Filhos' -ErrorAction Stop
    if (-not $childAccount.Enabled) { throw 'Conta Filhos desabilitada.' }
    $agentArgs = '/c ' + [char]34 + $agentBat + [char]34
    $agentAction = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $agentArgs
    $agentTrigger = New-ScheduledTaskTrigger -AtLogOn -User $childAccount.Name
    $agentPrincipal = New-ScheduledTaskPrincipal -UserId $childAccount.SID.Value -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -Action $agentAction -Trigger $agentTrigger -Principal $agentPrincipal -Force -ErrorAction Stop | Out-Null
    $registeredAgent = Get-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -ErrorAction Stop
    if ([string]$registeredAgent.Principal.LogonType -ne 'Interactive') {
        throw 'Agendamento do agente nao ficou em modo interativo.'
    }
    Write-Host "Agente Filhos agendado sem senha na linha de comando." -ForegroundColor Green
} catch {
    throw "Nao foi possivel registrar o agente Filhos com seguranca: $($_.Exception.Message)"
}

# 7. Iniciar os servicos em segundo plano
Write-Host "Iniciando servicos em segundo plano..." -ForegroundColor Yellow
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Where-Object { $_.CommandLine -like "*auth_service*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Start-Process -FilePath $pythonw -ArgumentList "-m facekids.auth_service" -WorkingDirectory $root
Start-Sleep -Seconds 1

# Nota: FaceKidsFilhosAgent iniciara automaticamente quando a conta Filhos fizer logon (/sc onlogon).

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "     INSTALACAO E ATUALIZACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "- DLL ativa em: $dllTarget"
Write-Host "- Servico de autenticacao facial rodando em segundo plano."
Write-Host "- Agente dos Filhos ativo para exibir a Tela de Boas-Vindas com Foto."
Write-Host "- O login tradicional do Windows nao foi desativado pelo instalador."
Write-Host "============================================================" -ForegroundColor Cyan

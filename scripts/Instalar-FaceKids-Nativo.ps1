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
$python = Join-Path $root '.venv\Scripts\python.exe'
$requiredProtocolMarker = 'FACEKIDS_IPC_V1'
$brave = 'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     FaceControlKidsPC - Instalador de Desbloqueio Facial" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $brave)) {
    throw 'Brave nao foi encontrado para a conta Filhos.'
}

# 1. Verificar se a DLL existe e corresponde ao contrato IPC atual.
# O repositorio distribui uma DLL pronta, mas nunca devemos instalar um binario
# antigo junto com um auth_service novo e incompatível.
$dllNeedsBuild = -not (Test-Path -LiteralPath $dllSource)
if (-not $dllNeedsBuild) {
    try {
        $dllAscii = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($dllSource))
        $dllNeedsBuild = -not $dllAscii.Contains($requiredProtocolMarker)
        $dllNeedsBuild = $dllNeedsBuild -or -not $dllAscii.Contains('FACEKIDS_BOOT_RETRY_V1')
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
    if (-not $rebuiltDllAscii.Contains('FACEKIDS_BOOT_RETRY_V1')) {
        throw 'DLL sem repeticao automatica do boot. Instalacao interrompida.'
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
    $registeredLogonType = [string]$registeredTask.Principal.LogonType
    if ($regUser -ne $expectedUser -or
        $registeredLogonType -notin @('Interactive', 'InteractiveToken', '3')) {
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

# O Python esta no perfil administrativo. Os scripts Tcl/Tk precisam ficar em
# uma pasta compartilhada para tkinter funcionar no desktop da conta Filhos.
$pythonBase = (& $python -c 'import sys; print(sys.base_prefix)').Trim()
if ($LASTEXITCODE -ne 0 -or -not $pythonBase) {
    throw 'Nao foi possivel localizar o runtime base do Python.'
}
$tclRuntime = Join-Path $programDataDir 'tcl'
New-Item -ItemType Directory -Path $tclRuntime -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $pythonBase 'tcl\tcl8.6') -Destination $tclRuntime -Recurse -Force
Copy-Item -LiteralPath (Join-Path $pythonBase 'tcl\tk8.6') -Destination $tclRuntime -Recurse -Force

# A fonte de verdade do launcher fica em ProgramData e e lida pelo agente da
# conta Filhos. O navegador abre primeiro; a saudacao topmost aparece sobre ele.
$programsConfig = @{
    enabled = $true
    description = 'Lista de programas a inicializar automaticamente apos o desbloqueio facial'
    programs = @(
        @{
            name = 'Brave'
            executable = $brave
            arguments = ''
            enabled = $true
        }
    )
}
$programsConfig | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $programDataDir 'programas_inicializar.json') -Encoding UTF8 -Force

# Configuracao de regra do sistema: Bloqueio automatico por inatividade da conta Filhos (2 minutos)
$configJson = Join-Path $programDataDir 'configuracoes.json'
if (-not (Test-Path -LiteralPath $configJson)) {
    $defaultSettings = @{
        inactivity_lock_seconds = 120
        inactivity_warn_seconds = 100
        description = 'FaceControlKidsPC - Bloqueio automatico por inatividade da conta Filhos (2 min)'
    }
    $defaultSettings | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configJson -Encoding UTF8 -Force
    Write-Host "Regra de bloqueio por inatividade (2 min) configurada em $configJson" -ForegroundColor Green
}
$agentBat = "C:\ProgramData\FaceKids\iniciar-filhos-agent.bat"
$agentContent = @"
@echo off
echo [%date% %time%] Startup solicitado para %USERNAME% >> "C:\ProgramData\FaceKids\filhos_startup.log"
if /i "%USERNAME%" neq "Filhos" exit /b
cd /d "C:\ProgramData\FaceKids"
set PYTHONPATH=$root
set TCL_LIBRARY=$tclRuntime\tcl8.6
set TK_LIBRARY=$tclRuntime\tk8.6
start "" "$pythonw" -m facekids.filhos_agent
"@
Set-Content -Path $agentBat -Value $agentContent -Encoding ASCII -Force

# Inicializacao primaria na sessao interativa. O VBS e executado pelo Startup
# global em cada logon, enquanto o BAT acima restringe a execucao a Filhos.
# Isso evita depender de senha armazenada ou de uma tarefa /IT fragil.
$globalStartup = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup'
$agentStartupVbs = Join-Path $globalStartup 'FaceKidsFilhosAgent.vbs'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'FaceKidsFilhosAgent.vbs') -Destination $agentStartupVbs -Force
Write-Host "Inicializacao interativa do agente instalada em $agentStartupVbs" -ForegroundColor Green

# Tarefa interativa sem senha. InteractiveToken usa a sessao existente de
# Filhos e tambem permite iniciar o agente imediatamente apos uma atualizacao.
$filhosAccount = "$env:COMPUTERNAME\Filhos"
$agentAction = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/d /c `"$agentBat`""
$agentTrigger = New-ScheduledTaskTrigger -AtLogOn -User $filhosAccount
$agentPrincipal = New-ScheduledTaskPrincipal -UserId $filhosAccount -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -Action $agentAction -Trigger $agentTrigger -Principal $agentPrincipal -Force | Out-Null

$registeredAgent = Get-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -ErrorAction Stop
$agentLogonType = [string]$registeredAgent.Principal.LogonType
if ($registeredAgent.Principal.UserId -notmatch '(?i)(^|\\)Filhos$' -or
    $agentLogonType -notin @('Interactive', 'InteractiveToken', '3')) {
    throw 'A tarefa FaceKidsFilhosAgent nao ficou vinculada a sessao interativa de Filhos.'
}
Write-Host "Agente dos Filhos agendado sem senha para $filhosAccount." -ForegroundColor Green

# 7. Iniciar os servicos em segundo plano
Write-Host "Iniciando servicos em segundo plano..." -ForegroundColor Yellow
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Where-Object { $_.CommandLine -like "*auth_service*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Start-Process -FilePath $pythonw -ArgumentList "-m facekids.auth_service" -WorkingDirectory $root
Start-Sleep -Seconds 1

# Disparar agora na sessao Filhos, quando ela ja estiver conectada.
try {
    Start-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -ErrorAction Stop
    Write-Host 'Agente solicitado na sessao Filhos existente.' -ForegroundColor Green
} catch {
    Write-Host "A conta Filhos ainda nao possui sessao; o agente iniciara no proximo logon." -ForegroundColor DarkGray
}

# 8. Configurar e ativar autenticador facial no Boot (SYSTEM / antes do logon)
try {
    Write-Host "Configurando servico facial no Boot (SYSTEM)..." -ForegroundColor Yellow
    $bootScript = Join-Path $PSScriptRoot 'Ativar-Desbloqueio-No-Boot.ps1'
    if (Test-Path -LiteralPath $bootScript) {
        & $bootScript
        Write-Host "Desbloqueio facial no boot ativado com sucesso!" -ForegroundColor Green
    }
} catch {
    Write-Host "Aviso ao configurar boot facial: $($_.Exception.Message)" -ForegroundColor DarkYellow
    Write-Host "A inicializacao interativa via FaceKidsAuthService continuara funcionando." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "     INSTALACAO E ATUALIZACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "- DLL ativa em: $dllTarget"
Write-Host "- Servico de autenticacao facial rodando em segundo plano."
Write-Host "- Agente dos Filhos ativo para exibir a Tela de Boas-Vindas com Foto."
Write-Host "- O login tradicional por senha ('1' e '11') continua 100% disponivel."
Write-Host "============================================================" -ForegroundColor Cyan

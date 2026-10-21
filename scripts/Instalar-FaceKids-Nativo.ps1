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

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     FaceControlKidsPC - Instalador de Desbloqueio Facial" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Verificar se a DLL existe (compilar se necessario)
if (-not (Test-Path -LiteralPath $dllSource)) {
    Write-Host "Compilando FaceKidsCredentialProvider.dll..." -ForegroundColor Yellow
    $buildScript = Join-Path $root 'native\credential_provider_facekids\build.ps1'
    & powershell -ExecutionPolicy Bypass -File $buildScript
    if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao da DLL." }
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

# Criar script de execucao do servico e tarefa agendada no boot do sistema
$serviceBat = "C:\ProgramData\FaceKids\iniciar-auth-service.bat"
$serviceContent = @"
@echo off
cd /d "$root"
set PYTHONPATH=$root
start "" "$pythonw" -m facekids.auth_service
"@
Set-Content -Path $serviceBat -Value $serviceContent -Encoding ASCII -Force

try {
    & schtasks.exe /create /tn "FaceKidsAuthService" /tr "cmd.exe /c \`"$serviceBat\`"" /sc onlogon /rl HIGHEST /f 2>&1 | Out-Null
    Write-Host "Tarefa agendada FaceKidsAuthService configurada no Logon interativo (com acesso a webcam e privilegios elevados)." -ForegroundColor Green
} catch {
    Write-Host "Aviso ao agendar tarefa FaceKidsAuthService: $($_.Exception.Message)" -ForegroundColor DarkGray
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
$agentBat = "C:\ProgramData\FaceKids\iniciar-filhos-agent.bat"
$agentContent = @"
@echo off
if /i "%USERNAME%" neq "Filhos" exit /b
cd /d "C:\ProgramData\FaceKids"
set PYTHONPATH=$root
start "" "$pythonw" -m facekids.filhos_agent
"@
Set-Content -Path $agentBat -Value $agentContent -Encoding ASCII -Force

# Agendar exclusivamente no Logon da conta Filhos de forma interativa (/it)
try {
    & schtasks.exe /create /tn "FaceKidsFilhosAgent" /tr "cmd.exe /c \`"$agentBat\`"" /sc onlogon /ru "Filhos" /rp "1" /it /f 2>&1 | Out-Null
    Write-Host "Agente dos Filhos agendado com sucesso vinculado exclusivamente a conta 'Filhos' (/it)." -ForegroundColor Green
} catch {
    Write-Host "Aviso ao agendar tarefa vinculada com senha: $($_.Exception.Message)" -ForegroundColor DarkGray
    & schtasks.exe /create /tn "FaceKidsFilhosAgent" /tr "cmd.exe /c \`"$agentBat\`"" /sc onlogon /f 2>&1 | Out-Null
}

# 7. Iniciar os servicos em segundo plano
Write-Host "Iniciando servicos em segundo plano..." -ForegroundColor Yellow
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Where-Object { $_.CommandLine -like "*auth_service*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Start-Process -FilePath $pythonw -ArgumentList "-m facekids.auth_service" -WorkingDirectory $root
Start-Sleep -Seconds 1

# Disparar o agente na conta Filhos
try {
    $secPass = ConvertTo-SecureString "1" -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential("Filhos", $secPass)
    Start-Process -Credential $cred -FilePath "cmd.exe" -ArgumentList "/c `"$agentBat`"" -WorkingDirectory "C:\ProgramData\FaceKids" -ErrorAction SilentlyContinue
} catch {}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "     INSTALACAO E ATUALIZACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "- DLL ativa em: $dllTarget"
Write-Host "- Servico de autenticacao facial rodando em segundo plano."
Write-Host "- Agente dos Filhos ativo para exibir a Tela de Boas-Vindas com Foto."
Write-Host "- O login tradicional por senha ('1' e '11') continua 100% disponivel."
Write-Host "============================================================" -ForegroundColor Cyan

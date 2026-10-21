<#
.SYNOPSIS
  Instalador seguro do FaceKids Credential Provider nativo.
.DESCRIPTION
  1. Copia FaceKidsCredentialProvider.dll para C:\Windows\System32\
  2. Registra o CLSID no registro do Windows (sem ocultar senhas ou PINs nativos).
  3. Configura a tarefa agendada do Servico de Autenticacao Facial (Named Pipe).
  4. Inicia o servico em segundo plano.
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
    $gpp = 'C:\Users\MarcosMiniPC\w64devkit\w64devkit\bin\g++.exe'
    if (-not (Test-Path $gpp)) {
        throw "Compilador g++ nao encontrado em $gpp"
    }
    Push-Location (Join-Path $root 'native\credential_provider_facekids')
    try {
        & $gpp -shared -std=c++17 -O2 -DINITGUID `
          dllmain.cpp FaceKidsProvider.cpp FaceKidsCredential.cpp FaceKidsProvider.def `
          -o FaceKidsCredentialProvider.dll `
          -lole32 -ladvapi32 -lsecur32 -luuid
        if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao da DLL." }
    } finally {
        Pop-Location
    }
}

# 2. Copiar DLL para ProgramData\FaceKids
Write-Host "Copiando DLL para $programDataDir..." -ForegroundColor Yellow
if (-not (Test-Path $programDataDir)) {
    New-Item -ItemType Directory -Path $programDataDir -Force | Out-Null
}
Copy-Item -LiteralPath $dllSource -Destination $dllTarget -Force

# 3. Registrar DLL via regsvr32
Write-Host "Registrando Credential Provider no Windows..." -ForegroundColor Yellow
& regsvr32.exe /s $dllTarget
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao registrar a DLL com regsvr32 (codigo $LASTEXITCODE)."
}

# 4. Configurar SID da conta Filhos no registro
$filhosUser = Get-LocalUser -Name "Filhos" -ErrorAction SilentlyContinue
if ($filhosUser) {
    $regPath = "HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider"
    if (-not (Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
    }
    Set-ItemProperty -Path $regPath -Name "TargetUserSid" -Value $filhosUser.SID.Value -Force
    Write-Host "SID da conta Filhos configurado: $($filhosUser.SID.Value)" -ForegroundColor Green
}

# 5. Criar / Atualizar Tarefa Agendada para o Servico de Autenticacao
Write-Host "Configurando servico em segundo plano (Named Pipe)..." -ForegroundColor Yellow
$taskName = "FaceKidsAuthService"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m facekids.auth_service" -WorkingDirectory $root
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

# Registrar a tarefa agendada para rodar com privilegios elevados
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($triggerLogon, $triggerStartup) -Settings $settings -User "NT AUTHORITY\SYSTEM" -RunLevel Highest | Out-Null

# Iniciar a tarefa agora mesmo
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "INSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "- DLL registrada em: $dllTarget"
Write-Host "- Provedor facial ativo na tela de bloqueio (Win+L)."
Write-Host "- O login tradicional por senha continua 100% disponivel."
Write-Host "============================================================" -ForegroundColor Cyan

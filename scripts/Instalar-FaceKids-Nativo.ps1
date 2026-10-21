<#
.SYNOPSIS
  Instalador do FaceKids Credential Provider nativo.
.DESCRIPTION
  1. Copia FaceKidsCredentialProvider.dll para C:\ProgramData\FaceKids\
  2. Registra o CLSID com regsvr32.
  3. Configura a inicializacao automatica do servico de autenticacao facial (Named Pipe).
  4. Inicia o servico imediatamente em segundo plano.
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
          -lole32 -ladvapi32 -lsecur32 -luuid -lcredui
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

# Limpeza: Remover qualquer script legado do Startup global (para nao afetar a conta padrao dos Filhos)
$globalStartupVbs = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\FaceKidsAuthService.vbs'
if (Test-Path -LiteralPath $globalStartupVbs) {
    Remove-Item -LiteralPath $globalStartupVbs -Force -ErrorAction SilentlyContinue
    Write-Host "Script legado removido do Startup global." -ForegroundColor Green
}

# Limpeza: Remover chave de Run global HKLM para evitar execucao redundante na conta dos Filhos
try {
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "FaceKidsAuthService" -Force -ErrorAction SilentlyContinue
} catch {}

# Instalar script de inicializacao exclusivamente no perfil do Administrador (MarcosMiniPC)
$userStartup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$root"
WshShell.Run """$pythonw"" -m facekids.auth_service", 0, False
"@

try {
    $userVbs = Join-Path $userStartup 'FaceKidsAuthService.vbs'
    Set-Content -Path $userVbs -Value $vbsContent -Encoding ASCII -Force
    Write-Host "Inicializacao automatica configurada para o administrador ($userVbs)." -ForegroundColor Green
} catch {
    Write-Host "Aviso ao salvar no Startup do usuario: $($_.Exception.Message)" -ForegroundColor DarkGray
}

# 6. Iniciar o servico agora mesmo em segundo plano
Write-Host "Iniciando servico de reconhecimento facial..." -ForegroundColor Yellow
& taskkill.exe /f /im pythonw.exe 2>$null
Start-Sleep -Milliseconds 500
Start-Process -FilePath $pythonw -ArgumentList "-m facekids.auth_service" -WorkingDirectory $root
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "     INSTALACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "- DLL ativa em: $dllTarget"
Write-Host "- Servico de autenticacao facial rodando em segundo plano."
Write-Host "- Provedor facial pronto na tela de bloqueio (Win+L)."
Write-Host "- O login tradicional por senha ('1' e '11') continua 100% disponivel."
Write-Host "============================================================" -ForegroundColor Cyan

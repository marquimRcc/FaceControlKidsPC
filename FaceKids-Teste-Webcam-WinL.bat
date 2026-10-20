@echo off
setlocal EnableExtensions DisableDelayedExpansion
title FaceControlKidsPC - Instalacao e Teste Win+L
set "FACEKIDS_BOOTSTRAP_FILE=%~f0"
set "FACEKIDS_BOOTSTRAP_MODE=%~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $scriptText=[System.IO.File]::ReadAllText($env:FACEKIDS_BOOTSTRAP_FILE); $marker='# FACEKIDS_POWERSHELL_BEGIN'; $index=$scriptText.LastIndexOf($marker); if($index -lt 0){throw 'Marcador do instalador nao encontrado'}; & ([scriptblock]::Create($scriptText.Substring($index+$marker.Length)))"
set "FACEKIDS_RESULT=%ERRORLEVEL%"
if not "%FACEKIDS_BOOTSTRAP_MODE%"=="--check" (
  echo.
  if not "%FACEKIDS_RESULT%"=="0" echo [ERRO] O teste nao foi concluido. Veja a mensagem acima.
  echo Pressione uma tecla para fechar.
  pause >nul
)
exit /b %FACEKIDS_RESULT%
# FACEKIDS_POWERSHELL_BEGIN
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repository = 'marquimRcc/FaceControlKidsPC'
$branch = 'feature/windows-native-unlock-poc'
$archiveUrl = 'https://github.com/' + $repository + '/archive/refs/heads/' + $branch + '.zip'
$pythonUrl = 'https://www.python.org/ftp/python/3.13.12/python-3.13.12-amd64.exe'
$pythonVersion = '3.13.12'

function Write-Step([string] $message) {
    Write-Host "`n[FaceKids] $message" -ForegroundColor Cyan
}

function Start-Python([string] $exe, [string[]] $prefix, [string[]] $arguments) {
    & $exe @prefix @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha executando Python (codigo $LASTEXITCODE)."
    }
}

function Find-Python {
    $candidates = @(
        @{ Exe = 'py.exe'; Args = @('-3.12') },
        @{ Exe = 'py.exe'; Args = @('-3.11') },
        @{ Exe = 'py.exe'; Args = @('-3.13') },
        @{ Exe = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'); Args = @() },
        @{ Exe = 'python.exe'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }
        $check = @($candidate.Args) + @('-c', 'import sys;sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) and sys.maxsize>2**32 else 1)')
        try {
            & $candidate.Exe @check *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            # An installed launcher can have no matching version.
        }
    }
    return $null
}

if ($env:FACEKIDS_BOOTSTRAP_MODE -eq '--check') {
    if ($archiveUrl -notmatch '^https://github.com/') { throw 'Origem do projeto invalida.' }
    if ($pythonUrl -notmatch '^https://www.python.org/') { throw 'Origem do Python invalida.' }
    Write-Host '[OK] Bootstrap PowerShell analisado. Sem downloads ou instalacoes.' -ForegroundColor Green
    exit 0
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Este instalador requer Windows de 64 bits.'
    }
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA nao esta disponivel.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $base = Join-Path $env:LOCALAPPDATA 'FaceKids\WindowsUnlockPOC'
    $downloads = Join-Path $base 'downloads'
    $source = Join-Path $base 'source'
    $virtualenv = Join-Path $base 'venv'
    $extract = Join-Path $base 'extract-temp'
    New-Item -ItemType Directory -Path $downloads -Force | Out-Null
    Write-Host 'FaceControlKidsPC - teste de webcam com Windows bloqueado' -ForegroundColor Green
    Write-Host 'Sem Git, sem privilegios de administrador, sem alterar o login do Windows.'
    Write-Host "Instalacao em: $base"

    $python = Find-Python
    if (-not $python) {
        Write-Step "Python nao encontrado. Instalando Python $pythonVersion somente neste usuario..."
        $pythonDir = Join-Path $base 'python313'
        $pythonExe = Join-Path $pythonDir 'python.exe'
        if (-not (Test-Path $pythonExe)) {
            $installer = Join-Path $downloads "python-$pythonVersion-amd64.exe"
            Invoke-WebRequest -Uri $pythonUrl -UseBasicParsing -OutFile $installer -TimeoutSec 180
            $signature = Get-AuthenticodeSignature -FilePath $installer
            if ($signature.Status -ne 'Valid') {
                throw "A assinatura digital do instalador Python nao foi validada: $($signature.Status)."
            }
            $installArgs = @('/quiet', 'InstallAllUsers=0', ('TargetDir="' + $pythonDir + '"'), 'Include_pip=1', 'Include_launcher=0', 'PrependPath=0', 'AssociateFiles=0', 'Shortcuts=0')
            $process = Start-Process -FilePath $installer -ArgumentList $installArgs -PassThru -Wait
            if ($process.ExitCode -ne 0) {
                throw "Falha no instalador Python (codigo $($process.ExitCode))."
            }
        }
        if (-not (Test-Path $pythonExe)) {
            throw 'A instalacao terminou mas python.exe nao foi encontrado.'
        }
        $python = @{ Exe = $pythonExe; Args = @() }
    }
    Write-Step 'Preparando o ambiente Python isolado...'
    $venvPython = Join-Path $virtualenv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Start-Python -exe $python.Exe -prefix $python.Args -arguments @('-m', 'venv', $virtualenv)
    }

    Write-Step 'Baixando o projeto da branch de testes (sem precisar de Git)...'
    $zip = Join-Path $downloads 'facekids-windows-native-unlock-poc.zip'
    Invoke-WebRequest -Uri $archiveUrl -UseBasicParsing -OutFile $zip -TimeoutSec 180
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $root = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    if (-not $root) { throw 'Arquivo baixado nao contem uma pasta do projeto.' }
    $expected = Join-Path $root.FullName 'facekids\windows_lock_probe.py'
    if (-not (Test-Path $expected)) { throw 'O pacote baixado nao contem o diagnostico esperado.' }
    if (Test-Path $source) { Remove-Item -LiteralPath $source -Recurse -Force }
    Move-Item -LiteralPath $root.FullName -Destination $source
    Remove-Item -LiteralPath $extract -Recurse -Force

    Write-Step 'Instalando apenas as dependencias de webcam no ambiente virtual...'
    Start-Python -exe $venvPython -prefix @() -arguments @('-m', 'pip', '--disable-pip-version-check', 'install', '--only-binary=:all:', '-r', (Join-Path $source 'requirements.txt'))
    Start-Python -exe $venvPython -prefix @() -arguments @('-c', 'import cv2,numpy;print("[OK] OpenCV",cv2.__version__,"NumPy",numpy.__version__)')

    Write-Host "`n[PRONTO] O teste sera iniciado por 120 segundos." -ForegroundColor Green
    Write-Host '1. Assim que o cronometro comecar, pressione Win + L.' -ForegroundColor Yellow
    Write-Host '2. Deixe a conta Filhos bloqueada por 30 a 60 segundos.' -ForegroundColor Yellow
    Write-Host '3. Desbloqueie normalmente usando a senha Windows.' -ForegroundColor Yellow
    Write-Host '4. Aguarde o resultado nesta janela (nao a feche durante o teste).' -ForegroundColor Yellow
    Write-Host 'Nao ha instalacao de Credential Provider nem bloqueio automatico.'
    Start-Sleep -Seconds 7
    Push-Location $source
    try {
        Start-Python -exe $venvPython -prefix @() -arguments @('-m', 'facekids.windows_lock_probe', '--duration', '120')
    } finally {
        Pop-Location
    }
    Write-Host "`n[FINALIZADO] O CSV do diagnostico fica em: $env:LOCALAPPDATA\FaceKids\diagnostics\" -ForegroundColor Green
    Write-Host 'Guarde o CSV para analisarmos o comportamento da webcam bloqueada.'
} catch {
    Write-Host "`n[ERRO] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
exit 0

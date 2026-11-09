<#
.SYNOPSIS
  Compila o instalador unificado autônomo 'FaceKids-Instalador.exe' usando PyInstaller.
.DESCRIPTION
  Empacota o pacote facekids completo, o frontend moderno (Conceito A), os modelos faciais ONNX,
  a DLL Credential Provider e o motor de instalação em um único executável .exe.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$pyinstaller = Join-Path $root '.venv\Scripts\pyinstaller.exe'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     Construindo FaceKids-Instalador.exe" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Garante que a DLL nativa está compilada
$dllPath = Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll'
if (-not (Test-Path -LiteralPath $dllPath)) {
    Write-Host "Compilando DLL Credential Provider..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root 'native\credential_provider_facekids\build.ps1')
}

# 2. Limpa qualquer executável anterior na pasta dist
$entryScript = Join-Path $root 'packaging\installer_runner.py'
if (-not (Test-Path -LiteralPath $entryScript)) {
    $entryScript = Join-Path $root 'installer_runner.py'
}
$distDir = Join-Path $root 'dist'
$buildDir = Join-Path $root 'build'

if (Test-Path -LiteralPath $distDir) {
    Get-ChildItem -Path $distDir -Filter "*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

$facekidsPkg = Join-Path $root 'facekids'
$uiAssets = Join-Path $root 'facekids\ui_assets'
$modelsDir = Join-Path $root 'models'

Write-Host "Empacotando com PyInstaller em arquivo executável único..." -ForegroundColor Yellow

$pyinstallerArgs = @(
    '--noconfirm',
    '--onefile',
    '--windowed',
    '--uac-admin',
    '--name', 'FaceKids-Instalador',
    '--paths', $root,
    '--hidden-import', 'facekids.app_window',
    '--hidden-import', 'facekids.app_server',
    '--hidden-import', 'facekids.camera_service',
    '--hidden-import', 'facekids.installer_engine',
    '--hidden-import', 'facekids.session_secret',
    '--hidden-import', 'facekids.admin_auth',
    '--hidden-import', 'facekids.storage',
    "--add-data", "$facekidsPkg;facekids",
    "--add-data", "$uiAssets;facekids/ui_assets",
    "--add-data", "$modelsDir;models",
    "--add-data", "$dllPath;native/credential_provider_facekids",
    "--distpath", $distDir,
    "--workpath", $buildDir,
    $entryScript
)

& $pyinstaller @pyinstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "Falha ao compilar FaceKids-Instalador.exe com PyInstaller."
}

# Remove quaisquer outros executáveis mantendo apenas FaceKids-Instalador.exe
Get-ChildItem -Path $distDir -Filter "*.exe" | Where-Object { $_.Name -ne 'FaceKids-Instalador.exe' } | Remove-Item -Force -ErrorAction SilentlyContinue

$outputExe = Join-Path $distDir 'FaceKids-Instalador.exe'
if (Test-Path -LiteralPath $outputExe) {
    $sizeMb = [math]::Round(((Get-Item $outputExe).Length / 1MB), 2)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  FaceKids-Instalador.exe GERADO COM SUCESSO!" -ForegroundColor Green
    Write-Host "  Caminho: $outputExe" -ForegroundColor Green
    Write-Host "  Tamanho: $sizeMb MB" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    throw "O arquivo FaceKids-Instalador.exe não foi encontrado na pasta dist."
}

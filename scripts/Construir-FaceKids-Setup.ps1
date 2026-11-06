<#
.SYNOPSIS
  Compila o instalador unificado autônomo 'FaceKids-Setup.exe' usando PyInstaller.
.DESCRIPTION
  Empacota o frontend moderno (Conceito A), os modelos faciais ONNX,
  a DLL Credential Provider e o motor de instalação em um único executável .exe.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$pyinstaller = Join-Path $root '.venv\Scripts\pyinstaller.exe'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     Construindo FaceKids-Setup.exe (Instalador Unificado)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Garante que a DLL nativa está compilada
$dllPath = Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll'
if (-not (Test-Path -LiteralPath $dllPath)) {
    Write-Host "Compilando DLL Credential Provider..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root 'native\credential_provider_facekids\build.ps1')
}

# 2. Configura os diretórios de dados a serem embutidos
$entryScript = Join-Path $root 'scripts\installer_entry.py'
$distDir = Join-Path $root 'dist'
$buildDir = Join-Path $root 'build'

$uiAssets = Join-Path $root 'facekids\ui_assets'
$modelsDir = Join-Path $root 'models'

Write-Host "Empacotando com PyInstaller em arquivo executável único..." -ForegroundColor Yellow

$pyinstallerArgs = @(
    '--noconfirm',
    '--onefile',
    '--windowed',
    '--uac-admin',
    '--name', 'FaceKids-Setup',
    "--add-data", "$uiAssets;facekids/ui_assets",
    "--add-data", "$modelsDir;models",
    "--add-data", "$dllPath;native/credential_provider_facekids",
    "--distpath", $distDir,
    "--workpath", $buildDir,
    $entryScript
)

& $pyinstaller @pyinstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "Falha ao compilar FaceKids-Setup.exe com PyInstaller."
}

$outputExe = Join-Path $distDir 'FaceKids-Setup.exe'
if (Test-Path -LiteralPath $outputExe) {
    $sizeMb = [math]::Round(((Get-Item $outputExe).Length / 1MB), 2)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  FaceKids-Setup.exe GERADO COM SUCESSO!" -ForegroundColor Green
    Write-Host "  Caminho: $outputExe" -ForegroundColor Green
    Write-Host "  Tamanho: $sizeMb MB" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    throw "O arquivo FaceKids-Setup.exe não foi encontrado na pasta dist."
}

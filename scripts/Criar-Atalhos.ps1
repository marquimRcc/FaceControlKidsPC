<#
.SYNOPSIS
  Cria ou atualiza os atalhos do SafePCKids no Menu Iniciar e na Area de Trabalho.
.DESCRIPTION
  Registra o Painel dos Pais e o Instalador usando o pythonw.exe assinado
  (evitando bloqueio do Smart App Control do Windows 11) com o icone oficial.
#>
[CmdletBinding()]
param()

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        $pythonw = 'pythonw.exe'
    }
}

$iconPath = Join-Path $root 'assets\safepckids.ico'
$desktop = [Environment]::GetFolderPath('Desktop')
$userStartMenu = [Environment]::GetFolderPath('Programs')
$startMenuDir = Join-Path $userStartMenu 'SafePCKids'

if (-not (Test-Path -LiteralPath $startMenuDir)) {
    New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
}

$wsh = New-Object -ComObject WScript.Shell

# 1. Atalho no Menu Iniciar - Painel dos Pais
$lnkStartAdmin = Join-Path $startMenuDir 'SafePCKids - Painel dos Pais.lnk'
$s1 = $wsh.CreateShortcut($lnkStartAdmin)
$s1.TargetPath = $pythonw
$s1.Arguments = '-m safepckids.launcher --admin'
$s1.WorkingDirectory = $root
$s1.Description = 'SafePCKids - Painel Administrativo dos Pais'
if (Test-Path -LiteralPath $iconPath) { $s1.IconLocation = "$iconPath,0" }
$s1.Save()

# 2. Atalho no Menu Iniciar - Configuracao / Instalador
$lnkStartWizard = Join-Path $startMenuDir 'SafePCKids - Configuracao e Instalador.lnk'
$s2 = $wsh.CreateShortcut($lnkStartWizard)
$s2.TargetPath = $pythonw
$s2.Arguments = '-m safepckids.launcher --setup'
$s2.WorkingDirectory = $root
$s2.Description = 'SafePCKids - Assistente de Instalacao e Cadastro Facial'
if (Test-Path -LiteralPath $iconPath) { $s2.IconLocation = "$iconPath,0" }
$s2.Save()

# 3. Atalho na Area de Trabalho (Desktop) - Painel dos Pais
$lnkDesktop = Join-Path $desktop 'SafePCKids - Painel dos Pais.lnk'
$s3 = $wsh.CreateShortcut($lnkDesktop)
$s3.TargetPath = $pythonw
$s3.Arguments = '-m safepckids.launcher --admin'
$s3.WorkingDirectory = $root
$s3.Description = 'SafePCKids - Painel de Controle Parental'
if (Test-Path -LiteralPath $iconPath) { $s3.IconLocation = "$iconPath,0" }
$s3.Save()

Write-Host "Atalhos criados com sucesso:" -ForegroundColor Green
Write-Host " - Menu Iniciar: $startMenuDir" -ForegroundColor Cyan
Write-Host " - Desktop:      $lnkDesktop" -ForegroundColor Cyan

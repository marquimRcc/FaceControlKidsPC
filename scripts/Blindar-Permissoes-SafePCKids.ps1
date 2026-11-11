<#
.SYNOPSIS
  Aplica endurecimento de seguranca NTFS (Hardening) em C:\ProgramData\SafePCKids.
.DESCRIPTION
  - Restringe permissoes de C:\ProgramData\SafePCKids para SYSTEM e Administradores.
  - Remove permissoes de escrita ampla (Everyone, Authenticated Users, BUILTIN\Users).
  - Bloqueia alteracao da DLL, scripts BAT e configs por contas nao administrativas.
  - Concede apenas as permissoes estritamente necessarias para o agente Filhos operar.
#>
[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:ProgramData 'SafePCKids')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Root)) {
    Write-Warning "Diretorio $Root nao existe."
    return
}

Write-Host "Aplicando Hardening NTFS em $Root..." -ForegroundColor Cyan

# Localizar conta Filhos
$filhosUser = Get-LocalUser -Name "Filhos" -ErrorAction SilentlyContinue
$filhosName = if ($filhosUser) { $filhosUser.Name } else { "Filhos" }

# 1. Desabilita herança copiando ACEs (/inheritance:d)
& icacls $Root /inheritance:d 2>&1 | Out-Null

# 2. Remove permissoes amplas de escrita de Todos / Users / Authenticated Users / Filhos na raiz
& icacls $Root /remove:g "*S-1-1-0" 2>&1 | Out-Null      # Everyone / Todos
& icacls $Root /remove:g "*S-1-5-11" 2>&1 | Out-Null     # Authenticated Users
& icacls $Root /remove:g "*S-1-5-32-545" 2>&1 | Out-Null # BUILTIN\Users
& icacls $Root /remove:g $filhosName 2>&1 | Out-Null

# 3. Garante Full Control para SYSTEM (*S-1-5-18) e Administradores (*S-1-5-32-544)
& icacls $Root /grant:r "*S-1-5-18:(OI)(CI)(F)" "*S-1-5-32-544:(OI)(CI)(F)" 2>&1 | Out-Null

# Concede Read & Execute na raiz da pasta para BUILTIN\Users (*S-1-5-32-545)
& icacls $Root /grant "*S-1-5-32-545:(OI)(CI)(RX)" 2>&1 | Out-Null

if ($filhosUser) {
    # Filhos: apenas Read & Execute na raiz e subpastas gerais
    & icacls $Root /grant "${filhosName}:(OI)(CI)(RX)" 2>&1 | Out-Null
}

# 4. Proteger DLL e scripts executaveis: somente SYSTEM/Admin podem alterar
$binaries = @('SafePCKidsCredentialProvider.dll', 'iniciar-auth-service.bat', 'iniciar-filhos-agent.bat')
foreach ($bin in $binaries) {
    $p = Join-Path $Root $bin
    if (Test-Path -LiteralPath $p) {
        & icacls $p /inheritance:d 2>&1 | Out-Null
        & icacls $p /remove:g "*S-1-1-0" "*S-1-5-11" "*S-1-5-32-545" $filhosName 2>&1 | Out-Null
        & icacls $p /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" 2>&1 | Out-Null
        if ($bin -eq 'iniciar-filhos-agent.bat' -and $filhosUser) {
            # Filhos pode ler e executar o seu proprio agente BAT, mas nunca modificar
            & icacls $p /grant "${filhosName}:(RX)" 2>&1 | Out-Null
        } elseif ($bin -eq 'SafePCKidsCredentialProvider.dll' -and $filhosUser) {
            # Filhos pode ler/executar a DLL para logon, mas nunca modificar
            & icacls $p /grant "${filhosName}:(RX)" 2>&1 | Out-Null
        }
    }
}

# 5. Proteger configuracoes e last_unlock: somente leitura para Filhos
$configs = @('configuracoes.json', 'programas_inicializar.json', 'last_unlock.json')
foreach ($cfg in $configs) {
    $p = Join-Path $Root $cfg
    if (Test-Path -LiteralPath $p) {
        & icacls $p /inheritance:d 2>&1 | Out-Null
        & icacls $p /remove:g "*S-1-1-0" "*S-1-5-11" "*S-1-5-32-545" $filhosName 2>&1 | Out-Null
        & icacls $p /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" 2>&1 | Out-Null
        if ($filhosUser) {
            & icacls $p /grant "${filhosName}:(R)" 2>&1 | Out-Null
        }
    }
}

# 6. Pasta de fotos e TCL: somente leitura para Filhos / Users (apenas admin altera fotos dos cadastros)
$readOnlyDirs = @('fotos', 'tcl')
foreach ($d in $readOnlyDirs) {
    $p = Join-Path $Root $d
    if (Test-Path -LiteralPath $p) {
        & icacls $p /inheritance:d 2>&1 | Out-Null
        & icacls $p /remove:g "*S-1-1-0" "*S-1-5-11" "*S-1-5-32-545" $filhosName 2>&1 | Out-Null
        & icacls $p /grant:r "*S-1-5-18:(OI)(CI)(F)" "*S-1-5-32-544:(OI)(CI)(F)" 2>&1 | Out-Null
        & icacls $p /grant "*S-1-5-32-545:(OI)(CI)(RX)" 2>&1 | Out-Null
        if ($filhosUser) {
            & icacls $p /grant "${filhosName}:(OI)(CI)(RX)" 2>&1 | Out-Null
        }
    }
}

# 7. Arquivos de logs e heartbeat onde o agente Filhos grava informacoes:
$runtimeWriteFiles = @(
    'agent_heartbeat.json',
    'filhos_agent.log',
    'filhos_startup.log',
    'criancas.sqlite3',
    'criancas.sqlite3-wal',
    'criancas.sqlite3-shm',
    'kids.sqlite3',
    'kids.sqlite3-wal',
    'kids.sqlite3-shm'
)
foreach ($rw in $runtimeWriteFiles) {
    $p = Join-Path $Root $rw
    if (Test-Path -LiteralPath $p) {
        & icacls $p /inheritance:d 2>&1 | Out-Null
        & icacls $p /remove:g "*S-1-1-0" "*S-1-5-11" "*S-1-5-32-545" $filhosName 2>&1 | Out-Null
        & icacls $p /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" 2>&1 | Out-Null
        if ($filhosUser) {
            & icacls $p /grant "${filhosName}:(M)" 2>&1 | Out-Null
        }
    }
}

Write-Host "Hardening NTFS aplicado com sucesso em $Root!" -ForegroundColor Green

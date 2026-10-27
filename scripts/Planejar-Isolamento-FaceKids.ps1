<#
.SYNOPSIS
  Planeja a separacao de codigo privilegiado e dados do FaceKids (somente leitura).
.DESCRIPTION
  Nao move, copia, exclui ou reconfigura arquivos, ACLs, tarefas ou registro COM.
  Antes de mudar a instalacao real, um broker confiavel deve assumir o ledger;
  o agente Filhos hoje grava diretamente no SQLite compartilhado.
#>
[CmdletBinding()]
param(
    [string]$DataRoot = (Join-Path $env:ProgramData 'FaceKids'),
    [string]$ProtectedRoot = (Join-Path $env:ProgramFiles 'FaceKids')
)
$ErrorActionPreference = 'Stop'
$audit = Join-Path $PSScriptRoot 'Auditar-Permissoes-FaceKids.ps1'
$entries = @(& $audit -Root $DataRoot | ConvertFrom-Json)
$exposed = @($entries | Where-Object { $_.Exists -and @($_.BroadWriteAces).Count -gt 0 })
$assets = @(
    [pscustomobject]@{
        Name = 'CredentialProvider'
        Current = (Join-Path $DataRoot 'FaceKidsCredentialProvider.dll')
        Proposed = (Join-Path $ProtectedRoot 'FaceKidsCredentialProvider.dll')
        Risk = 'DllLoadFromBroadlyWritableDirectory'
        BlockedUntil = 'VM backup and proof Filhos cannot change DLL or parent path'
    },
    [pscustomobject]@{
        Name = 'AuthServiceLauncher'
        Current = (Join-Path $DataRoot 'iniciar-auth-service.bat')
        Proposed = (Join-Path $ProtectedRoot 'iniciar-auth-service.bat')
        Risk = 'ElevatedTaskLaunchingMutableScript'
        BlockedUntil = 'VM task principal and filesystem ACL regression verified'
    },
    [pscustomobject]@{
        Name = 'QuotaLedger'
        Current = (Join-Path $DataRoot 'criancas.sqlite3')
        Proposed = (Join-Path $DataRoot 'protected-ledger\criancas.sqlite3')
        Risk = 'ChildCanModifyUsageAndIdentity'
        BlockedUntil = 'Service-owned broker debit API and agent integration tested'
    }
)
[pscustomobject]@{
    Mode = 'ReadOnlyMigrationPlan'
    DataRoot = $DataRoot
    ProtectedRoot = $ProtectedRoot
    RiskyExistingPaths = @($exposed | ForEach-Object { $_.Path })
    ProposedAssets = $assets
    RequiresServiceOwnedQuotaLedger = $true
    RequiresVmRollbackValidation = $true
    ReadyToDeploy = $false
    MutationsPerformed = 0
} | ConvertTo-Json -Depth 6

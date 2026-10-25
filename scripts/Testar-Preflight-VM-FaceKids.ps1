<#
.SYNOPSIS
  Preflight SOMENTE LEITURA para homologacao restauravel do Windows.
.DESCRIPTION
  Nao instala ou registra Credential Provider, nao altera Winlogon, tarefas,
  bancos, fotos, ACLs ou registro. Identificacao de VM por modelo e apenas
  indicativa; nunca afirma snapshot externo ou recuperacao de logon comprovados.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$hostInfo = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
$manufacturer = if ($hostInfo) { [string]$hostInfo.Manufacturer } else { '' }
$model = if ($hostInfo) { [string]$hostInfo.Model } else { '' }
$looksVirtual = ($manufacturer + ' ' + $model) -match '(Hyper-V|Virtual Machine|VMware|VirtualBox|QEMU|KVM|Xen|Parallels)'
$osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$isWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$expectedDll = Join-Path $env:ProgramData 'FaceKids\FaceKidsCredentialProvider.dll'
$expectedDb = Join-Path $env:ProgramData 'FaceKids\criancas.sqlite3'

[pscustomobject]@{
    Mode = 'ReadOnlyWinlogonVmPreflight'
    WindowsDetected = [bool]$isWindows
    GuestModelLooksVirtual = [bool]$looksVirtual
    OperatingSystem = if ($osInfo) { [string]$osInfo.Caption } else { $null }
    ExpectedCredentialProviderDllPresent = [bool](Test-Path -LiteralPath $expectedDll)
    ExpectedFamilyQuotaDatabasePresent = [bool](Test-Path -LiteralPath $expectedDb)
    ExternalSnapshotTested = $false
    OfflineAdministratorRecoveryTested = $false
    CredentialProviderWinlogonTested = $false
    FaceCameraAndLivenessTested = $false
    ChildEffectiveTokenAfterMigrationTested = $false
    ReadyForFamilyInstallation = $false
    WritesPerformed = 0
    RequiredManualEvidence = @(
      'A supported VM with external snapshot and proven restore',
      'Normal administrator password/PIN login retained after Winlogon failure',
      'Real Credential Provider registration/removal only inside restored VM',
      'Three local profile face tests with Win+L, reboot, camera absence and liveness',
      'Trusted service owns all SQLite/WAL/SHM paths after access-token migration'
    )
} | ConvertTo-Json -Depth 5

#Requires -Version 5.1
<#
.SYNOPSIS
  Read-only environment preflight for FaceKids Windows SCM experiments.
.DESCRIPTION
  Never registers services, modifies Winlogon, changes a password,
  writes a registry key or installs any DLL. Recognition of a
  hypervisor is only an indication, NOT proof of a valid VM snapshot.
#>
[CmdletBinding()]
param(
    [switch]$RequireGitHubHosted
)

$ErrorActionPreference = 'Stop'
if ($RequireGitHubHosted) {
    if ($env:GITHUB_ACTIONS -ne 'true' -or
        $env:FACEKIDS_RUNNER_ENVIRONMENT -ne 'github-hosted') {
        throw 'REFUSED: service lifecycle tests require GitHub-hosted Windows runner.'
    }
}
$system = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
$operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
if (-not $system -or -not $operatingSystem) {
    throw 'REFUSED: Windows host inspection unavailable.'
}
$model = [string]$system.Model
$manufacturer = [string]$system.Manufacturer
$isVirtual = ($model -match 'Virtual Machine|VMware|VirtualBox|KVM|QEMU|Parallels|HVM|Hyper-V' -or
              $manufacturer -match 'VMware|innotek|QEMU|Xen|Parallels')
if (-not $isVirtual) {
    throw 'REFUSED: could not identify a virtualized Windows environment.'
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'REFUSED: not a Windows NT host.'
}
Write-Host 'PASS: environment resembles a virtualized Windows host.'
Write-Host 'WARNING: virtualization detection does NOT prove a snapshot or recovery is available.'
Write-Host 'No login settings, registry entries, passwords or services were changed.'

#Requires -Version 5.1
<#
.SYNOPSIS
  P6 — preflight and optional isolated tests INSIDE a disposable Windows VM.
.DESCRIPTION
  This script DOES NOT install/register Credential Providers, SCM services,
  change registry, ACL, passwords, user accounts, Winlogon or family SQLite.
  -RunUnitTests executes repository synthetic tests (which use temporary data).
  -CameraProbe opens/releases the guest webcam (no pictures retained).
  A VM-like model is NOT proof of a working external snapshot.
#>
[CmdletBinding()]
param(
    [switch]$RunUnitTests,
    [switch]$CameraProbe,
    [ValidateRange(0, 9)][int]$CameraIndex = 0
)

$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'P6 REFUSED: Windows VM guest only.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$family = Join-Path $env:ProgramData 'FaceKids'
if ($root.TrimEnd('\') -eq $family.TrimEnd('\') -or
    $root.StartsWith(($family.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'P6 REFUSED: repository points to installed family directory.'
}
$hostInfo = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$vmDescription = (([string]$hostInfo.Manufacturer) + ' ' + ([string]$hostInfo.Model))
$isVm = $vmDescription -match '(Virtual Machine|VMware|VirtualBox|QEMU|KVM|Xen|Parallels|innotek|HVM|Bochs|BHYVE)'
if (-not $isVm) {
    throw 'P6 REFUSED: no recognizable VM guest hardware. Do not run on family PC.'
}
$cpKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{FAC0D042-3DD0-4A8C-9F18-440C44330C20}'
$credentialProviderAlreadyRegistered = Test-Path -LiteralPath $cpKey
$services = @(Get-Service -Name 'FaceKids*' -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty Name)
$python = $null
$venv = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venv) {
    $python = $venv
} elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $python = 'py.exe'
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    $python = 'python.exe'
}
$report = [ordered]@{
    Protocol = 'FACEKIDS_VM_P6_PREFLIGHT_V1'
    Timestamp = (Get-Date).ToString('o')
    Mode = 'GuestPreflightNoInstallation'
    BranchExpected = 'developer'
    VmGuestDetected = [bool]$isVm
    Windows = [string]$osInfo.Caption
    CredentialProviderAlreadyRegistered = [bool]$credentialProviderAlreadyRegistered
    ExistingFaceKidsServices = $services
    PythonFound = [bool]$python
    UnitTestsRequested = [bool]$RunUnitTests
    UnitTestsExitCode = $null
    CameraProbeRequested = [bool]$CameraProbe
    CameraProbeExitCode = $null
    ExternalSnapshotRestoredAndVerified = 'MANUAL_NOT_VERIFIED'
    AdministratorFallbackAfterFailure = 'MANUAL_NOT_VERIFIED'
    CameraAsSystemSession0 = 'NOT_TESTED_BY_THIS_SCRIPT'
    LogonUIAutomaticUnlock = 'NOT_TESTED_BY_THIS_SCRIPT'
    FamilyDeploymentApproved = $false
    WinlogonScmAclChangesByScript = 0
}
if ($RunUnitTests -or $CameraProbe) {
    if (-not $python) {
        throw 'Python not found. Install Python 3.11 and requirements in the VM before optional tests.'
    }
}
if ($RunUnitTests) {
    Push-Location $root
    try {
        if ($python -eq 'py.exe') {
            & py.exe -3.11 -m unittest discover -s tests -p 'test_*.py'
        } else {
            & $python -m unittest discover -s tests -p 'test_*.py'
        }
        $report.UnitTestsExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
}
if ($CameraProbe) {
    # Only the guest's interactive camera; NOT SYSTEM Session 0 or LogonUI.
    $code = @'
import cv2,sys
index=int(sys.argv[1])
cap=cv2.VideoCapture(index, cv2.CAP_DSHOW)
try:
    if not cap.isOpened():
        print("CAMERA_GUEST_INTERACTIVE=UNAVAILABLE")
        sys.exit(2)
    ok, frame=cap.read()
    print("CAMERA_GUEST_INTERACTIVE=" + ("FRAME_OBSERVED" if ok and frame is not None else "NO_FRAME"))
    sys.exit(0 if ok and frame is not None else 3)
finally:
    cap.release()
'@
    if ($python -eq 'py.exe') {
        & py.exe -3.11 -c $code $CameraIndex
    } else {
        & $python -c $code $CameraIndex
    }
    $report.CameraProbeExitCode = $LASTEXITCODE
}
$report | ConvertTo-Json -Depth 5
if ($RunUnitTests -and $report.UnitTestsExitCode -ne 0) {
    throw 'P6: VM unit tests failed (diagnostic only; nothing installed).'
}
if ($CameraProbe -and $report.CameraProbeExitCode -ne 0) {
    Write-Warning 'VM interactive webcam unavailable; check USB passthrough and app permissions.'
}

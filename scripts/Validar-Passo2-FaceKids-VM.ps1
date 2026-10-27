#Requires -Version 5.1
<#
.SYNOPSIS
  Passo 2: preflight somente leitura antes de registrar Credential Provider
  na VM VirtualBox. Nao altera usuarios, senhas, snapshots, Winlogon ou SCM.
.DESCRIPTION
  Snapshot e login por senha nao sao validaveis automaticamente dentro do
  convidado. Sao obrigatoriamente evidencias MANUAIS do operador no host/VM.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Somente Windows convidado VirtualBox.'
}
$pc = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$signature = [string]$pc.Manufacturer + ' ' + [string]$pc.Model
if ($signature -notmatch '(?i)VirtualBox|innotek') {
    throw 'RECUSADO: verificador exclusivo de VM VirtualBox.'
}
$user = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($user.Name.Split('\')[-1] -ieq 'Filhos') {
    throw 'Abra este preflight pela conta administrativa da VM.'
}
$lab = Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab'
$root = Join-Path $lab 'codigo-developer'
$db = Join-Path $lab 'dados-isolados\data\criancas.sqlite3'
$py = Join-Path $lab '.venv\Scripts\python.exe'
$workerFile = Join-Path $lab 'vm-auth-worker.json'
$stage = Join-Path $lab 'scripts\FaceKids-VM-Autenticacao.ps1'
$clsid = '{FAC0D042-3DD0-4A8C-9F18-440C44330C20}'
$cpKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
$comKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$clsid"
$familyDll = Join-Path $env:ProgramData 'FaceKids\FaceKidsCredentialProvider.dll'
$labDll = Join-Path $env:ProgramData 'FaceKids-VM-CP-Lab\FaceKidsCredentialProvider.dll'

$adminUser = Get-LocalUser -Name $user.Name.Split('\')[-1] -ErrorAction SilentlyContinue
$child = Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue
$adminEnabled = [bool]($adminUser -and $adminUser.Enabled)
$childEnabled = [bool]($child -and $child.Enabled)
$localAdmins = @(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction SilentlyContinue)
$adminMember = [bool](@($localAdmins | Where-Object {
    $sid = if ($_.SID) { $_.SID.Value } else { '' }
    $sid -eq [string]$user.User.Value
}).Count -gt 0)
$workerValid = $false
$workerPid = $null
if (Test-Path -LiteralPath $workerFile -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $workerFile -Raw | ConvertFrom-Json
        if ($state.python -eq $py -and $state.processId) {
            $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$state.processId) -ErrorAction SilentlyContinue
            if ($proc -and $proc.ExecutablePath -eq $py -and
                $proc.CommandLine -match 'facekids[.]auth_service') {
                $owner = Invoke-CimMethod -InputObject $proc -MethodName GetOwnerSid -ErrorAction SilentlyContinue
                $workerValid = [bool]($owner -and $owner.ReturnValue -eq 0 -and
                                       $owner.Sid -eq [string]$user.User.Value)
                if ($workerValid) { $workerPid = [int]$proc.ProcessId }
            }
        }
    } catch {
        $workerValid = $false
    }
}
$cpAbsent = -not ((Test-Path -LiteralPath $cpKey) -or
                 (Test-Path -LiteralPath $comKey) -or
                 (Test-Path -LiteralPath $labDll))
$assets = (Test-Path -LiteralPath $py -PathType Leaf) -and
          (Test-Path -LiteralPath $db -PathType Leaf) -and
          (Test-Path -LiteralPath $stage -PathType Leaf) -and
          (Test-Path -LiteralPath (Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll') -PathType Leaf)
$checks = [ordered]@{
    VmVirtualBox = $true
    CurrentAdminAccountEnabled = $adminEnabled
    CurrentAccountInLocalAdministrators = $adminMember
    FilhosAccountEnabled = $childEnabled
    LabAssetsAvailable = [bool]$assets
    AuthWorkerRunningAsCurrentAccount = $workerValid
    CredentialProviderNotRegistered = $cpAbsent
    FamilyCredentialProviderDllAbsent = -not (Test-Path -LiteralPath $familyDll)
}
Write-Host ''
Write-Host '=== FaceKids VM - PASSO 2: PREPARACAO PARA CREDENTIAL PROVIDER ===' -ForegroundColor Cyan
foreach ($name in $checks.Keys) {
    $value = [bool]$checks[$name]
    Write-Host (('[{0}] {1}' -f $(if ($value) {'OK'} else {'ATENCAO'}), $name))
}
Write-Host ('Worker PID: ' + $(if ($workerPid) { $workerPid } else { 'NAO CONFIRMADO' }))
Write-Host 'Snapshot externo novo: NAO VERIFICADO (somente VirtualBox no HOST).' -ForegroundColor Yellow
Write-Host 'Restauracao do novo snapshot: NAO VERIFICADA (teste manual).' -ForegroundColor Yellow
Write-Host 'Login administrativo por senha/PIN: NAO VERIFICADO (teste manual).' -ForegroundColor Yellow
Write-Host 'Senha Windows da conta Filhos = 1: NAO VERIFICADA (teste manual).' -ForegroundColor Yellow
Write-Host 'Nenhuma senha foi lida ou testada; nenhum arquivo foi criado/alterado.'
if (@($checks.Values | Where-Object { -not $_ }).Count -gt 0) {
    Write-Warning 'Existem precondicoes tecnicas pendentes; NAO execute ActivateCP.'
    exit 2
}
Write-Host ''
Write-Host 'Preflight tecnico aprovado. Ainda NAO autoriza ActivateCP.' -ForegroundColor Green
Write-Host 'No HOST VirtualBox: salve um NOVO snapshot antes de registrar a DLL.'
Write-Host 'Depois confirme manualmente a recuperacao administrativa e a senha real de Filhos.'
Write-Host 'Ao desligar/reiniciar a VM, worker interativo para; reinicie-o e repita PING/ALLOW.'

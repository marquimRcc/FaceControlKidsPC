<#
.SYNOPSIS
  Ensaio ACL e rollback SOMENTE em arquivos temporarios sinteticos.
.DESCRIPTION
  Nao recebe caminhos e nunca altera ProgramData, Windows Login, servicos,
  tarefas, registro COM, usuarios ou o SQLite real. Nao prova acesso efetivo
  do token Filhos: esse teste separado requer VM preparada.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('facekids-quota-acl-lab-' + [guid]::NewGuid().ToString('N'))
$original = $null
$file = $null
$restored = $false
$protected = $false
try {
    New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
    $file = Join-Path $root 'synthetic-ledger.sqlite3'
    [IO.File]::WriteAllBytes($file, [byte[]](0x46, 0x41, 0x4b, 0x45))
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    $original = Get-Acl -LiteralPath $file
    $initialSddl = $original.Sddl
    $acl = Get-Acl -LiteralPath $file
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($entry in @($acl.Access)) {
        $acl.RemoveAccessRuleSpecific($entry) | Out-Null
    }
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $builtinUsers = New-Object Security.Principal.SecurityIdentifier 'S-1-5-32-545'
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        $currentSid, 'FullControl', 'Allow')))
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        $builtinUsers, 'ReadAndExecute', 'Allow')))
    Set-Acl -LiteralPath $file -AclObject $acl -ErrorAction Stop

    $check = Get-Acl -LiteralPath $file
    $protected = -not @($check.Access | Where-Object {
        $sid = $_.IdentityReference.Translate(
            [Security.Principal.SecurityIdentifier]).Value
        ($sid -eq 'S-1-5-32-545') -and
        (($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Write) -ne 0)
    }).Count
    if (-not $protected) { throw 'Lab Users ACL unexpectedly includes write' }
    if ((Get-FileHash -LiteralPath $file).Hash -ne $hash) {
        throw 'Lab ACL mutation unexpectedly modified file bytes'
    }

    Set-Acl -LiteralPath $file -AclObject $original -ErrorAction Stop
    $restored = ((Get-Acl -LiteralPath $file).Sddl -eq $initialSddl)
    if (-not $restored) { throw 'Synthetic ACL failed rollback' }

    [pscustomobject]@{
        Mode = 'DisposableAclRollback'
        BroadUsersWriteAceAbsent = [bool]$protected
        OriginalAclRestored = [bool]$restored
        SyntheticFileBytesUnchanged = $true
        ChildEffectiveTokenTested = $false
        ProductionPathsTouched = $false
        ServiceOrCredentialProviderInstalled = $false
    } | ConvertTo-Json -Depth 3
} finally {
    if ($file -and (Test-Path -LiteralPath $file) -and $original) {
        try { Set-Acl -LiteralPath $file -AclObject $original -ErrorAction Stop }
        catch { Write-Warning "ACL restore failed for the TEMPORARY fixture: $($_.Exception.Message)" }
    }
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop
    }
}

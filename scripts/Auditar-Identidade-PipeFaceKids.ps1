<#
.SYNOPSIS
  Diagnostico SOMENTE LEITURA de identidade do processo de autenticacao facial.
.DESCRIPTION
  Compara SIDs da tarefa agendada e processos observados, sem abrir o pipe,
  webcam, credenciais ou arquivos biometricos. Uma correspondencia NAO
  comprova que aquele processo e o servidor conectado no pipe:
  so GetNamedPipeServerProcessId no handle do cliente oferece essa associacao.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

function Resolve-PrincipalSid {
    param([AllowNull()][string]$Principal)
    if ([string]::IsNullOrWhiteSpace($Principal)) { return $null }
    if ($Principal -match '^S-\d+(-\d+)+$') { return $Principal }
    try {
        $account = [Security.Principal.NTAccount]::new($Principal)
        return $account.Translate([Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $null
    }
}

$task = Get-ScheduledTask -TaskName 'FaceKidsAuthService' -ErrorAction SilentlyContinue
$taskSid = if ($task) { Resolve-PrincipalSid -Principal $task.Principal.UserId } else { $null }
$taskReport = if ($null -eq $task) {
    [pscustomobject]@{
        Present = $false
        Principal = $null
        PrincipalSid = $null
        LogonType = $null
        RunLevel = $null
        State = $null
    }
} else {
    [pscustomobject]@{
        Present = $true
        Principal = $task.Principal.UserId
        PrincipalSid = $taskSid
        LogonType = [string]$task.Principal.LogonType
        RunLevel = [string]$task.Principal.RunLevel
        State = [string]$task.State
    }
}

# Enumera apenas metadados. Nunca inclui linha de comando nos resultados,
# pois comandos arbitrarios podem conter credenciais ou caminhos sensiveis.
$observed = @(
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*-m facekids.auth_service*' } |
        ForEach-Object {
            $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
            $ownerSidResult = Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction SilentlyContinue
            $ownerSid = if ($ownerSidResult -and $ownerSidResult.ReturnValue -eq 0) {
                [string]$ownerSidResult.Sid
            } else { $null }
            $ownerMatchesTask = if ($ownerSid -and $taskSid) {
                $ownerSid -eq $taskSid
            } else { $null }
            [pscustomobject]@{
                ProcessId = [int]$_.ProcessId
                SessionId = [int]$_.SessionId
                OwnerName = if ($owner) { $owner.User } else { $null }
                OwnerDomain = if ($owner) { $owner.Domain } else { $null }
                OwnerSid = $ownerSid
                OwnerMatchesScheduledPrincipal = $ownerMatchesTask
            }
        }
)

[pscustomobject]@{
    Task = $taskReport
    AuthProcesses = $observed
    NamedPipeServerIdentityVerified = $false
    SafeForAuthentication = $false
    Limitations = 'Task/process SID agreement is diagnostic only; connected-pipe identity and executable trust are not established.'
} | ConvertTo-Json -Depth 5

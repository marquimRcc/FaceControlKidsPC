<#
.SYNOPSIS
  Diagnostica tarefa e processo que hospeda FaceKidsAuthPipe (somente leitura).
.DESCRIPTION
  Nao conecta ao pipe, nao abre webcam, nao consulta rostos, nao modifica
  tarefas ou logon. A observacao de processos nao prova a identidade de um
  servidor Named Pipe conectado: GetNamedPipeServerProcessId e validacao de
  token no cliente nativo ainda precisam de ensaio em VM.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName 'FaceKidsAuthService' -ErrorAction SilentlyContinue
$taskReport = if ($null -eq $task) {
    [pscustomobject]@{
        Present = $false
        Principal = $null
        LogonType = $null
        RunLevel = $null
        State = $null
    }
} else {
    [pscustomobject]@{
        Present = $true
        Principal = $task.Principal.UserId
        LogonType = [string]$task.Principal.LogonType
        RunLevel = [string]$task.Principal.RunLevel
        State = [string]$task.State
    }
}

# A enumeração usa apenas metadados de processos, sem capturar comandos
# completos, senhas, fotos ou quaisquer frames da câmera.
$observed = @(
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*-m facekids.auth_service*' } |
        ForEach-Object {
            $identity = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
            [pscustomobject]@{
                ProcessId = [int]$_.ProcessId
                SessionId = [int]$_.SessionId
                OwnerName = if ($identity) { $identity.User } else { $null }
                OwnerDomain = if ($identity) { $identity.Domain } else { $null }
            }
        }
)

$policyKey = 'HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider'
$policy = Get-ItemProperty -LiteralPath $policyKey -ErrorAction SilentlyContinue
$enforceSid = ($null -ne $policy -and $policy.EnforceAuthServiceSid -eq 1)

[pscustomobject]@{
    TrustEnforcedByConfiguration = [bool]$enforceSid
    ExpectedServiceSidConfigured = [bool]($policy -and $policy.AuthServiceSid)
    Task = $taskReport
    AuthProcesses = $observed
    NamedPipeServerIdentityVerified = $false
    SafeForAuthentication = $false
} | ConvertTo-Json -Depth 5

#Requires -Version 5.1
<#
.SYNOPSIS
  FaceKids VM: preflight de login COM diagnostico detalhado e historico persistente.
.DESCRIPTION
  Nunca instala CP, altera senhas, servicos, quotas ou configura o Windows.
  Unica escrita: arquivos de log no workspace isolado do laboratorio.
  A autenticação Windows e as senhas continuam sujeitas a teste manual.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Somente Windows convidado VirtualBox.'
}
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if (([string]$computer.Manufacturer + ' ' + [string]$computer.Model) -notmatch '(?i)VirtualBox|innotek') {
    throw 'RECUSADO: diagnostico exclusivo da VM VirtualBox.'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.Name.Split('\')[-1] -ieq 'Filhos') {
    throw 'Execute na conta administrativa da VM, nao em Filhos.'
}

$lab = Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab'
$root = Join-Path $lab 'codigo-developer'
$python = Join-Path $lab '.venv\Scripts\python.exe'
$db = Join-Path $lab 'dados-isolados\data\criancas.sqlite3'
$workerFile = Join-Path $lab 'vm-auth-worker.json'
$serverStatusFile = Join-Path $lab 'vm-auth-status.json'
$stage = Join-Path $lab 'scripts\FaceKids-VM-Autenticacao.ps1'
$logDir = Join-Path $lab 'logs'
$historyFile = Join-Path $logDir 'facekids-vm-events.jsonl'
$lastFile = Join-Path $logDir 'passo2-ultimo.json'
$clsid = '{FAC0D042-3DD0-4A8C-9F18-440C44330C20}'
$cpKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
$comKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$clsid"
$policyKey = 'HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider'
$labDll = Join-Path $env:ProgramData 'FaceKids-VM-CP-Lab\FaceKidsCredentialProvider.dll'
$familyDll = Join-Path $env:ProgramData 'FaceKids\FaceKidsCredentialProvider.dll'

function Test-AuthPipePing {
    $pipe = $null
    try {
        $pipe = [System.IO.Pipes.NamedPipeClientStream]::new(
            '.', 'FaceKidsAuthPipe', [System.IO.Pipes.PipeDirection]::InOut,
            [System.IO.Pipes.PipeOptions]::Asynchronous)
        $pipe.Connect(3000)
        $request = [Text.Encoding]::ASCII.GetBytes('PING' + [char]10)
        $pipe.Write($request, 0, $request.Length)
        $pipe.Flush()
        $buffer = New-Object byte[] 4096
        $operation = $pipe.BeginRead($buffer, 0, $buffer.Length, $null, $null)
        try {
            if (-not $operation.AsyncWaitHandle.WaitOne(6000)) {
                return [pscustomobject]@{ Responding = $false; Code = 'PIPE_TIMEOUT' }
            }
            $n = $pipe.EndRead($operation)
        } finally {
            $operation.AsyncWaitHandle.Close()
        }
        if ($n -lt 1) {
            return [pscustomobject]@{ Responding = $false; Code = 'PIPE_NO_RESPONSE' }
        }
        $response = [Text.Encoding]::UTF8.GetString($buffer, 0, $n) | ConvertFrom-Json
        if ($response.status -eq 'PONG') {
            return [pscustomobject]@{ Responding = $true; Code = 'IPC_PONG' }
        }
        return [pscustomobject]@{ Responding = $false; Code = 'PIPE_UNEXPECTED_RESPONSE' }
    } catch [System.TimeoutException] {
        return [pscustomobject]@{ Responding = $false; Code = 'PIPE_UNAVAILABLE' }
    } catch {
        return [pscustomobject]@{
            Responding = $false; Code = 'PIPE_CONNECT_OR_READ_ERROR'
        }
    } finally {
        if ($pipe) { $pipe.Dispose() }
    }
}

function Get-WorkerDiagnostics {
    $data = [ordered]@{
        Reason = 'NOT_CHECKED'
        TrackedPid = $null
        MatchingSid = $false
        OtherAuthPids = @()
    }
    try {
        # Only process IDs are recorded; no command lines, faces, names or secrets.
        $all = @(Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -and $_.CommandLine -match 'facekids[.]auth_service'
            })
        $data.OtherAuthPids = @($all | ForEach-Object { [int]$_.ProcessId })
    } catch {
        $data.Reason = 'PROCESS_INVENTORY_UNAVAILABLE'
    }
    if (-not (Test-Path -LiteralPath $workerFile -PathType Leaf)) {
        $data.Reason = 'WORKER_RECORD_MISSING'
        return [pscustomobject]$data
    }
    try {
        $state = Get-Content -LiteralPath $workerFile -Raw -ErrorAction Stop |
            ConvertFrom-Json -ErrorAction Stop
    } catch {
        $data.Reason = 'WORKER_RECORD_UNREADABLE'
        return [pscustomobject]$data
    }
    if (-not $state.processId -or -not $state.python) {
        $data.Reason = 'WORKER_RECORD_INCOMPLETE'
        return [pscustomobject]$data
    }
    if ([string]$state.python -ine $python) {
        $data.Reason = 'WORKER_PYTHON_PATH_MISMATCH'
        return [pscustomobject]$data
    }
    $trackedPid = [int]$state.processId
    $data.TrackedPid = $trackedPid
    try {
        $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $trackedPid) -ErrorAction Stop
        if (-not $p) {
            $data.Reason = 'WORKER_EXITED_OR_STALE_PID'
            return [pscustomobject]$data
        }
        if (-not $p.ExecutablePath -or
            (Split-Path $p.ExecutablePath -Leaf) -notin @('python.exe','pythonw.exe')) {
            $data.Reason = 'WORKER_EXECUTABLE_MISMATCH_OR_UNREADABLE'
            return [pscustomobject]$data
        }
        if (-not $p.CommandLine -or $p.CommandLine -notmatch 'facekids[.]auth_service' -or
            $p.CommandLine -notlike ('*'+$serverStatusFile+'*')) {
            $data.Reason = 'WORKER_COMMANDLINE_MISMATCH_OR_UNREADABLE'
            return [pscustomobject]$data
        }
        try {
            $reported = Get-Content -LiteralPath $serverStatusFile -Raw -ErrorAction Stop |
                ConvertFrom-Json -ErrorAction Stop
        } catch {
            $data.Reason = 'SERVER_STATUS_MISSING_OR_UNREADABLE'
            return [pscustomobject]$data
        }
        if ([int]$reported.pid -ne $trackedPid) {
            $data.Reason = 'WORKER_TRACKED_PID_DIFFERS_FROM_SERVER'
            return [pscustomobject]$data
        }
        try {
            $owner = Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid -ErrorAction Stop
            if ($owner.ReturnValue -ne 0 -or -not $owner.Sid) {
                $data.Reason = 'WORKER_SID_QUERY_FAILED'
                return [pscustomobject]$data
            }
            if ([string]$owner.Sid -ne [string]$identity.User.Value) {
                $data.Reason = 'WORKER_OWNER_SID_MISMATCH'
                return [pscustomobject]$data
            }
            $data.MatchingSid = $true
            $data.Reason = 'WORKER_VERIFIED'
            return [pscustomobject]$data
        } catch {
            $data.Reason = 'WORKER_SID_QUERY_EXCEPTION'
            return [pscustomobject]$data
        }
    } catch {
        $data.Reason = 'PROCESS_QUERY_EXCEPTION'
        return [pscustomobject]$data
    }
}

function Save-Diagnostic {
    param($Report)
    try {
        New-Item -ItemType Directory -Path $logDir -Force -ErrorAction Stop | Out-Null
        $line = ConvertTo-Json -InputObject $Report -Depth 7 -Compress
        Add-Content -LiteralPath $historyFile -Value $line -Encoding UTF8 -ErrorAction Stop
        $pretty = ConvertTo-Json -InputObject $Report -Depth 7
        Set-Content -LiteralPath $lastFile -Value $pretty -Encoding UTF8 -ErrorAction Stop
        Write-Host ('Historico: ' + $historyFile) -ForegroundColor DarkCyan
        Write-Host ('Ultima execucao: ' + $lastFile) -ForegroundColor DarkCyan
    } catch {
        Write-Warning ('LOG_NAO_GRAVADO: ' + $_.Exception.Message)
    }
}

$admin = Get-LocalUser -Name $identity.Name.Split('\')[-1] -ErrorAction SilentlyContinue
$child = Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue
$localAdmins = @(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction SilentlyContinue)
$member = [bool](@($localAdmins | Where-Object {
    $_.SID -and $_.SID.Value -eq [string]$identity.User.Value
}).Count -gt 0)
$worker = Get-WorkerDiagnostics
$ipc = Test-AuthPipePing
$assets = (Test-Path -LiteralPath $python -PathType Leaf) -and
          (Test-Path -LiteralPath $db -PathType Leaf) -and
          (Test-Path -LiteralPath $stage -PathType Leaf) -and
          (Test-Path -LiteralPath (Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll') -PathType Leaf)
$cpAbsent = -not ((Test-Path -LiteralPath $cpKey) -or
                 (Test-Path -LiteralPath $comKey) -or
                 (Test-Path -LiteralPath $policyKey) -or
                 (Test-Path -LiteralPath $labDll))
$checks = [ordered]@{
    VmVirtualBox = $true
    CurrentAdminAccountEnabled = [bool]($admin -and $admin.Enabled)
    CurrentAccountInLocalAdministrators = $member
    FilhosAccountEnabled = [bool]($child -and $child.Enabled)
    LabAssetsAvailable = [bool]$assets
    AuthWorkerRunningAsCurrentAccount = [bool]$worker.MatchingSid
    IpcPongConfirmed = [bool]$ipc.Responding
    CredentialProviderNotRegistered = $cpAbsent
    FamilyCredentialProviderDllAbsent = -not (Test-Path -LiteralPath $familyDll)
}
$blocked = @($checks.Values | Where-Object { -not [bool]$_ }).Count -gt 0
$status = if ($blocked) { 'BLOCKED' } else { 'READY_TECHNICALLY' }
$reason = if (-not $worker.MatchingSid) {
    $worker.Reason
} elseif (-not $ipc.Responding) {
    $ipc.Code
} elseif ($blocked) {
    'OTHER_PRECONDITION_FAILED'
} else {
    'PRECHECK_PASSED'
}

Write-Host ''
Write-Host '=== FaceKids VM - PASSO 2: DIAGNOSTICO COM HISTORICO ===' -ForegroundColor Cyan
foreach ($name in $checks.Keys) {
    $ok = [bool]$checks[$name]
    $label = if ($ok) { 'OK' } else { 'ATENCAO' }
    Write-Host ('[{0}] {1}' -f $label, $name)
}
Write-Host ('Worker registrado PID: ' + $(if ($worker.TrackedPid) { $worker.TrackedPid } else { 'AUSENTE' }))
Write-Host ('Motivo do worker: ' + $worker.Reason)
Write-Host ('Outros processos auth observados (PIDs): ' + $(if ($worker.OtherAuthPids.Count) {
    $worker.OtherAuthPids -join ','
} else { 'NENHUM' }))
Write-Host ('Teste independente de IPC: ' + $ipc.Code)
Write-Host 'Login administrativo convencional: VALIDACAO MANUAL PENDENTE.'
Write-Host 'Senha Windows esperada de Filhos: VALIDACAO MANUAL PENDENTE.'

$recommendation = if (-not $worker.MatchingSid) {
    'Revisar processo e registro do worker. Se nao houver outro autenticador, iniciar via -Action StartAuth/RestartAuth.'
} elseif (-not $ipc.Responding) {
    'Rever porta IPC, logs vm-auth-err.log e estado do autenticador antes de prosseguir.'
} elseif ($blocked) {
    'Corrigir itens ATENCAO antes de instalar o Credential Provider.'
} else {
    'Preflight tecnico aprovado. Confirmar manualmente login convencional e senha Windows de Filhos.'
}
Write-Host ('Resultado: ' + $status)
Write-Host ('Proxima acao: ' + $recommendation) -ForegroundColor $(if ($blocked) {'Yellow'} else {'Green'})

$report = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    source = 'step2_preflight'
    action = 'diagnose'
    status = $status
    reason_code = $reason
    checks = $checks
    worker = [ordered]@{
        reason = $worker.Reason
        tracked_pid = $worker.TrackedPid
        candidate_pids = @($worker.OtherAuthPids)
        owner_sid_matches_current = [bool]$worker.MatchingSid
    }
    ipc = $ipc.Code
    manual_login_check = 'NOT_VERIFIED_BY_SCRIPT'
    manual_filhos_password_check = 'NOT_VERIFIED_BY_SCRIPT'
    remediation = $recommendation
}
Save-Diagnostic -Report $report
if ($blocked) {
    Write-Warning 'PRECHECK_BLOQUEADO: nao execute ActivateCP. O motivo e o codigo acima; nenhum componente Windows foi alterado.'
} else {
    Write-Host 'Preflight tecnico aprovado. Ainda NAO autoriza ActivateCP sem as confirmacoes manuais.' -ForegroundColor Green
}

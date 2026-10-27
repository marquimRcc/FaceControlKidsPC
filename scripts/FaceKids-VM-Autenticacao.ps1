#Requires -Version 5.1
<#
 FaceKids VM-only staged Windows logon integration.
 StartAuth starts an INTERACTIVE user process, NOT an SCM service.
 No action touches the household main installation. CP activation is opt-in.
#>
[CmdletBinding()]
param(
    [ValidateSet('Status','StartAuth','RestartAuth','Ping','FaceProbe','ActivateCP','Rollback')]
    [string]$Action = 'Status',
    [switch]$RecoveryConfirmed,
    [switch]$FixedPasswordConfirmed
)
$ErrorActionPreference='Stop'
$marker='FaceKids-VM-CP-Lab-v1'
$clsid='{FAC0D042-3DD0-4A8C-9F18-440C44330C20}'
$cpKey="HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
$comKey="Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$clsid"
$policyKey='HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider'
$lab=Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab'
$root=Join-Path $lab 'codigo-developer'
$python=Join-Path $lab '.venv\Scripts\python.exe'
$db=Join-Path $lab 'dados-isolados\data\criancas.sqlite3'
$statusFile=Join-Path $lab 'vm-auth-status.json'
$workerFile=Join-Path $lab 'vm-auth-worker.json'
$dllSource=Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll'
$dllFolder=Join-Path $env:ProgramData 'FaceKids-VM-CP-Lab'
$dllTarget=Join-Path $dllFolder 'FaceKidsCredentialProvider.dll'
$regsvr=Join-Path $env:WINDIR 'System32\regsvr32.exe'

function Assert-Guest {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Exige Windows convidado.'
    }
    $hostInfo=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    if (([string]$hostInfo.Manufacturer + ' ' + [string]$hostInfo.Model) -notmatch '(?i)innotek|VirtualBox') {
        throw 'RECUSADO: somente VM VirtualBox.'
    }
    $current=[Security.Principal.WindowsIdentity]::GetCurrent()
    if ($current.Name.Split('\')[-1] -ieq 'Filhos') {
        throw 'RECUSADO: execute na conta ADMINISTRATIVA da VM, nao em Filhos.'
    }
    return $current
}
function Require-Admin {
    param($Current)
    $principal=[Security.Principal.WindowsPrincipal]::new($Current)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Para alterar o login, abra PowerShell COMO ADMINISTRADOR na VM.'
    }
}
function Require-Assets {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $root 'facekids\auth_service.py') -PathType Leaf) -or
        -not (Test-Path -LiteralPath $db -PathType Leaf)) {
        throw 'Laboratorio incompleto: use primeiro o Painel dos Pais na developer para cadastrar o rosto.'
    }
    foreach($name in @('face_detection_yunet_2023mar.onnx','face_recognition_sface_2021dec.onnx')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root ('models\' + $name)) -PathType Leaf)) {
            throw ('Modelo facial ausente: ' + $name)
        }
    }
}
function Require-Filhos {
    $account=Get-LocalUser -Name 'Filhos' -ErrorAction Stop
    if (-not $account.Enabled -or -not $account.SID) { throw 'Conta Filhos indisponivel.' }
    return [string]$account.SID.Value
}
function Get-Worker {
    # Track the real server PID, which can differ from the venv launcher.
    if (-not (Test-Path -LiteralPath $workerFile -PathType Leaf)) { return $null }
    try {
        $state=Get-Content -LiteralPath $workerFile -Raw | ConvertFrom-Json
        if ($state.python -ne $python -or -not $state.processId) { return $null }
        $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$state.processId) -ErrorAction SilentlyContinue
        if (-not $p -or -not $p.ExecutablePath) { return $null }
        $exe=Split-Path $p.ExecutablePath -Leaf
        if ($exe -notin @('python.exe','pythonw.exe')) { return $null }
        if (-not $p.CommandLine -or $p.CommandLine -notmatch 'facekids[.]auth_service' -or
            $p.CommandLine -notlike ('*'+$statusFile+'*')) { return $null }
        $serverState=Get-Content -LiteralPath $statusFile -Raw -ErrorAction Stop | ConvertFrom-Json
        if ([int]$serverState.pid -ne [int]$p.ProcessId) { return $null }
        $owner=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid -ErrorAction Stop
        $expectedSid=[string]([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
        if ($owner.ReturnValue -ne 0 -or [string]$owner.Sid -ne $expectedSid) { return $null }
        return $p
    } catch { return $null }
}
function Get-WorkerSid {
    param([int]$ProcessId)
    $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $ProcessId) -ErrorAction Stop
    if (-not $p) { throw 'Worker terminou.' }
    $s=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid -ErrorAction Stop
    if ($s.ReturnValue -ne 0 -or -not $s.Sid) { throw 'SID do worker indisponivel.' }
    return [string]$s.Sid
}
function Require-Worker {
    $p=Get-Worker
    if (-not $p) { throw 'Worker ausente: execute -Action StartAuth primeiro.' }
    return $p
}
function Invoke-AuthPipe {
    param([ValidateSet('PING','AUTH_QUERY')][string]$Command)
    $pipe=[System.IO.Pipes.NamedPipeClientStream]::new('.', 'FaceKidsAuthPipe',
        [System.IO.Pipes.PipeDirection]::InOut, [System.IO.Pipes.PipeOptions]::Asynchronous)
    try {
        $pipe.Connect(4000)
        $request=[Text.Encoding]::ASCII.GetBytes($Command + [char]10)
        $pipe.Write($request,0,$request.Length)
        $pipe.Flush()
        $buffer=New-Object byte[] 4096
        $operation=$pipe.BeginRead($buffer,0,$buffer.Length,$null,$null)
        try {
            if (-not $operation.AsyncWaitHandle.WaitOne(12000)) {
                throw 'Timeout de resposta do FaceKidsAuthPipe.'
            }
            $count=$pipe.EndRead($operation)
        } finally {
            $operation.AsyncWaitHandle.Close()
        }
        if ($count -le 0) { throw 'Pipe encerrou sem resposta.' }
        return ([Text.Encoding]::UTF8.GetString($buffer,0,$count) | ConvertFrom-Json)
    } finally { $pipe.Dispose() }
}
function Stop-OurWorker {
    $p=Get-Worker
    if ($p) { Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction Stop }
    Remove-Item -LiteralPath $workerFile -Force -ErrorAction SilentlyContinue
}
function Assert-OurCp {
    $policy=Get-ItemProperty -LiteralPath $policyKey -ErrorAction SilentlyContinue
    if (-not $policy -or $policy.VmInstallerMarker -ne $marker) {
        throw 'Registro de CP nao pertence ao laboratorio desta VM. Recusado alterar.'
    }
}
function Remove-OurCp {
    if ((Test-Path -LiteralPath $cpKey) -or
        (Test-Path -LiteralPath $comKey) -or
        (Test-Path -LiteralPath $policyKey)) {
        Assert-OurCp
        if (Test-Path -LiteralPath $dllTarget -PathType Leaf) {
            $unreg=Start-Process -FilePath $regsvr -ArgumentList ('/s /u "'+$dllTarget+'"') -Wait -PassThru
            if ($unreg.ExitCode -ne 0) { throw 'Falha ao desregistrar DLL; recupere o acesso administrativo e remova a DLL de laboratorio manualmente.' }
        }
        Remove-Item -LiteralPath $cpKey -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $comKey -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $policyKey -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $cpKey) { throw 'CP ainda registrado. Restaure o snapshot externo.' }
    }
}
$current=Assert-Guest
if ($Action -eq 'RestartAuth') {
    # Do not stop the verified worker unless the replacement can be launched.
    Require-Assets
    $null=Require-Filhos
    $existing=Get-Worker
    if ($existing) {
        $sid=Get-WorkerSid -ProcessId ([int]$existing.ProcessId)
        if ($sid -ne [string]$current.User.Value) {
            throw 'Recusado reiniciar autenticador pertencente a outro SID.'
        }
        Stop-OurWorker
    }
    $Action='StartAuth'
}
switch ($Action) {
    'Status' {
        $p=Get-Worker
        $policy=Get-ItemProperty -LiteralPath $policyKey -ErrorAction SilentlyContinue
        [pscustomobject]@{
            VM='VirtualBox'; Codigo=$root; Python=(Test-Path -LiteralPath $python)
            BancoFacial=(Test-Path -LiteralPath $db); WorkerAtivo=[bool]$p
            WorkerPID=if($p){$p.ProcessId}else{$null}
            WorkerSID=if($p){Get-WorkerSid -ProcessId ([int]$p.ProcessId)}else{$null}
            ProviderRegistrado=(Test-Path -LiteralPath $cpKey)
            ProviderDaVM=($policy -and $policy.VmInstallerMarker -eq $marker)
            DLLInstalada=(Test-Path -LiteralPath $dllTarget)
            DesbloqueioWindowsHomologado=$false
        } | Format-List
    }
    'StartAuth' {
        Require-Assets
        $null=Require-Filhos
        if (Test-Path -LiteralPath $cpKey) { Assert-OurCp }
        if (Get-Worker) {
            Write-Host 'Worker ja ativo. Execute -Action Ping.' -ForegroundColor Green
            break
        }
        $other=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'facekids[.]auth_service' })
        if($other.Count -gt 0){throw 'Existe outro autenticador. Recusado disputar webcam/mutex.'}
        $env:FACEKIDS_VM_LAB_DIR=Join-Path $lab 'dados-isolados'
        $env:FACEKIDS_VM_LAB_ACK='ISOLATED_VM_ONLY'
        $env:FACEKIDS_VM_SHADOW='0'
        Remove-Item -LiteralPath $statusFile -Force -ErrorAction SilentlyContinue
        $cmd='-m facekids.auth_service --camera-backend dshow --status-file "'+$statusFile+'"'
        $p=Start-Process -FilePath $python -ArgumentList $cmd -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lab 'vm-auth-out.log') -RedirectStandardError (Join-Path $lab 'vm-auth-err.log')
        try {
            $sid=Get-WorkerSid -ProcessId $p.Id
            if($sid -ne [string]$current.User.Value){throw 'Worker com SID inesperado.'}
            @{processId=$p.Id;python=$python;sid=$sid} | ConvertTo-Json | Set-Content -LiteralPath $workerFile -Encoding UTF8
            $ready=$false
            for($i=0;$i -lt 15;$i++){
                Start-Sleep -Seconds 1
                $p.Refresh()
                if($p.HasExited){throw ('Worker encerrou: '+$p.ExitCode)}
                if(Test-Path -LiteralPath $statusFile){
                    $s=Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json
                    if($s.phase -eq 'listening'){$ready=$true;break}
                }
            }
            if(-not $ready){throw 'Nao entrou no estado listening em 15 s.'}
            # status.pid belongs to the server actually answering the pipe.
            # It may differ from Start-Process -PassThru PID on Windows venv.
            # The status JSON was read into $s in the loop above.
            # Never read $status here: it is undefined and coerces to PID 0.
            $actualPid=[int]$s.pid
            if ($actualPid -lt 1) { throw 'Servidor nao publicou PID valido.' }
            $actual=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $actualPid) -ErrorAction Stop
            if (-not $actual -or -not $actual.CommandLine -or
                $actual.CommandLine -notmatch 'facekids[.]auth_service' -or
                $actual.CommandLine -notlike ('*'+$statusFile+'*')) {
                throw 'PID reportado no status nao pertence ao servidor facial do laboratorio.'
            }
            $actualSid=Get-WorkerSid -ProcessId $actualPid
            if ($actualSid -ne [string]$current.User.Value) {
                throw 'Servidor facial em outro SID.'
            }
            @{processId=$actualPid;launcherPid=$p.Id;python=$python;sid=$actualSid} |
                ConvertTo-Json | Set-Content -LiteralPath $workerFile -Encoding UTF8
            Write-Host ('Autenticador interativo iniciado (janela oculta), servidor PID '+$actualPid+
                ', lancador PID '+$p.Id) -ForegroundColor Green
            Write-Warning 'NAO E SCM; depende da sessao administrativa permanecer aberta.'
        } catch {
            $p.Refresh()
            if(-not $p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}
            Remove-Item -LiteralPath $workerFile -Force -ErrorAction SilentlyContinue
            throw
        }
    }
    'Ping' {
        $null=Require-Worker
        $response=Invoke-AuthPipe -Command PING
        if($response.status -ne 'PONG'){throw ('Resposta inesperada: '+$response.status)}
        Write-Host 'IPC PONG confirmado, sem acionar a webcam.' -ForegroundColor Green
    }
    'FaceProbe' {
        $null=Require-Worker
        $response=Invoke-AuthPipe -Command AUTH_QUERY
        # NUNCA imprimir password nem o JSON completo.
        [pscustomobject]@{
            Status=$response.status
            PerfilId=if($response.data){$response.data.child_id}else{$null}
            Saldo=if($response.data){$response.data.remaining}else{$null}
            Protocolo=$response.protocol_marker
        } | Format-List
        if($response.status -ne 'ALLOW'){throw 'Reconhecimento falhou; nao registre o CP.'}
    }
    'ActivateCP' {
        Require-Admin $current
        Require-Assets
        $targetSid=Require-Filhos
        if(-not ($RecoveryConfirmed -and $FixedPasswordConfirmed)){
            throw 'Exige -RecoveryConfirmed -FixedPasswordConfirmed: confirme login administrativo e senha Windows de Filhos.'
        }
        if(-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess){
            throw 'Execute PowerShell x64 na VM para instalar DLL x64.'
        }
        if((Test-Path -LiteralPath $cpKey) -or (Test-Path -LiteralPath $comKey) -or
           (Test-Path -LiteralPath $policyKey)){
            throw 'CP/COM/politica ja existentes. Recusado sobrescrever.'
        }
        if(-not (Test-Path -LiteralPath $dllSource -PathType Leaf)){throw 'DLL ausente no repositorio.'}
        $dllBytes=[IO.File]::ReadAllBytes($dllSource)
        $ascii=[Text.Encoding]::ASCII.GetString($dllBytes)
        if($dllBytes.Length -lt 10240 -or -not $ascii.Contains('FACEKIDS_IPC_V1') -or
           -not $ascii.Contains('FACEKIDS_BOOT_RETRY_V1')){
            throw 'DLL nao atende aos marcadores minimos do protocolo.'
        }
        $p=Require-Worker
        $serverSid=Get-WorkerSid -ProcessId ([int]$p.ProcessId)
        if($serverSid -ne [string]$current.User.Value){throw 'SID do autenticador divergente.'}
        $pong=Invoke-AuthPipe -Command PING
        if($pong.status -ne 'PONG'){throw 'Pipe nao esta pronto.'}
        Write-Host 'Olhe para a webcam para a prova facial imediatamente anterior ao registro.'
        $face=Invoke-AuthPipe -Command AUTH_QUERY
        if($face.status -ne 'ALLOW' -or $face.user -ne 'Filhos' -or
           $face.protocol_marker -ne 'FACEKIDS_IPC_V1' -or [int]$face.data.remaining -lt 1){
            throw ('Registro RECUSADO: resposta facial '+$face.status)
        }
        # O CP LEGADO utiliza senha Windows fixa "1". Nunca alterar senha aqui.
        New-Item -ItemType Directory -Path $dllFolder -Force | Out-Null
        Copy-Item -LiteralPath $dllSource -Destination $dllTarget -Force
        New-Item -Path $policyKey -Force | Out-Null
        try {
            New-ItemProperty -Path $policyKey -Name VmInstallerMarker -PropertyType String -Value $marker -Force | Out-Null
            New-ItemProperty -Path $policyKey -Name TargetUserSid -PropertyType String -Value $targetSid -Force | Out-Null
            New-ItemProperty -Path $policyKey -Name AuthServiceSid -PropertyType String -Value $serverSid -Force | Out-Null
            New-ItemProperty -Path $policyKey -Name EnforceAuthServiceSid -PropertyType DWord -Value 1 -Force | Out-Null
            $installed=Start-Process -FilePath $regsvr -ArgumentList ('/s "'+$dllTarget+'"') -Wait -PassThru
            if($installed.ExitCode -ne 0){throw ('regsvr32 retornou '+$installed.ExitCode)}
            if(-not (Test-Path -LiteralPath $cpKey)){throw 'Credential Provider nao foi registrado.'}
            $inproc=(Get-Item -LiteralPath (Join-Path $comKey 'InprocServer32') -ErrorAction Stop).GetValue('')
            if($inproc -ne $dllTarget){
                throw 'InprocServer32 nao aponta para a DLL exclusiva da VM.'
            }
            Write-Host 'DLL registrada na VM, sem Win+L/logoff automatico.' -ForegroundColor Green
            Write-Warning 'Guarde o login convencional. Caso necessario, remova o CP com -Action Rollback na conta administrativa.'
        } catch {
            Write-Warning ('Falha no registro: '+$_.Exception.Message)
            Remove-OurCp
            throw
        }
    }
    'Rollback' {
        Require-Admin $current
        Remove-OurCp
        Stop-OurWorker
        Write-Host 'CP da VM desregistrado, worker parado. Banco e fotos preservados.' -ForegroundColor Green
    }
}

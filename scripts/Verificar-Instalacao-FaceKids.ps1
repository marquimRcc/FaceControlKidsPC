#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$tasks = foreach ($name in @('FaceKidsAuthService', 'FaceKidsFilhosAgent', 'FaceKidsBootAuth')) {
    try {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        [pscustomobject]@{
            name = $name
            registered = $true
            state = [string]$task.State
            user = [string]$task.Principal.UserId
            logon_type = [string]$task.Principal.LogonType
            run_level = [string]$task.Principal.RunLevel
            action = [string]$task.Actions[0].Execute
            arguments = [string]$task.Actions[0].Arguments
        }
    } catch {
        [pscustomobject]@{ name = $name; registered = $false; error = $_.Exception.Message }
    }
}
$result = [pscustomobject]@{
    account_exists = [bool](Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue)
    provider_registered = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{FAC0D042-3DD0-4A8C-9F18-440C44330C20}'
    installation_ready = Test-Path 'C:\ProgramData\FaceKids\installation-ready.json'
    tasks = @($tasks)
    auth_processes = @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like '*-m facekids.auth_service*' -or $_.CommandLine -like '*-m facekids.boot_auth*'
    } | ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; command = $_.CommandLine } })
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath 'C:\ProgramData\FaceKids\health_result.json' -Encoding UTF8

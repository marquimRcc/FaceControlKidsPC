<#
.SYNOPSIS
  Auditoria somente leitura da superficie de rede, firewall e politicas DNS/navegador do SafePCKids.
.DESCRIPTION
  Nao altera firewall, registro, servicos ou arquivos.
  Reporta onde a porta 8765 esta escutando, se a regra de firewall HTTP esta restrita
  a perfil Private e o estado das regras AdGuard / SafeSearch.
#>
[CmdletBinding()]
param(
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'

$listeners = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess
)

$remoteRule = Get-NetFirewallRule -Name 'SafePCKids_Remote_Control_HTTP' -ErrorAction SilentlyContinue
$remoteRuleReport = if ($remoteRule) {
    $profileText = [string]$remoteRule.Profile
    [pscustomobject]@{
        Exists = $true
        Enabled = [string]$remoteRule.Enabled
        Direction = [string]$remoteRule.Direction
        Action = [string]$remoteRule.Action
        Profile = $profileText
        PublicExposed = ($profileText -match 'Any|Public')
    }
} else {
    [pscustomobject]@{ Exists = $false }
}

$adguardRules = @(
    Get-NetFirewallRule -Name 'SafePCKids_AdGuard_*' -ErrorAction SilentlyContinue |
        Select-Object Name, Enabled, Direction, Action, Profile
)

$browserKeys = @(
    'HKLM:\SOFTWARE\Policies\Microsoft\Edge',
    'HKLM:\SOFTWARE\Policies\Google\Chrome',
    'HKLM:\SOFTWARE\Policies\BraveSoftware\Brave'
)
$browserPolicies = foreach ($key in $browserKeys) {
    if (Test-Path -LiteralPath $key) {
        $props = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Key = $key
            Present = $true
            DnsOverHttpsMode = $props.DnsOverHttpsMode
            ForceGoogleSafeSearch = $props.ForceGoogleSafeSearch
            ForceYouTubeRestrict = $props.ForceYouTubeRestrict
        }
    } else {
        [pscustomobject]@{ Key = $key; Present = $false }
    }
}

[pscustomobject]@{
    Port = $Port
    Listeners = $listeners
    RemoteFirewallRule = $remoteRuleReport
    AdGuardFirewallRuleCount = $adguardRules.Count
    BrowserPolicies = $browserPolicies
} | ConvertTo-Json -Depth 5

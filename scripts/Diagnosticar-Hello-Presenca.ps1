#Requires -Version 5.1
<#
.SYNOPSIS
  Read-only Windows Hello / Presence Sensing hardware preflight.
.DESCRIPTION
  Lists detected camera, biometric and sensor devices. Does NOT install,
  enroll, configure, unlock, lock, store credentials or store face data.
  Names and PnP classes cannot certify Windows Hello compatibility.
#>
[CmdletBinding()]
param([switch]$OpenSettings)

$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Este diagnostico requer Windows 10/11.'
}
Write-Host '=== FACEKIDS: CAMINHO PARA DESBLOQUEIO FACIAL WINDOWS ===' -ForegroundColor Cyan
Write-Host 'Somente leitura. Nao modifica contas, PIN, senha, drivers ou registro.'
Write-Host ''
$os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
Write-Host "Windows: $($os.Caption) - build $($os.BuildNumber)"
Write-Host ''

$present = @{}
if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
    Write-Warning 'Get-PnpDevice indisponivel. Nao foi possivel verificar as classes PnP.'
} else {
    foreach ($pnpClass in @('Camera','Image','Biometric','Sensor')) {
        $devices = @()
        try {
            $devices = @(Get-PnpDevice -PresentOnly -Class $pnpClass -ErrorAction Stop)
        } catch {
            # A PnP class may have no device, or be absent on some Windows builds.
            $devices = @()
        }
        $devices = @($devices | Where-Object { $_ -and $_.FriendlyName } |
                      Sort-Object FriendlyName -Unique)
        $present[$pnpClass] = $devices
        Write-Host "[$pnpClass] $($devices.Count) dispositivo(s):"
        if ($devices.Count -eq 0) {
            Write-Host '  Nenhum dispositivo listado.' -ForegroundColor DarkGray
        }
        foreach ($device in $devices) {
            Write-Host "  - $($device.FriendlyName) [$($device.Status)]"
        }
    }
}
Write-Host ''
try {
    $service = Get-Service -Name 'WbioSrvc' -ErrorAction Stop
    Write-Host "Windows Biometric Service: $($service.Status)"
} catch {
    Write-Host 'Windows Biometric Service: nao encontrado ou inacessivel.'
}
Write-Host ''

$cameras = @($present['Camera']) + @($present['Image'])
$names = @($cameras | Where-Object { $_ -and $_.FriendlyName } |
                      ForEach-Object { [string]$_.FriendlyName })
if ($names.Count -eq 0) {
    Write-Warning 'Nenhuma camera identificada pelo PnP. Verifique conexao e permissao.'
} elseif (@($names | Where-Object { $_ -match '(?i)\bIR\b|infrared|infravermelh' }).Count -gt 0) {
    Write-Host 'Candidato a camera infravermelha encontrado pelo NOME.' -ForegroundColor Yellow
    Write-Host 'IMPORTANTE: isto NAO comprova suporte ou configuracao do Windows Hello.'
} else {
    Write-Host 'Nao ha camera explicitamente rotulada IR na lista.' -ForegroundColor Yellow
    Write-Host 'Uma camera RGB comum nao basta para login facial Windows Hello.'
}
if ($present.ContainsKey('Sensor') -and $present['Sensor'].Count -gt 0) {
    Write-Host 'Dispositivos na classe Sensor presentes; isso NAO comprova sensor de presenca.'
} else {
    Write-Host 'Nenhum sensor PnP da classe Sensor; wake-on-approach pode nao estar disponivel.'
}
Write-Host ''
Write-Host 'PROXIMAS CHECAGENS VISUAIS (sem alterar configuracoes):'
Write-Host '  1. Configuracoes > Contas > Opcoes de entrada > Reconhecimento facial (Windows Hello).'
Write-Host '     Veja se aparece como DISPONIVEL para configurar, e qual requisito falta.'
Write-Host '  2. Configuracoes > Sistema > Energia e bateria > Tela, suspensao e hibernacao.'
Write-Host '     Veja se existe a opcao de acordar quando voce se aproxima.'
Write-Host '     No Windows 11 tambem pode aparecer Configuracoes > Privacidade > Deteccao de presenca.'
Write-Host ''
Write-Host 'RESULTADO: DIAGNOSTICO_SEM_ALTERACOES'
Write-Host 'Nao habilitamos desbloqueio facial nem ativacao ao aproximar-se.'
if ($OpenSettings) {
    Write-Host 'Abrindo SOMENTE a interface de opcoes de entrada...'
    Start-Process 'ms-settings:signinoptions'
}

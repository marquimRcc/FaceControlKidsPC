#Requires -Version 5.1
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

$user = Get-LocalUser -Name 'Filhos'
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
public static class FaceKidsUserProfile {
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    public static extern int CreateProfile(string sid, string name, StringBuilder path, uint size);
}
'@
$profilePath = New-Object System.Text.StringBuilder 1024
$status = [FaceKidsUserProfile]::CreateProfile($user.SID.Value, $user.Name, $profilePath, 1024)
if ($status -ne 0) { throw ('CreateProfile falhou: 0x{0:X8}' -f $status) }

$hive = 'FaceKidsFirstLogon_' + [Guid]::NewGuid().ToString('N')
$hiveFile = Join-Path $profilePath.ToString() 'NTUSER.DAT'
& reg.exe load "HKU\$hive" $hiveFile
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel carregar as preferencias de Filhos.' }
try {
    $preferences = @{
        'Software\Policies\Microsoft\Windows\OOBE' = @{ DisablePrivacyExperience = 1 }
        'Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo' = @{ Enabled = 0 }
        'Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement' = @{ ScoobeSystemSettingEnabled = 0 }
        'Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager' = @{
            SoftLandingEnabled = 0
            SystemPaneSuggestionsEnabled = 0
            'SubscribedContent-310093Enabled' = 0
            'SubscribedContent-338389Enabled' = 0
        }
        'Software\Microsoft\Windows\CurrentVersion\Privacy' = @{ TailoredExperiencesWithDiagnosticDataEnabled = 0 }
        'Software\Microsoft\InputPersonalization' = @{ RestrictImplicitInkCollection = 1; RestrictImplicitTextCollection = 1 }
        'Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy' = @{ HasAccepted = 0 }
    }
    foreach ($path in $preferences.Keys) {
        $key = [Microsoft.Win32.Registry]::Users.CreateSubKey("$hive\$path")
        try {
            foreach ($name in $preferences[$path].Keys) {
                $key.SetValue($name, $preferences[$path][$name], [Microsoft.Win32.RegistryValueKind]::DWord)
            }
        } finally {
            $key.Dispose()
        }
    }
    $location = [Microsoft.Win32.Registry]::Users.CreateSubKey(
        "$hive\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location")
    try { $location.SetValue('Value', 'Deny', [Microsoft.Win32.RegistryValueKind]::String) }
    finally { $location.Dispose() }
} finally {
    & reg.exe unload "HKU\$hive"
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel descarregar as preferencias de Filhos.' }
}

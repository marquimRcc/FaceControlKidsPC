# FaceKids - read-only Windows SID check from the parent's account.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Write-Host '=== FaceKids: Diagnostico Windows ===' -ForegroundColor Cyan
$branchName = (& git -C $root branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branchName -ne 'feature/windows-native-unlock-poc') {
    throw "Branch incorreta: $branchName"
}
Write-Host "Branch: $branchName"
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
Write-Host "Conta atual: $($me.Name)"
Write-Host "SID da conta atual: $($me.User.Value)"
$child = Get-LocalUser -Name 'Filhos' -ErrorAction Stop
if (-not $child.SID) { throw 'Nao foi possivel identificar o SID de Filhos.' }
Write-Host "Conta Filhos: $($child.Name)"
Write-Host "SID Filhos: $($child.SID.Value)"
Write-Host "Conta Filhos habilitada: $($child.Enabled)"
if ($me.User.Value -eq $child.SID.Value) { throw 'Execute na conta principal, nao em Filhos.' }
$regPath = 'HKLM:\SOFTWARE\FaceControlKidsPC\CredentialProvider'
$cfg = Get-ItemProperty -Path $regPath -Name TargetUserSid -ErrorAction SilentlyContinue
if ($null -eq $cfg) {
    Write-Host 'Provider: SID nao configurado no registro (comportamento esperado).'
} elseif ($cfg.TargetUserSid -ne $child.SID.Value) {
    Write-Warning "SID do registro NAO corresponde a Filhos: $($cfg.TargetUserSid)"
} else {
    Write-Host 'Provider: SID do registro corresponde a Filhos.'
}
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) { throw "Python virtual ausente: $py" }
Push-Location $root
try {
    Write-Host 'Executando testes de quotas e reconhecimento simulado...'
    & $py -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Testes falharam: $LASTEXITCODE" }
    Write-Host 'Consultando sessoes reais do Windows (WTS) sem alterar nada...'
    & $py -m facekids.windows_session_diagnostic
    if ($LASTEXITCODE -ne 0) { throw "Diagnostico WTS falhou: $LASTEXITCODE" }

} finally {
    Pop-Location
}
Write-Host 'PASS: SIDs identificados e testes Python aprovados.' -ForegroundColor Green
Write-Host 'Nenhuma alteracao foi feita no login ou registro do Windows.'

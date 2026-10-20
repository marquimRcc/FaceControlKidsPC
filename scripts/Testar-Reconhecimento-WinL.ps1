#Requires -Version 5.1
# Parent-only, read-only adult embedding matcher while Windows is Win+L locked.
# Does not alter Windows passwords, registry, services or credentials.
[CmdletBinding()]
param(
    [ValidateRange(20,300)][int]$Duration = 90,
    [ValidateRange(0,10)][int]$CameraIndex = 0
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Este diagnostico requer Windows 10/11.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne 'feature/parent-face-pilot') {
        throw "Branch incorreta: $branch; use feature/parent-face-pilot."
    }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Ambiente Python ausente. Execute primeiro scripts\Testar-Meu-Rosto.ps1.'
    }
    & $python -m unittest discover -s tests -p 'test_locked_face_probe.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Autotestes do diagnostico falharam.' }
    Write-Host 'Abrindo camera XWF-1080P para comparar APENAS com cadastro adulto existente.' -ForegroundColor Cyan
    Write-Host 'Aperte Win+L agora, fique na frente da webcam e desbloqueie com PIN/senha normal depois de ~50 s.'
    Write-Host 'SEM desbloqueio automatico. Nao salvara fotos, videos ou novos vetores.'
    & $python -m facekids.locked_face_probe --duration $Duration --camera-index $CameraIndex
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Diagnostico ainda inconclusivo ($LASTEXITCODE); envie a linha final e o resumo."
    } else {
        Write-Host 'PASS: correspondencia de rosto observada durante Win+L (somente diagnostico)' -ForegroundColor Green
    }
} finally {
    Pop-Location
}

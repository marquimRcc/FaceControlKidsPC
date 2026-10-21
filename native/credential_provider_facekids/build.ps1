#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir
try {
    $gpp = 'C:\Users\MarcosMiniPC\w64devkit\w64devkit\bin\g++.exe'
    if (-not (Test-Path $gpp)) {
        throw "Compilador g++ nao encontrado em $gpp"
    }

    Write-Host "[FaceKids] Compilando FaceKidsCredentialProvider.dll..." -ForegroundColor Cyan
    & $gpp -shared -std=c++17 -O2 -DINITGUID `
      dllmain.cpp FaceKidsProvider.cpp FaceKidsCredential.cpp FaceKidsProvider.def `
      -o FaceKidsCredentialProvider.dll `
      -lole32 -ladvapi32 -lsecur32 -luuid -lcredui
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar FaceKidsCredentialProvider.dll" }

    Write-Host "[FaceKids] Compilando TestProviderHost.exe..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 TestProviderHost.cpp -o TestProviderHost.exe -lole32 -luuid
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar TestProviderHost.exe" }

    Write-Host "[FaceKids] Compilando TestPipeClient.exe..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 TestPipeClient.cpp -o TestPipeClient.exe -lole32
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar TestPipeClient.exe" }

    Write-Host "[FaceKids] Build completo com sucesso!" -ForegroundColor Green
} finally {
    Pop-Location
}

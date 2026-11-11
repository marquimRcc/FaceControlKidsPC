#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir
try {
    $gpp = $null
    if (Get-Command g++.exe -ErrorAction SilentlyContinue) {
        $gpp = (Get-Command g++.exe).Source
    } elseif (Test-Path 'C:\Users\MarcosMiniPC\w64devkit\w64devkit\bin\g++.exe') {
        $gpp = 'C:\Users\MarcosMiniPC\w64devkit\w64devkit\bin\g++.exe'
    } elseif (Test-Path 'C:\msys64\mingw64\bin\g++.exe') {
        $gpp = 'C:\msys64\mingw64\bin\g++.exe'
    } elseif (Test-Path 'C:\msys64\ucrt64\bin\g++.exe') {
        $gpp = 'C:\msys64\ucrt64\bin\g++.exe'
    } elseif (Test-Path 'C:\ProgramData\mingw64\bin\g++.exe') {
        $gpp = 'C:\ProgramData\mingw64\bin\g++.exe'
    }
    if (-not $gpp) {
        throw "Compilador g++ nao encontrado no PATH nem nos locais padrao."
    }

    Write-Host "[SafePCKids] Usando compilador: $gpp" -ForegroundColor Cyan

    Write-Host "[SafePCKids] Compilando SafePCKidsCredentialProvider.dll..." -ForegroundColor Cyan
    & $gpp -shared -std=c++17 -O2 -static -static-libgcc -static-libstdc++ `
      dllmain.cpp SafePCKidsProvider.cpp SafePCKidsCredential.cpp SafePCKidsProvider.def `
      -o SafePCKidsCredentialProvider.dll `
      -lole32 -ladvapi32 -lsecur32 -luuid -lcredui
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar SafePCKidsCredentialProvider.dll" }

    Write-Host "[SafePCKids] Compilando TestProviderHost.exe..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 -static -static-libgcc -static-libstdc++ TestProviderHost.cpp -o TestProviderHost.exe -lole32 -luuid
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar TestProviderHost.exe" }

    Write-Host "[SafePCKids] Compilando TestPipeClient.exe..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 -static -static-libgcc -static-libstdc++ TestPipeClient.cpp -o TestPipeClient.exe -lole32
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar TestPipeClient.exe" }

    Write-Host "[SafePCKids] Testes isolados de JSON e identidade de servidor..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 -static -static-libgcc -static-libstdc++ TestJsonEnvelopeGuardPortable.cpp -o TestJsonEnvelopeGuardPortable.exe
    if ($LASTEXITCODE -ne 0) { throw "Falha no teste nativo do parser JSON" }

    & $gpp -std=c++17 -O2 -static -static-libgcc -static-libstdc++ TestPipePeerIdentity.cpp -o TestPipePeerIdentity.exe -ladvapi32
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar teste de SID do pipe" }

    Write-Host "[SafePCKids] Compilando teste de repeticao automatica..." -ForegroundColor Cyan
    & $gpp -std=c++17 -O2 -static -static-libgcc -static-libstdc++ -DSAFEPCKIDS_RETRY_HOST_TEST TestCredentialRetry.cpp SafePCKidsCredential.cpp SafePCKidsProvider.cpp `
        -o TestCredentialRetry.exe -lole32 -ladvapi32 -lsecur32 -luuid -lcredui
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar TestCredentialRetry.exe" }

    $objdump = Join-Path (Split-Path -Parent $gpp) 'objdump.exe'
    if (Test-Path -LiteralPath $objdump) {
        $imports = & $objdump -p SafePCKidsCredentialProvider.dll | Out-String
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel inspecionar imports da DLL.' }
        if ($imports -match '(?im)DLL Name:\s*(libgcc|libstdc\+\+|libwinpthread)') {
            throw 'DLL ainda depende do runtime MinGW externo; nao distribuir para LogonUI.'
        }
    }

    Write-Host "[SafePCKids] Build completo com sucesso!" -ForegroundColor Green
} finally {
    Pop-Location
}

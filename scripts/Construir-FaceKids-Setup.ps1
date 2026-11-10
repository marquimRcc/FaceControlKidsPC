#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$CertificatePath = $env:FACEKIDS_SIGNING_CERT,
    [string]$CertificatePassword = $env:FACEKIDS_SIGNING_PASSWORD,
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Ambiente de compilacao .venv ausente.' }
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilador .NET Framework x64 ausente.' }
$base = & $python -c 'import sys; assert sys.maxsize > 2**32; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0 -or -not $base) { throw 'Python x64 necessario para gerar o EXE.' }

function Invoke-FaceKidsCodeSign([string]$FilePath) {
    if (-not $CertificatePath -or -not (Test-Path -LiteralPath $CertificatePath)) {
        return
    }
    Write-Host "[FaceKids] Assinando digitalmente: $FilePath" -ForegroundColor Cyan
    try {
        $cert = $null
        if ($CertificatePassword) {
            $securePass = ConvertTo-SecureString $CertificatePassword -AsPlainText -Force
            $cert = Get-PfxCertificate -FilePath $CertificatePath -Password $securePass
        } else {
            $cert = Get-PfxCertificate -FilePath $CertificatePath
        }
        $sig = Set-AuthenticodeSignature -FilePath $FilePath -Certificate $cert -TimestampServer $TimestampServer -HashAlgorithm SHA256
        if ($sig.Status -notin @('Valid', 'UnknownError')) {
            Write-Warning "Assinatura de $FilePath retornou status: $($sig.Status) ($($sig.StatusMessage))"
        } else {
            Write-Host "[FaceKids] Arquivo assinado com sucesso ($($sig.Status))." -ForegroundColor Green
        }
    } catch {
        Write-Warning "Falha ao assinar $FilePath : $_"
    }
}

if ($CertificatePath -and (Test-Path -LiteralPath $CertificatePath)) {
    Write-Host "[FaceKids] Certificado de assinatura configurado: $CertificatePath" -ForegroundColor Green
} else {
    Write-Host "[FaceKids] Aviso: Nenhum certificado de assinatura fornecido. O instalador sera gerado sem assinatura digital." -ForegroundColor Yellow
}

$dist = Join-Path $root 'dist'
$null = New-Item -ItemType Directory -Path $dist -Force
$scratch = Join-Path $root ('build\windows-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $scratch 'payload'
$runtime = Join-Path $payload 'runtime'
$null = New-Item -ItemType Directory -Path $runtime -Force
try {
    foreach ($name in @('python.exe', 'pythonw.exe', 'LICENSE.txt', 'DLLs', 'tcl')) {
        Copy-Item -LiteralPath (Join-Path $base $name) -Destination $runtime -Recurse
    }
    Get-ChildItem -LiteralPath $base -Filter '*.dll' -File | Copy-Item -Destination $runtime
    $lib = Join-Path $runtime 'Lib'
    $sitePackages = Join-Path $lib 'site-packages'
    $null = New-Item -ItemType Directory -Path $sitePackages -Force
    Get-ChildItem -LiteralPath (Join-Path $base 'Lib') |
        Where-Object { $_.Name -notin @('site-packages', '__pycache__', 'test', 'ensurepip') } |
        Copy-Item -Destination $lib -Recurse
    $venvSite = Join-Path $root '.venv\Lib\site-packages'
    foreach ($pattern in @('numpy', 'numpy.libs', 'numpy-*.dist-info', 'cv2', 'opencv_python-*.dist-info')) {
        $items = @(Get-ChildItem -LiteralPath $venvSite -Filter $pattern)
        if (-not $items) { throw "Dependencia ausente no ambiente de compilacao: $pattern" }
        $items | Copy-Item -Destination $sitePackages -Recurse
    }
    foreach ($name in @('facekids', 'assets', 'models')) {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $payload -Recurse
    }
    $dllDir = Join-Path $payload 'native\credential_provider_facekids'
    $scriptsDir = Join-Path $payload 'scripts'
    $null = New-Item -ItemType Directory -Path $dllDir, $scriptsDir -Force
    $targetDll = Join-Path $dllDir 'FaceKidsCredentialProvider.dll'
    Copy-Item -LiteralPath (Join-Path $root 'native\credential_provider_facekids\FaceKidsCredentialProvider.dll') -Destination $targetDll
    Invoke-FaceKidsCodeSign -FilePath $targetDll
    foreach ($name in @('Ativar-Desbloqueio-No-Boot.ps1', 'Preparar-Perfil-Filhos.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $scriptsDir
    }
    if (Test-Path -LiteralPath (Join-Path $root 'LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $payload
    }
    Push-Location $payload
    try {
        & (Join-Path $runtime 'python.exe') -E -s -m facekids.package_check
        if ($LASTEXITCODE -ne 0) { throw "Runtime do pacote invalido (codigo $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = Join-Path $scratch 'FaceKidsPayload.zip'
    [System.IO.Compression.ZipFile]::CreateFromDirectory($payload, $zip)
    $candidate = Join-Path $scratch 'FaceKids-Instalador-Windows-x64.exe'
    $manifest = Join-Path $root 'packaging\windows-installer.manifest'
    $icon = Join-Path $root 'assets\facekids.ico'
    $compilerArgs = @(
        '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
        '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
        '/reference:System.Windows.Forms.dll', "/resource:$zip,FaceKidsPayload", "/out:$candidate",
        "/win32manifest:$manifest", "/win32icon:$icon", (Join-Path $root 'packaging\WindowsInstaller.cs')
    )
    & $compiler @compilerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o instalador.' }

    Copy-Item -LiteralPath $candidate -Destination $dist -Force
    $outputExe = Join-Path $dist 'FaceKids-Instalador-Windows-x64.exe'
    Invoke-FaceKidsCodeSign -FilePath $outputExe
    Get-FileHash -LiteralPath $outputExe -Algorithm SHA256
    $test = Start-Process -FilePath $outputExe -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru
    if ($test.ExitCode -ne 0) { throw "O EXE nao passou no autoteste (codigo $($test.ExitCode))." }
} finally {
    $resolved = (Resolve-Path -LiteralPath $scratch).Path
    $buildRoot = (Resolve-Path -LiteralPath (Join-Path $root 'build')).Path
    if ([IO.Path]::GetDirectoryName($resolved) -eq $buildRoot -and
        [IO.Path]::GetFileName($resolved) -match '^windows-[a-f0-9]{32}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

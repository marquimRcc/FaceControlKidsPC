[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$root = Join-Path $env:ProgramFiles 'SafePCKids'
$dataRoot = Join-Path $env:ProgramData 'SafePCKids'
$null = New-Item -ItemType Directory -Path $root, $dataRoot -Force

if ($sourceRoot -ne $root) {
    foreach ($folder in @('safepckids', 'models', 'scripts', 'assets', 'native')) {
        $source = Join-Path $sourceRoot $folder
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Componente do instalador ausente: $source"
        }
        Copy-Item -LiteralPath $source -Destination $root -Recurse -Force
    }
    foreach ($file in @('pyproject.toml', 'README.md', 'requirements.txt')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination $root -Force
    }
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = $null
    $pythonArgs = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $pythonCommand = 'py.exe'
        $pythonArgs = @('-3')
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $pythonCommand = 'python.exe'
    } elseif (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        Write-Host 'Instalando Python para o SafePCKids...'
        & winget.exe install --id Python.Python.3.12 --exact --silent --scope machine --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar Python automaticamente.' }
        $candidate = Get-ChildItem -Path "$env:ProgramFiles\Python312\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($candidate) { $pythonCommand = $candidate.FullName }
    }
    if (-not $pythonCommand) { throw 'Python 3 nao foi encontrado e nao foi possivel instala-lo automaticamente.' }

    & $pythonCommand @pythonArgs -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw 'Nao foi possivel preparar o Python do SafePCKids.'
    }
}

Write-Host 'Conferindo bibliotecas do SafePCKids...'
Push-Location $root
try {
    & $venvPython -c 'import cv2, numpy; import safepckids'
    if ($LASTEXITCODE -ne 0) {
        & $venvPython -m pip install --disable-pip-version-check -e $root
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar as bibliotecas do SafePCKids.' }
    }
    & $venvPython -c 'import cv2, numpy; import safepckids'
    if ($LASTEXITCODE -ne 0) { throw 'As bibliotecas do SafePCKids continuam indisponiveis.' }
} finally {
    Pop-Location
}

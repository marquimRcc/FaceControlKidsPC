#Requires -Version 5.1
<#
.SYNOPSIS
  FaceKids developer VM: download, prepare, preflight and open Parents Dashboard.
.DESCRIPTION
  Disposable Windows guest only. Never registers credential providers, SCM,
  tasks, Winlogon settings, firewall rules or local accounts. Source and
  SQLite/photos are isolated under LOCALAPPDATA/FaceKids-VM-Lab.
#>
[CmdletBinding()]
param(
    [ValidateRange(0,9)][int]$CameraIndex = 0,
    [switch]$SkipTests,
    [switch]$NoCameraProbe,
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Assert-VM {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Este launcher exige uma VM Windows.'
    }
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $signature = ('{0} {1}' -f $computer.Manufacturer, $computer.Model)
    if ($signature -notmatch '(?i)Virtual Machine|VMware|VirtualBox|QEMU|KVM|Xen|Parallels|innotek|HVM|Bochs|BHYVE') {
        throw 'RECUSADO: Windows nao reconhecido como maquina virtual. Nao execute no PC familiar.'
    }
    $account = ([Security.Principal.WindowsIdentity]::GetCurrent().Name -split '\\')[-1]
    if ($account -ieq 'Filhos') {
        throw 'Abra este primeiro launcher numa conta administrativa convencional da VM para acessar o Painel dos Pais.'
    }
    Write-Host ('[FaceKids VM] Convidado virtual: {0}' -f $signature) -ForegroundColor Cyan
    Write-Warning 'A identificacao de VM NAO comprova snapshot restauravel. Confirme o checkpoint no hipervisor antes de mexer no login.'
}

function Find-Python311 {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab\runtime\python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:ProgramFiles 'Python311\python.exe')
    )
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        try {
            $found = (& py.exe -3.11 -c 'import sys;print(sys.executable)' 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $found) {
                $candidates = @($found) + $candidates
            }
        } catch { }
    }
    foreach ($p in $candidates) {
        if (-not $p -or -not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
        try {
            & $p -c 'import sys,tkinter;assert sys.version_info[:2] == (3,11)'
            if ($LASTEXITCODE -eq 0) { return [string]$p }
        } catch { }
    }
    return $null
}

Assert-VM
$workspace = Join-Path $env:LOCALAPPDATA 'FaceKids-VM-Lab'
$repo = Join-Path $workspace 'codigo-developer'
$dataDir = Join-Path $workspace 'dados-isolados'
$venv = Join-Path $workspace '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$venvPythonW = Join-Path $venv 'Scripts\pythonw.exe'
if ($PreflightOnly) {
    [pscustomobject]@{
        Mode = 'VM-bootstrap-plan-only'
        Source = 'https://github.com/marquimRcc/FaceControlKidsPC/tree/developer'
        Workspace = $workspace
        IsolatedData = $dataDir
        LegacyFamilyPathsTouched = $false
        WindowsLoginModified = $false
    } | Format-List
    return
}
New-Item -ItemType Directory -Path $workspace -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

# GitHub archive requires no local Git installation. Keep venv/data outside
# source so updates cannot erase enrollment/photos or Python dependencies.
Write-Host '[1/5] Baixando branch developer do GitHub...' -ForegroundColor Cyan
$temp = Join-Path $workspace ('download-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
    $zip = Join-Path $temp 'developer.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/marquimRcc/FaceControlKidsPC/archive/refs/heads/developer.zip' -OutFile $zip
    if (-not (Test-Path $zip) -or (Get-Item $zip).Length -lt 2048) {
        throw 'Arquivo recebido do GitHub esta incompleto.'
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $temp -Force
    $source = Join-Path $temp 'FaceControlKidsPC-developer'
    if (-not (Test-Path (Join-Path $source 'facekids\admin_dashboard.py')) -or
        -not (Test-Path (Join-Path $source 'scripts\Testar-P5-P6-VM-FaceKids.ps1')) -or
        -not (Test-Path (Join-Path $source 'facekids\vm_lab_paths.py'))) {
        throw 'Pacote developer inesperado. Instalacao de laboratorio interrompida.'
    }
    if (Test-Path -LiteralPath $repo) {
        $backup = Join-Path $workspace ('codigo-anterior-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Move-Item -LiteralPath $repo -Destination $backup
    }
    Move-Item -LiteralPath $source -Destination $repo
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host '[2/5] Preparando Python 3.11 e bibliotecas...' -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Find-Python311
    if (-not $python) {
        # Python 3.11.9 is the final official 3.11 Windows installer.
        # Install only inside the VM workspace and do not require winget.
        # Windows PowerShell 5.1 can expose a null RuntimeInformation.OSArchitecture
        # on older .NET installations. Query the guest processor through WMI
        # instead of invoking ToString() on a potentially null value.
        $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
        if (-not [Environment]::Is64BitOperatingSystem -or
            $null -eq $cpu -or [int]$cpu.Architecture -ne 9) {
            throw 'Bootstrap oficial Python 3.11.9 requer Windows x64 nesta VM.'
        }
        $pythonHome = Join-Path $workspace 'runtime\python311'
        $downloadDir = Join-Path $workspace 'downloads'
        New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
        $installer = Join-Path $downloadDir 'python-3.11.9-amd64.exe'
        $expectedSha256 = '5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde'
        $installerUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
        Write-Host 'winget nao necessario: baixando Python 3.11.9 oficial do python.org...' -ForegroundColor Cyan
        $validCache = $false
        if (Test-Path -LiteralPath $installer -PathType Leaf) {
            $cachedDigest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256 -ErrorAction Stop).Hash
            $validCache = ([string]$cachedDigest -eq $expectedSha256)
        }
        if (-not $validCache) {
            Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
            Invoke-WebRequest -UseBasicParsing -Uri $installerUrl -OutFile $installer
        }
        if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
            throw 'Python oficial recusado: download incompleto.'
        }
        $downloadDigest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256 -ErrorAction Stop).Hash
        if ([string]$downloadDigest -ne $expectedSha256) {
            throw ('Python oficial recusado: SHA-256 divergente. Esperado: ' +
                $expectedSha256 + '; obtido: ' + [string]$downloadDigest)
        }
        Write-Host 'SHA-256 verificado. Instalando Python somente no perfil da VM...' -ForegroundColor Cyan
        $installArgs = @(
            '/quiet',
            'InstallAllUsers=0',
            'PrependPath=0',
            'Include_launcher=0',
            'Include_pip=1',
            'Include_tcltk=1',
            'Include_test=0',
            'Shortcuts=0',
            ('TargetDir="' + $pythonHome + '"')
        )
        $process = Start-Process -FilePath $installer -ArgumentList $installArgs -PassThru -Wait
        if ($process.ExitCode -notin @(0, 3010)) {
            throw ('Falha ao instalar Python na VM, codigo: ' + $process.ExitCode)
        }
        $python = Find-Python311
        if (-not $python) {
            throw 'Python oficial instalado, mas Tk/Python 3.11 nao foi validado. Consulte instalacao na VM.'
        }
    }
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente Python isolado.' }
}
& $venvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $repo 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar OpenCV/NumPy dentro da VM.' }
# Avoid Python -c quoting: Windows PowerShell 5.1 strips nested double quotes.
& $venvPython -m facekids.vm_guest_diagnostics dependencies
if ($LASTEXITCODE -ne 0) { throw 'Bibliotecas nao funcionais na VM.' }

# Both the parent dashboard and pilot database must use ONLY VM data paths.
$env:FACEKIDS_VM_LAB_DIR = $dataDir
$env:FACEKIDS_VM_LAB_ACK = 'ISOLATED_VM_ONLY'
$env:FACEKIDS_VM_SHADOW = '0'
Remove-Item Env:FACEKIDS_VM_SHADOW_ACK -ErrorAction SilentlyContinue

Write-Host '[3/5] Preparando modelos YuNet e SFace (verificacao SHA-256)...' -ForegroundColor Cyan
Push-Location $repo
try {
    & $venvPython -m facekids.cli download-models
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Modelos nao ficaram prontos. O painel abrira, mas o cadastro facial pode exigir repetir o download.'
    }

    Write-Host '[4/5] Preflight, testes e verificacao da webcam da VM...' -ForegroundColor Cyan
    $argsP6 = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                (Join-Path $repo 'scripts\Testar-P5-P6-VM-FaceKids.ps1'),
                '-CameraIndex', "$CameraIndex")
    if (-not $SkipTests) { $argsP6 += '-RunUnitTests' }
    if (-not $NoCameraProbe) { $argsP6 += '-CameraProbe' }
    & powershell.exe @argsP6
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'O preflight/teste P6 registrou falhas. Isto NAO aprova o desbloqueio: reveja a saida acima. O Painel de laboratorio sera aberto para diagnostico.'
    }
} finally {
    Pop-Location
}

Write-Host '[5/5] Abrindo Painel dos Pais (dados isolados da VM)...' -ForegroundColor Green
$pythonGui = if (Test-Path -LiteralPath $venvPythonW) { $venvPythonW } else { $venvPython }
$proc = Start-Process -FilePath $pythonGui -ArgumentList '-m', 'facekids.admin_dashboard' -WorkingDirectory $repo -PassThru
Start-Sleep -Seconds 2
if ($proc.HasExited -and $proc.ExitCode -ne 0) {
    throw 'Painel terminou inesperadamente. Execute manualmente: ' + $venvPython + ' -m facekids.admin_dashboard'
}
Write-Host ''
Write-Host 'PAINEL ABERTO. Use Nova crianca para cadastrar um ou mais perfis (pode testar seu proprio rosto).' -ForegroundColor Green
Write-Host ('Codigo: {0}' -f $repo)
Write-Host ('Banco/fotos isolados: {0}' -f $dataDir)
Write-Host 'Nao foi instalado Credential Provider nem servico SCM nesta etapa.'

# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# Raiz do projeto relativa ao local do .spec (packaging/pyinstaller/)
ROOT = Path(SPECPATH).resolve().parent.parent

a = Analysis(
    [str(ROOT / 'packaging' / 'installer_runner.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'safepckids'), 'safepckids'),
        (str(ROOT / 'safepckids' / 'ui_assets'), 'safepckids/ui_assets'),
        (str(ROOT / 'assets'), 'assets'),
        (str(ROOT / 'models'), 'models'),
        (str(ROOT / 'native' / 'credential_provider_safepckids' / 'SafePCKidsCredentialProvider.dll'), 'native/credential_provider_safepckids')
    ],
    hiddenimports=[
        'safepckids.app_window',
        'safepckids.app_server',
        'safepckids.camera_service',
        'safepckids.installer_engine',
        'safepckids.session_secret',
        'safepckids.credential_store',
        'safepckids.avatar_utils',
        'safepckids.admin_auth',
        'safepckids.storage',
        'safepckids.auth_service',
        'safepckids.filhos_agent'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SafePCKids-Instalador',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=str(ROOT / 'assets' / 'safepckids.ico'),
)

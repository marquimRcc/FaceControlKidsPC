# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# Raiz do projeto relativa ao local do .spec (packaging/pyinstaller/)
ROOT = Path(SPECPATH).resolve().parent.parent

a = Analysis(
    [str(ROOT / 'packaging' / 'installer_runner.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'facekids'), 'facekids'),
        (str(ROOT / 'facekids' / 'ui_assets'), 'facekids/ui_assets'),
        (str(ROOT / 'assets'), 'assets'),
        (str(ROOT / 'models'), 'models'),
        (str(ROOT / 'native' / 'credential_provider_facekids' / 'FaceKidsCredentialProvider.dll'), 'native/credential_provider_facekids')
    ],
    hiddenimports=[
        'facekids.app_window',
        'facekids.app_server',
        'facekids.camera_service',
        'facekids.installer_engine',
        'facekids.session_secret',
        'facekids.credential_store',
        'facekids.avatar_utils',
        'facekids.admin_auth',
        'facekids.storage',
        'facekids.auth_service',
        'facekids.filhos_agent'
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
    name='FaceKids-Instalador',
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
    icon=str(ROOT / 'assets' / 'facekids.ico'),
)

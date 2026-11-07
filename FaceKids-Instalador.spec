# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/installer_runner.py'],
    pathex=['C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC'],
    binaries=[],
    datas=[
        ('C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/facekids', 'facekids'),
        ('C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/facekids/ui_assets', 'facekids/ui_assets'),
        ('C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/assets', 'assets'),
        ('C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/models', 'models'),
        ('C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/native/credential_provider_facekids/FaceKidsCredentialProvider.dll', 'native/credential_provider_facekids')
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
        'facekids.storage'
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
    uac_admin=True,
    icon='C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/assets/facekids.ico',
)

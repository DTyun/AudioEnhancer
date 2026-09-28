# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# On Windows, PyInstaller may collect Poppler's ICU DLLs from PATH. Qt 6 uses
# the Windows ICU API, while Poppler's ICU exports versioned symbols. Bundling
# that DLL beside the executable makes QtCore fail with WinError 127.
a.binaries = TOC(
    entry for entry in a.binaries
    if entry[0].lower().replace('\\', '/') not in ('icuuc.dll', 'icudt78.dll')
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AudioEnhancer',
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
    icon=['app.ico'],
)

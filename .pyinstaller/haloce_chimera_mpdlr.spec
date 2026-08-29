# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../ChimeraMapDownloader.pyw'],
    pathex=[],
    binaries=[],
    datas=[('C:/ChimeraMapDownloader/chimera_map_downloader_v3.5_windows_build_package final/halonet_map_index.json', '.')],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox'],
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
    name='haloce_chimera_mpdlr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/ChimeraMapDownloader/chimera_map_downloader_v3.5_windows_build_package final/haloce.ico'],
)

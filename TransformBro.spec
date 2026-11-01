# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    ['TransformBro.py'],
    pathex=[],
    binaries=[],
    datas=[(str(ROOT / 'assets' / 'TransformBro.ico'), 'assets')],
    hiddenimports=['fitz', 'pymupdf', 'win32com.client', 'pythoncom', 'pywintypes', 'olefile'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TransformBro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'TransformBro.ico'),
    version=str(ROOT / 'packaging' / 'version_info.txt'),
)

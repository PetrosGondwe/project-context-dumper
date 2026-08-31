# Build a standalone executable with:
#   pip install pyinstaller
#   pyinstaller pyinstaller.spec
#
# Output lands in dist/ProjectContextDumper(.exe on Windows / .app on macOS).

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["pdfplumber"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ProjectContextDumper",
    debug=False,
    strip=False,
    upx=True,
    console=False,   # GUI app, no terminal window
)

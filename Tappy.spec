# -*- mode: python ; coding: utf-8 -*-
# Cross-platform PyInstaller spec for Tappy.
#   macOS:    pyinstaller Tappy.spec   ->  dist/Tappy.app
#   Windows:  pyinstaller Tappy.spec   ->  dist/Tappy/Tappy.exe
import sys

if sys.platform == "darwin":
    # pyqt-liquidglass imports these pyobjc frameworks lazily.
    hidden = ["AppKit", "Foundation", "Quartz", "objc"]
    icon = "assets/icons/tappy.icns"
elif sys.platform == "win32":
    hidden = ["win32mica"]
    icon = "assets/icons/tappy.ico"
else:
    hidden = []
    icon = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=hidden,
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
    [],
    exclude_binaries=True,
    name='Tappy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tappy',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Tappy.app',
        icon=icon,
        bundle_identifier='com.tappy.app',
        info_plist={
            'NSHighResolutionCapable': True,
            # Set to True to run as a menu-bar agent with no Dock icon.
            'LSUIElement': False,
        },
    )

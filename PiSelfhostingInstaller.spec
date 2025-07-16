# PiSelfhostingInstaller.spec
# -*- mode: python ; coding: utf-8 -*-

# This spec file is updated to support the src/ layout by pointing to the correct
# entry-point script and bundling the data files from their correct locations.

a = Analysis(
    # 1. USE THE CORRECT SCRIPT AS THE ENTRY POINT
    # This should be the modern webapp script inside the 'src' package.
    ['src/config_webapp.py'],

    # 2. ENSURE THE PROJECT ROOT IS IN THE SEARCH PATH
    # This allows PyInstaller to find the 'src' package.
    pathex=['.'],

    binaries=[],

    # 3. REFER TO THE CORRECT LOCATION OF TEMPLATES, STATIC FILES, AND OTHER DATA
    # These paths are relative to the project root, where you run PyInstaller from.
    datas=[
        ('configurator_app/templates', 'configurator_app/templates'),
        ('configurator_app/static', 'configurator_app/static'),
        ('config', 'config'),
        ('components_metadata.json', '.')
    ],
    hiddenimports=[],
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
    name='PiSelfhostingInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

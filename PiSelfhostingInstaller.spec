# PiSelfhostingInstaller.spec

# This file is a "blueprint" for PyInstaller, configured for a one-file,
# windowed application, consistent across all operating systems.

a = Analysis(
    ['src/configurator_app/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Add all non-code files needed by your application here.
        # Format: ('source_path_on_disk', 'destination_path_in_bundle')
        ('src/configurator_app/templates', 'configurator_app/templates'),
        ('src/configurator_app/static', 'configurator_app/static')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='PiSelfhostingInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Set console to False for a windowed (GUI) application.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # The icon path will be set via the command line during the build.
    # PyInstaller will automatically update this spec file if an icon is provided.
)

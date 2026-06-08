# PiSelfhostingInstaller.spec
import platform

# This file is a "blueprint" for PyInstaller, configured for a one-file,
# windowed application, consistent across all operating systems.

# --- Define the icon based on the OS ---
icon_file = None
if platform.system() == "Windows":
    icon_file = "images/favicon.ico"
elif platform.system() == "Darwin":  # Darwin is the system name for macOS
    # Activate the icon for macOS using the file you provided.
    icon_file = "images/piselfhosting-apple.icns"
# For other systems (like Linux), icon_file remains None.

a = Analysis(
    # Point to the correct main application script.
    ['src/configurator_app/app.py'],
    # Add 'src' to the path to help PyInstaller resolve local module imports.
    pathex=['src'],
    binaries=[],
    datas=[
        # Flask app templates and static files
        ('src/configurator_app/templates', 'templates'),
        ('src/configurator_app/static', 'static'),
        # Config files
        ('config', 'config'),
        # Component templates - essential for generating configurations
        ('component_templates', 'component_templates'),
    ],
    hiddenimports=[
        'nacl',
        'bcrypt',
        'cryptography'
    ],
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
    # --- CHANGE 1: Enable debug output from PyInstaller's bootloader ---
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # --- CHANGE 2: Enable the console to see tracebacks ---
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # This now uses the correct icon file for each OS.
    icon=icon_file
)

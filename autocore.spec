# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — builds a single AutoCore.exe from gui.py.

Build command (run from the repo root):
    pip install pyinstaller customtkinter requests
    pyinstaller autocore.spec

Output: dist/AutoCore.exe
"""

import os
import customtkinter

block_cipher = None

# customtkinter ships its own asset folder that must be bundled as-is
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ["gui.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # OpenCore config template
        ("sample.plist", "."),
        # customtkinter themes + images
        (ctk_path, "customtkinter"),
    ],
    hiddenimports=[
        # AutoCore modules
        "hardware", "kexts", "efi_builder", "config_plist",
        "usbflash", "usb_mapper", "build_coresync",
        "lang", "constants", "utils", "progress",
        # stdlib used at runtime
        "plistlib", "zipfile", "shutil", "tempfile",
        "threading", "queue", "subprocess",
        "platform", "json", "re", "time", "glob",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
    name="AutoCore",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # no terminal window — pure GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # set to "icon.ico" if you add an icon file
)

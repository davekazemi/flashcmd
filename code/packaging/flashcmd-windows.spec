# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parents[1]
CODE_DIR = ROOT / "code"
sys.path.insert(0, str(CODE_DIR))
from flashcmd_version import APP_NAME, __version__

VERSION_PARTS = tuple(int(part) for part in __version__.split(".")) + (0,)
VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=VERSION_PARTS, prodvers=VERSION_PARTS, mask=0x3F,
        flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", APP_NAME),
            StringStruct("FileDescription", "FlashCMD shortcut manager"),
            StringStruct("FileVersion", __version__),
            StringStruct("InternalName", APP_NAME),
            StringStruct("OriginalFilename", "FlashCMD.exe"),
            StringStruct("ProductName", APP_NAME),
            StringStruct("ProductVersion", __version__),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(CODE_DIR / "shortcut_manager.py")],
    pathex=[str(CODE_DIR)],
    binaries=[],
    datas=[
        (str(CODE_DIR / "docs" / "branding" / "FlashCmd.ico"), "code/docs/branding"),
        (str(CODE_DIR / "docs" / "branding" / "icon-badge.png"), "code/docs/branding"),
        (str(CODE_DIR / "docs" / "branding" / "bmc-button.png"), "code/docs/branding"),
    ],
    hiddenimports=[
        "flashcmd_launcher", "flashcmd_version", "quickcmd_core",
        "pynput", "pynput.keyboard", "pynput.keyboard._win32", "pynput._util.win32",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(CODE_DIR / "docs" / "branding" / "FlashCmd.ico"),
    version=VERSION_INFO,
)

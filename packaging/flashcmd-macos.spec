# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from flashcmd_version import APP_NAME, BUNDLE_IDENTIFIER, __version__

a = Analysis(
    [str(ROOT / "shortcut_manager.py")],
    pathex=[str(ROOT)], binaries=[],
    datas=[
        (str(ROOT / "docs" / "branding" / "icon-badge.png"), "docs/branding"),
        (str(ROOT / "docs" / "branding" / "bmc-button.png"), "docs/branding"),
    ],
    hiddenimports=[
        "flashcmd_launcher", "flashcmd_version", "quickcmd_core",
        "pynput", "pynput.keyboard", "pynput.keyboard._darwin", "pynput._util.darwin",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name=APP_NAME)
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ROOT / "docs" / "branding" / "FlashCmd.icns"),
    bundle_identifier=BUNDLE_IDENTIFIER,
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSAppleEventsUsageDescription": "FlashCMD opens saved commands in Terminal.",
        "NSHighResolutionCapable": True,
    },
)

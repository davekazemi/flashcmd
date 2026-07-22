from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"


class BuildAssetTests(unittest.TestCase):
    def test_clean_checkout_build_inputs_live_under_code(self):
        expected = (
            "scripts/build_windows.ps1", "scripts/test.ps1",
            "scripts/build_macos.sh", "scripts/test.sh",
            "scripts/generate_macos_icon.sh",
            "packaging/flashcmd-windows.spec", "packaging/flashcmd-macos.spec",
            "installer/windows/FlashCmd.wxs",
            "installer/windows/FlashCMD-License.rtf", "requirements-build.txt",
            "docs/branding/FlashCmd.ico", "docs/branding/FlashCmd.icns",
            "docs/branding/icon-badge.png", "docs/branding/bmc-button.png",
        )
        for relative in expected:
            with self.subTest(path=relative):
                self.assertTrue((CODE / relative).is_file())

    def test_specs_and_scripts_resolve_relocated_paths(self):
        windows_spec = (CODE / "packaging/flashcmd-windows.spec").read_text(encoding="utf-8")
        macos_spec = (CODE / "packaging/flashcmd-macos.spec").read_text(encoding="utf-8")
        windows_build = (CODE / "scripts/build_windows.ps1").read_text(encoding="utf-8")
        macos_build = (CODE / "scripts/build_macos.sh").read_text(encoding="utf-8")
        for spec in (windows_spec, macos_spec):
            self.assertIn("SPEC_DIR.parents[1]", spec)
            self.assertIn('"code/docs/branding"', spec)
        self.assertIn('code\\packaging\\flashcmd-windows.spec', windows_build)
        self.assertIn('code\\installer\\windows\\FlashCmd.wxs', windows_build)
        self.assertIn("code/packaging/flashcmd-macos.spec", macos_build)

    def test_installer_has_persisted_optional_startup_component(self):
        wix = (CODE / "installer/windows/FlashCmd.wxs").read_text(encoding="utf-8")
        for text in (
            'Id="ADD_TO_STARTUP"', 'Id="RememberStartupOption"',
            'Text="Add FlashCMD to startup"', 'Id="StartupFolder"',
            'Id="StartupShortcut"', 'Condition="ADD_TO_STARTUP = 1"',
            'Transitive="yes"', 'Name="AddToStartup"',
            'Action="removeOnUninstall"', 'Id="WIXUI_EXITDIALOGOPTIONALCHECKBOX"',
        ):
            with self.subTest(text=text):
                self.assertIn(text, wix)

    def test_runtime_branding_path_matches_spec_destination(self):
        manager = (CODE / "shortcut_manager.py").read_text(encoding="utf-8")
        self.assertIn('RESOURCE_DIR, "code", "docs", "branding"', manager)

    def test_packaged_version_smoke_test_is_early_and_bounded(self):
        manager = (CODE / "shortcut_manager.py").read_text(encoding="utf-8")
        windows_build = (CODE / "scripts/build_windows.ps1").read_text(encoding="utf-8")
        self.assertLess(
            manager.index('sys.argv[1:] == ["--version"]'),
            manager.index("import tkinter as tk"),
        )
        self.assertIn("WaitForExit(60000)", windows_build)
        self.assertIn("taskkill /PID $SmokeProcess.Id /T /F", windows_build)
        self.assertIn('Remove-Item "Env:$Name"', windows_build)
        self.assertIn('foreach ($Name in @("TCL_LIBRARY", "TK_LIBRARY"))', windows_build)


if __name__ == "__main__":
    unittest.main()
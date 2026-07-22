import os
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import flashcmd_launcher as launcher


class MacOSLauncherTests(unittest.TestCase):
    @mock.patch("flashcmd_launcher.subprocess.Popen")
    def test_program_action_launches_directly_with_parsed_arguments(self, popen):
        launcher.launch_program(
            "/Applications/My Tool.app/Contents/MacOS/tool",
            '--name "Daily Files"', "/tmp/work", platform="darwin",
        )
        popen.assert_called_once_with(
            ["/Applications/My Tool.app/Contents/MacOS/tool", "--name", "Daily Files"],
            shell=False, cwd="/tmp/work",
        )

    def test_command_quotes_shell_directory_and_multiline_text(self):
        command = "printf '%s\\n' \"hello world\"\nprintf done"
        result = launcher.build_macos_terminal_command(
            "/Applications/My Shell/bin/zsh", command, "/Users/demo/Work Files",
        )
        self.assertIn("cd -- '/Users/demo/Work Files'", result)
        self.assertIn("'/Applications/My Shell/bin/zsh' -lc", result)
        self.assertIn("exec '/Applications/My Shell/bin/zsh' -il", result)
        self.assertIn("'\"'\"'", result)
        self.assertIn("\n", result)

    def test_applescript_is_static_and_command_is_one_argument(self):
        command = 'echo "quoted"\necho second'
        argv = launcher.build_macos_terminal_argv("/bin/zsh", command, "/tmp/a b")
        self.assertEqual(argv[:2], ["/usr/bin/osascript", "-e"])
        self.assertEqual(len(argv), 4)
        self.assertNotIn(command, argv[2])
        self.assertIn(command, argv[3])

    @mock.patch("flashcmd_launcher.subprocess.Popen")
    def test_macos_popen_uses_argv_without_shell_or_cwd(self, popen):
        launcher.launch_shortcut("/bin/zsh", "echo ok", "/tmp", platform="darwin")
        args, kwargs = popen.call_args
        self.assertEqual(args[0][0], "/usr/bin/osascript")
        self.assertEqual(kwargs, {"shell": False})


class WindowsLauncherTests(unittest.TestCase):
    @mock.patch("flashcmd_launcher.subprocess.Popen")
    def test_program_action_launches_directly_without_console(self, popen):
        launcher.launch_program(
            r"C:\Program Files\FME\fme.exe", '--run "job.fmw"',
            r"C:\Work", platform="win32",
        )
        popen.assert_called_once_with(
            r'"C:\Program Files\FME\fme.exe" --run "job.fmw"',
            shell=False, cwd=r"C:\Work",
            creationflags=getattr(launcher.subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_cleanup_waits_then_removes_batch(self):
        with tempfile.NamedTemporaryFile(delete=False) as batch:
            batch_path = batch.name
        process = mock.Mock()
        launcher._cleanup_after_process(process, batch_path)
        process.wait.assert_called_once_with()
        self.assertFalse(os.path.exists(batch_path))

    def test_windows_launch_preserves_batch_argv_flags_and_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            real_named_temp = tempfile.NamedTemporaryFile

            def local_named_temp(**kwargs):
                kwargs["dir"] = directory
                return real_named_temp(**kwargs)

            process = mock.Mock()
            with mock.patch("flashcmd_launcher.tempfile.NamedTemporaryFile", side_effect=local_named_temp), \
                    mock.patch("flashcmd_launcher.shutil.which", return_value=None), \
                    mock.patch("flashcmd_launcher.subprocess.Popen", return_value=process) as popen, \
                    mock.patch("flashcmd_launcher.threading.Thread") as thread:
                launcher.launch_shortcut("cmd.exe", "echo one\necho two", directory, platform="win32")
                argv = popen.call_args.args[0]
                self.assertEqual(argv[:2], ["cmd.exe", "/k"])
                with open(argv[2], "r", encoding="utf-8") as saved:
                    self.assertEqual(saved.read(), "@echo off\necho one\necho two\n")
                self.assertEqual(popen.call_args.kwargs["cwd"], directory)
                self.assertFalse(popen.call_args.kwargs["shell"])
                self.assertEqual(
                    popen.call_args.kwargs["creationflags"],
                    getattr(launcher.subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                thread.assert_called_once_with(
                    target=launcher._cleanup_after_process,
                    args=(process, argv[2]), daemon=True,
                )
                thread.return_value.start.assert_called_once_with()
                os.remove(argv[2])

    def test_windows_terminal_uses_shortcut_title_color_and_configured_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            process = mock.Mock()
            with mock.patch("flashcmd_launcher.shutil.which", return_value=r"C:\WindowsApps\wt.exe"), \
                    mock.patch("flashcmd_launcher.subprocess.Popen", return_value=process) as popen, \
                    mock.patch("flashcmd_launcher.threading.Thread") as thread:
                launcher.launch_shortcut(
                    "cmd.exe", "echo ok", directory, platform="win32",
                    title="Daily Build", color="#2563EB",
                )
            argv = popen.call_args.args[0]
            self.assertEqual(argv[:2], [r"C:\WindowsApps\wt.exe", "new-tab"])
            self.assertIn("--startingDirectory", argv)
            self.assertEqual(argv[argv.index("--title") + 1], "Daily Build")
            self.assertIn("--suppressApplicationTitle", argv)
            self.assertEqual(argv[argv.index("--tabColor") + 1], "#2563EB")
            self.assertEqual(argv[-3:-1], ["cmd.exe", "/k"])
            thread.assert_called_once_with(
                target=launcher._cleanup_after_process,
                args=(process, argv[-1], launcher.WINDOWS_TERMINAL_BATCH_CLEANUP_DELAY),
                daemon=True,
            )
            os.remove(argv[-1])

    def test_failed_windows_terminal_launch_falls_back_to_configured_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            process = mock.Mock()
            with mock.patch("flashcmd_launcher.shutil.which", return_value="wt.exe"), \
                    mock.patch(
                        "flashcmd_launcher.subprocess.Popen",
                        side_effect=[OSError("terminal unavailable"), process],
                    ) as popen, mock.patch("flashcmd_launcher.threading.Thread"):
                launcher.launch_shortcut("cmd.exe", "echo ok", directory, platform="win32")
            self.assertEqual(popen.call_count, 2)
            self.assertEqual(popen.call_args.args[0][:2], ["cmd.exe", "/k"])
            os.remove(popen.call_args.args[0][2])

    def test_failed_windows_launch_removes_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            real_named_temp = tempfile.NamedTemporaryFile

            def local_named_temp(**kwargs):
                kwargs["dir"] = directory
                return real_named_temp(**kwargs)

            with mock.patch("flashcmd_launcher.tempfile.NamedTemporaryFile", side_effect=local_named_temp), \
                    mock.patch("flashcmd_launcher.shutil.which", return_value=None), \
                    mock.patch("flashcmd_launcher.subprocess.Popen", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    launcher.launch_shortcut("cmd.exe", "echo no", "", platform="win32")
            self.assertEqual(os.listdir(directory), [])

    def test_unsupported_platform_is_explicit(self):
        with self.assertRaises(NotImplementedError):
            launcher.launch_shortcut("/bin/sh", "echo ok", platform="plan9")


class MultiActionLauncherTests(unittest.TestCase):
    def test_result_marker_requires_expected_nonce_and_signed_integer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "result")
            for text, expected in (("nonce 0", 0), ("nonce -17", -17), ("nonce +3", 3)):
                with self.subTest(text=text):
                    with open(path, "w", encoding="utf-8") as marker:
                        marker.write(text)
                    self.assertEqual(launcher.parse_result_marker(path, "nonce"), expected)
            for text in ("wrong 0", "nonce", "nonce nope", "nonce 1 extra"):
                with self.subTest(text=text):
                    with open(path, "w", encoding="utf-8") as marker:
                        marker.write(text)
                    self.assertIsNone(launcher.parse_result_marker(path, "nonce"))

    def test_windows_wrapper_isolates_child_and_atomically_moves_marker(self):
        action = {"name": "Exit", "command": "exit /b 7", "start_in": ""}
        with tempfile.TemporaryDirectory() as directory:
            prepared = launcher._prepare_command(directory, 0, action, "windows", "cmd.exe")
            with open(prepared.wrapper_path, "r", encoding="utf-8") as wrapper:
                text = wrapper.read()
        self.assertIn("cmd.exe /d /c", text)
        self.assertIn("%errorlevel%", text)
        self.assertIn("move /y", text)
        self.assertIn("cmd.exe /k", text)
        self.assertLess(text.index(".started"), text.index("cmd.exe /d /c"))

    def test_compound_windows_terminal_argv_groups_named_colored_tabs(self):
        wrappers = [
            SimpleNamespace(action={"name": "API", "start_in": r"C:\API", "color": "#2563eb"}, wrapper_path=r"C:\run\a.bat"),
            SimpleNamespace(action={"name": "Web", "start_in": "", "color": "#dc2626"}, wrapper_path=r"C:\run\b.bat"),
        ]
        argv = launcher.build_compound_windows_terminal_argv(
            "wt.exe", "flashcmd-abc", wrappers,
        )
        self.assertEqual(argv[:3], ["wt.exe", "--window", "flashcmd-abc"])
        self.assertEqual(argv.count("new-tab"), 2)
        self.assertEqual(argv.count(";"), 1)
        self.assertEqual(argv.count("--suppressApplicationTitle"), 2)
        self.assertEqual(argv.count("#2563EB"), 1)
        self.assertEqual(argv.count("#DC2626"), 1)

    def test_sequential_reuses_unique_window_and_continues_after_failure(self):
        actions = [
            {"name": "One", "command": "exit /b 2", "start_in": "", "color": "#2563EB"},
            {"name": "Two", "command": "echo ok", "start_in": ""},
        ]
        monitor_results = [
            launcher.ActionResult(0, "One", launcher.STATUS_FAILED, 2, "Exited with code 2."),
            launcher.ActionResult(1, "Two", launcher.STATUS_SUCCESS, 0),
        ]
        process = mock.Mock()
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.shutil.which", return_value="wt.exe"), \
                mock.patch("flashcmd_launcher.subprocess.Popen", return_value=process) as popen, \
                mock.patch("flashcmd_launcher._monitor_command", side_effect=monitor_results):
            result = launcher.launch_shortcut(
                "cmd.exe", actions, "sequential", platform="win32", run_id="run-1",
            )
        self.assertEqual([item.status for item in result.actions], ["failed", "success"])
        self.assertEqual(popen.call_count, 2)
        first, second = [call.args[0] for call in popen.call_args_list]
        self.assertEqual(first[first.index("--window") + 1], "flashcmd-run1")
        self.assertEqual(second[second.index("--window") + 1], "flashcmd-run1")
        self.assertEqual(first[first.index("--title") + 1], "One")
        self.assertEqual(second[second.index("--title") + 1], "Two")
        self.assertEqual(first[first.index("--tabColor") + 1], "#2563EB")
        self.assertNotIn("--tabColor", second)

    def test_parallel_uses_one_wt_invocation_and_keeps_program_direct(self):
        actions = [
            {"name": "API", "command": "echo api", "start_in": "", "color": "#2563EB"},
            {"name": "Tool", "action_mode": "program", "program_path": "tool.exe", "arguments": "", "start_in": "", "color": "#16A34A"},
            {"name": "Web", "command": "echo web", "start_in": "", "color": "invalid"},
        ]
        host = mock.Mock()
        program = mock.Mock(returncode=0)
        program.poll.return_value = 0
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.shutil.which", return_value="wt.exe"), \
                mock.patch("flashcmd_launcher.subprocess.Popen", return_value=host) as popen, \
                mock.patch("flashcmd_launcher.launch_program", return_value=program) as launch_program, \
                mock.patch("flashcmd_launcher._monitor_command", side_effect=[
                    launcher.ActionResult(0, "API", "success", 0),
                    launcher.ActionResult(2, "Web", "success", 0),
                ]):
            result = launcher.launch_shortcut("cmd.exe", actions, "parallel", platform="win32")
        self.assertTrue(result.success)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args.args[0].count("new-tab"), 2)
        self.assertEqual(popen.call_args.args[0].count("--tabColor"), 1)
        self.assertIn("#2563EB", popen.call_args.args[0])
        self.assertNotIn("#16A34A", popen.call_args.args[0])
        launch_program.assert_called_once_with("tool.exe", "", "", platform="windows")

    def test_parallel_programs_are_all_launched_before_waiting(self):
        events = []

        def launch(path, _arguments, _start_in, platform=None):
            events.append(f"launch:{path}")
            process = mock.Mock(returncode=0)
            process.poll.side_effect = lambda: events.append(f"poll:{path}") or 0
            return process

        actions = [
            {"name": "One", "action_mode": "program", "program_path": "one.exe", "start_in": ""},
            {"name": "Two", "action_mode": "program", "program_path": "two.exe", "start_in": ""},
        ]
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.launch_program", side_effect=launch):
            launcher.launch_shortcut("cmd.exe", actions, "parallel", platform="win32")
        self.assertEqual(events[:2], ["launch:one.exe", "launch:two.exe"])

    def test_missing_start_directory_is_one_action_failure(self):
        actions = [
            {"name": "Missing", "action_mode": "program", "program_path": "bad.exe", "start_in": r"Z:\missing"},
            {"name": "Good", "action_mode": "program", "program_path": "good.exe", "start_in": ""},
        ]
        process = mock.Mock(returncode=0)
        process.poll.return_value = 0
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.os.path.isdir", side_effect=lambda path: not path), \
                mock.patch("flashcmd_launcher.launch_program", return_value=process) as launch_program:
            result = launcher.launch_shortcut("cmd.exe", actions, "sequential", platform="win32")
        self.assertEqual([item.status for item in result.actions], ["launch_error", "success"])
        launch_program.assert_called_once()

    def test_initial_wt_failure_uses_console_fallback_without_retrying_action(self):
        action = [{"name": "One", "command": "echo one", "start_in": ""}]
        process = mock.Mock()
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.shutil.which", return_value="wt.exe"), \
                mock.patch("flashcmd_launcher.subprocess.Popen", side_effect=[OSError("no wt"), process]) as popen, \
                mock.patch("flashcmd_launcher._monitor_command", return_value=launcher.ActionResult(0, "One", "success", 0)):
            result = launcher.launch_shortcut("cmd.exe", action, platform="win32")
        self.assertTrue(result.fallback_used)
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(popen.call_args.args[0][:4], ["cmd.exe", "/d", "/c", mock.ANY])

    def test_cancelled_run_does_not_launch_remaining_actions(self):
        cancelled = threading.Event()
        cancelled.set()
        actions = [{"name": "Tool", "action_mode": "program", "program_path": "tool.exe", "start_in": ""}]
        with mock.patch("flashcmd_launcher.cleanup_stale_run_directories"), \
                mock.patch("flashcmd_launcher.launch_program") as launch_program:
            result = launcher.launch_shortcut(
                "cmd.exe", actions, platform="win32", cancel_event=cancelled,
            )
        self.assertEqual(result.actions[0].status, launcher.STATUS_CANCELLED)
        launch_program.assert_not_called()

    def test_stale_cleanup_never_touches_unprefixed_or_recent_directories(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, launcher.RUN_DIRECTORY_PREFIX + "old")
            recent = os.path.join(root, launcher.RUN_DIRECTORY_PREFIX + "recent")
            unrelated = os.path.join(root, "other-old")
            for path in (old, recent, unrelated):
                os.mkdir(path)
            os.utime(old, (1, 1))
            os.utime(unrelated, (1, 1))
            removed = launcher.cleanup_stale_run_directories(
                root, now=1000, max_age=100,
            )
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(recent))
            self.assertTrue(os.path.exists(unrelated))


if __name__ == "__main__":
    unittest.main()
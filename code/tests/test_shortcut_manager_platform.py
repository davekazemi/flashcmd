import contextlib
import io
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import shortcut_manager
from flashcmd_launcher import ActionResult, ProgressEvent, RunResult, STATUS_FAILED, STATUS_SUCCESS
from quickcmd_core import (
    ACTION_MODE_COMMAND_LINE, ACTION_MODE_PROGRAM,
    build_task_scheduler_shortcut_xml, parse_task_scheduler_shortcut_xml,
)


class PlatformSafetyTests(unittest.TestCase):
    def test_shortcut_color_picker_stores_selected_custom_color(self):
        dialog = SimpleNamespace(
            color_var=mock.Mock(), _update_color_preview=mock.Mock(),
        )
        dialog.color_var.get.return_value = "#2563EB"
        with mock.patch(
            "shortcut_manager.colorchooser.askcolor",
            return_value=((161, 178, 195), "#a1b2c3"),
        ) as askcolor:
            shortcut_manager.ShortcutDialog._choose_shortcut_color(dialog)
        askcolor.assert_called_once_with(
            color="#2563EB", parent=dialog, title="Choose shortcut color",
        )
        dialog.color_var.set.assert_called_once_with("#A1B2C3")
        dialog._update_color_preview.assert_called_once_with()

    def test_shortcut_color_picker_cancel_preserves_current_color(self):
        dialog = SimpleNamespace(
            color_var=mock.Mock(), _update_color_preview=mock.Mock(),
        )
        dialog.color_var.get.return_value = ""
        with mock.patch("shortcut_manager.colorchooser.askcolor", return_value=(None, None)):
            shortcut_manager.ShortcutDialog._choose_shortcut_color(dialog)
        dialog.color_var.set.assert_not_called()
        dialog._update_color_preview.assert_not_called()

    def test_clearing_shortcut_color_updates_preview(self):
        dialog = SimpleNamespace(color_var=mock.Mock(), _update_color_preview=mock.Mock())
        shortcut_manager.ShortcutDialog._clear_shortcut_color(dialog)
        dialog.color_var.set.assert_called_once_with("")
        dialog._update_color_preview.assert_called_once_with()

    def test_replacing_action_text_forces_immediate_repaint(self):
        text = mock.Mock()
        dialog = SimpleNamespace(cmd=text)

        shortcut_manager.ShortcutDialog._replace_command_text(dialog, "--run imported.fmw")

        text.delete.assert_called_once_with("1.0", shortcut_manager.tk.END)
        text.insert.assert_called_once_with("1.0", "--run imported.fmw")
        text.mark_set.assert_called_once_with("insert", "1.0")
        text.see.assert_called_once_with("1.0")
        text.update_idletasks.assert_called_once_with()

    def test_folder_toggle_tracks_case_insensitive_collapsed_state(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.collapsed_folders = set()
        manager.refresh_cards = mock.Mock()

        manager._toggle_folder("Work")
        self.assertEqual(manager.collapsed_folders, {"work"})
        manager._toggle_folder("WORK")
        self.assertEqual(manager.collapsed_folders, set())
        self.assertEqual(manager.refresh_cards.call_count, 2)

    def test_simulated_macos_import_skips_windows_only_modules(self):
        code = (
            "import sys; sys.platform='darwin'; import shortcut_manager; "
            "assert shortcut_manager.pystray is None; "
            "assert shortcut_manager.ctypes is None; "
            "assert shortcut_manager.CONFIG_CANDIDATES[0] == shortcut_manager.CONFIG_FILE; "
            "assert any('FlashCmd' in value for value in shortcut_manager.CONFIG_CANDIDATES[1:])"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_platform_helpers(self):
        self.assertTrue(shortcut_manager.is_windows("win32"))
        self.assertFalse(shortcut_manager.is_windows("darwin"))
        self.assertTrue(shortcut_manager.is_macos("darwin"))

    def test_version_fast_path_does_not_create_tk(self):
        output = io.StringIO()
        with mock.patch("shortcut_manager.tk.Tk") as tk_root, contextlib.redirect_stdout(output):
            result = shortcut_manager.main(["--version"])
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "FlashCMD 0.1.0")
        tk_root.assert_not_called()

    def test_parse_restore_hotkey_canonicalizes_aliases(self):
        display, expression = shortcut_manager.parse_restore_hotkey("control + option + f")
        self.assertEqual(display, "Ctrl+Alt+F")
        self.assertEqual(expression, "<ctrl>+<alt>+f")

    def test_parse_restore_hotkey_requires_modifier(self):
        with self.assertRaises(ValueError):
            shortcut_manager.parse_restore_hotkey("F12")

    def test_capture_restore_hotkey_uses_held_modifiers(self):
        self.assertEqual(shortcut_manager.hotkey_modifier_from_keysym("Control_L"), "Ctrl")
        self.assertEqual(
            shortcut_manager.capture_restore_hotkey("f", {"Alt", "Ctrl"}),
            "Ctrl+Alt+F",
        )

    def test_settings_dialog_hotkey_keypress_captures_combo(self):
        dialog = SimpleNamespace(
            _capture_modifiers={"Ctrl", "Alt"},
            hotkey_var=mock.Mock(),
            hotkey_error=mock.Mock(),
        )
        result = shortcut_manager.SettingsDialog._capture_hotkey_keypress(
            dialog, SimpleNamespace(keysym="f"),
        )
        self.assertEqual(result, "break")
        dialog.hotkey_var.set.assert_called_once_with("Ctrl+Alt+F")

    def test_settings_dialog_clear_hotkey_resets_state(self):
        dialog = SimpleNamespace(
            _capture_modifiers={"Ctrl"},
            hotkey_var=mock.Mock(),
            hotkey_error=mock.Mock(),
            hotkey=mock.Mock(),
        )
        shortcut_manager.SettingsDialog._clear_hotkey_capture(dialog)
        self.assertEqual(dialog._capture_modifiers, set())
        dialog.hotkey_var.set.assert_called_once_with("")
        dialog.hotkey.focus_set.assert_called_once_with()

    def test_single_instance_endpoint_receives_restore_message(self):
        endpoint = shortcut_manager.SingleInstanceEndpoint(0)
        event = threading.Event()
        endpoint.set_restore_callback(event.set)
        try:
            shortcut_manager.notify_existing_instance(endpoint.port)
            self.assertTrue(event.wait(1.0))
        finally:
            endpoint.close()

    def test_main_signals_running_instance_before_creating_tk(self):
        with mock.patch("shortcut_manager.instance_port", return_value=45000), \
                mock.patch("shortcut_manager.SingleInstanceEndpoint", side_effect=OSError("busy")), \
                mock.patch("shortcut_manager.notify_existing_instance", return_value=True) as notify, \
                mock.patch("shortcut_manager.tk.Tk") as tk_root:
            result = shortcut_manager.main([])
        self.assertEqual(result, 0)
        notify.assert_called_once_with(45000)
        tk_root.assert_not_called()

    def test_support_button_opens_buy_me_a_coffee_link(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.root = mock.Mock()
        with mock.patch("shortcut_manager.webbrowser.open_new_tab") as open_tab:
            shortcut_manager.ShortcutManager.open_buy_me_a_coffee(manager)
        open_tab.assert_called_once_with(shortcut_manager.BUY_ME_A_COFFEE_URL)

    def test_named_executable_uses_path_lookup(self):
        with mock.patch("shortcut_manager.shutil.which", return_value="/bin/zsh"):
            self.assertTrue(shortcut_manager.executable_path_is_valid("zsh", "darwin"))

    def test_macos_absolute_executable_requires_execute_permission(self):
        with mock.patch("shortcut_manager.os.path.isfile", return_value=True), \
                mock.patch("shortcut_manager.os.access", return_value=False):
            self.assertFalse(shortcut_manager.executable_path_is_valid("/bin/zsh", "darwin"))

    def test_manager_run_starts_daemon_worker_with_projected_actions(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.root = mock.Mock()
        manager.settings = {"terminal_path": "cmd.exe"}
        manager._active_runs = {}
        manager._ui_events = shortcut_manager.queue.Queue()
        manager._selected_shortcut = mock.Mock(return_value={
            "name": "Tool", "action_mode": ACTION_MODE_PROGRAM,
            "program_path": r"C:\Program Files\Tool\tool.exe",
            "arguments": "--run", "start_in": "",
        })
        manager._set_status = mock.Mock()
        with mock.patch("shortcut_manager.uuid.uuid4", return_value=SimpleNamespace(hex="run1")), \
                mock.patch("shortcut_manager.threading.Thread") as thread:
            manager.run()
        thread.assert_called_once()
        self.assertTrue(thread.call_args.kwargs["daemon"])
        args = thread.call_args.kwargs["args"]
        self.assertEqual(args[0:3], ("run1", "Tool", "cmd.exe"))
        self.assertEqual(args[3][0]["program_path"], r"C:\Program Files\Tool\tool.exe")
        thread.return_value.start.assert_called_once_with()
        self.assertIn("run1", manager._active_runs)

    def test_worker_only_enqueues_progress_and_result(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager._ui_events = shortcut_manager.queue.Queue()
        manager._set_status = mock.Mock()
        result = RunResult(
            "run1", "sequential", (ActionResult(0, "Build", STATUS_SUCCESS, 0),),
        )
        cancel_event = threading.Event()

        def launch(*_args, **kwargs):
            kwargs["on_progress"](ProgressEvent("run1", "launching", 0, 1))
            return result

        with mock.patch("shortcut_manager.launch_shortcut", side_effect=launch) as launcher:
            manager._run_shortcut_worker(
                "run1", "Daily Build", "cmd.exe",
                [{"name": "Build", "command": "echo ok", "start_in": ""}],
                "sequential", "#2563EB", cancel_event,
            )
        launcher.assert_called_once()
        self.assertEqual(manager._ui_events.get_nowait()[0], "progress")
        queued = manager._ui_events.get_nowait()
        self.assertEqual(queued[0], "result")
        self.assertIs(queued[3], result)
        manager._set_status.assert_not_called()

    def test_ui_event_processing_aggregates_all_failures_on_main_thread(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.root = mock.Mock()
        manager._exiting = False
        manager._active_runs = {"run1": threading.Event()}
        manager._ui_events = shortcut_manager.queue.Queue()
        manager._set_status = mock.Mock()
        result = RunResult("run1", "sequential", (
            ActionResult(0, "API", STATUS_FAILED, 2, "Exited with code 2."),
            ActionResult(1, "Web", "launch_error", detail="missing"),
        ))
        manager._ui_events.put(("result", "run1", "Development", result))
        with mock.patch("shortcut_manager.messagebox.showerror") as showerror:
            manager._process_ui_events()
        message = showerror.call_args.args[1]
        self.assertIn("API", message)
        self.assertIn("Web", message)
        self.assertNotIn("run1", manager._active_runs)
        manager.root.after.assert_called_once_with(100, manager._process_ui_events)

    def test_action_reorder_and_delete_preserve_valid_order(self):
        dialog = SimpleNamespace(
            actions=[{"name": "One"}, {"name": "Two"}, {"name": "Three"}],
            _selected_action_index=lambda: 1,
            _refresh_action_list=mock.Mock(),
        )
        shortcut_manager.ShortcutDialog._move_action(dialog, -1)
        self.assertEqual([action["name"] for action in dialog.actions], ["Two", "One", "Three"])
        dialog._selected_action_index = lambda: 1
        shortcut_manager.ShortcutDialog._delete_action(dialog)
        self.assertEqual([action["name"] for action in dialog.actions], ["Two", "Three"])
        dialog._refresh_action_list.assert_called_with(1)

    def test_action_clone_inserts_independent_copy_after_selection(self):
        original = {"name": "API", "command": "echo api", "metadata": {"value": 1}}
        dialog = SimpleNamespace(
            actions=[original, {"name": "Web"}],
            _selected_action_index=lambda: 0,
            actions_error=mock.Mock(), _refresh_action_list=mock.Mock(),
        )
        shortcut_manager.ShortcutDialog._clone_action(dialog)
        self.assertEqual([action["name"] for action in dialog.actions], ["API", "API", "Web"])
        self.assertIsNot(dialog.actions[1], original)
        self.assertIsNot(dialog.actions[1]["metadata"], original["metadata"])
        dialog.actions[1]["metadata"]["value"] = 2
        self.assertEqual(original["metadata"]["value"], 1)
        dialog._refresh_action_list.assert_called_once_with(1)

    def test_shortcut_clone_prompts_for_name_and_deep_copies_before_save(self):
        original = {
            "name": "Development", "actions": [
                {"name": "API", "command": "echo api", "metadata": {"value": 1}},
            ],
        }
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.root = mock.Mock()
        manager.shortcuts = [original]
        manager._selected_shortcut = mock.Mock(return_value=original)
        manager.save = mock.Mock(return_value=True)
        manager.refresh_cards = mock.Mock()
        manager._set_status = mock.Mock()
        with mock.patch("shortcut_manager.simpledialog.askstring", return_value="Development Copy") as ask:
            manager.clone()
        self.assertEqual(len(manager.shortcuts), 2)
        cloned = manager.shortcuts[1]
        self.assertEqual(cloned["name"], "Development Copy")
        self.assertIsNot(cloned, original)
        self.assertIsNot(cloned["actions"][0]["metadata"], original["actions"][0]["metadata"])
        ask.assert_called_once_with(
            "Clone Shortcut", "Enter a name for the cloned shortcut:",
            initialvalue="Development Copy", parent=manager.root,
        )
        manager.save.assert_called_once_with()
        manager.refresh_cards.assert_called_once_with(preserve_selection=True)

    def test_shortcut_clone_cancel_does_not_modify_or_save(self):
        original = {"name": "Demo", "command": "echo ok"}
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.root = mock.Mock()
        manager.shortcuts = [original]
        manager._selected_shortcut = mock.Mock(return_value=original)
        manager.save = mock.Mock()
        with mock.patch("shortcut_manager.simpledialog.askstring", return_value=None):
            manager.clone()
        self.assertEqual(manager.shortcuts, [original])
        manager.save.assert_not_called()

    def test_shortcut_context_selects_card_before_showing_menu(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager.select_shortcut = mock.Mock()
        manager.shortcut_context_menu = mock.Mock()
        event = SimpleNamespace(x_root=100, y_root=200)
        manager._show_shortcut_context(event, 4)
        manager.select_shortcut.assert_called_once_with(4)
        manager.shortcut_context_menu.tk_popup.assert_called_once_with(100, 200)
        manager.shortcut_context_menu.grab_release.assert_called_once_with()

    def test_shortcut_dialog_import_replaces_actions_from_all_exec_entries(self):
        xml_text = build_task_scheduler_shortcut_xml("Imported Task", [
            {"name": "One", "action_mode": ACTION_MODE_PROGRAM, "program_path": "one.exe"},
            {"name": "Two", "action_mode": ACTION_MODE_PROGRAM, "program_path": "two.exe"},
        ])
        with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-8", delete=False) as task_file:
            task_file.write(xml_text)
            path = task_file.name
        dialog = SimpleNamespace(
            actions=[{"name": "Old"}], execution_mode=mock.Mock(), name=mock.Mock(),
            actions_error=mock.Mock(), _replace_entry=mock.Mock(), _refresh_action_list=mock.Mock(),
        )
        dialog.name.get.return_value = ""
        try:
            with mock.patch("shortcut_manager.filedialog.askopenfilename", return_value=path):
                shortcut_manager.ShortcutDialog._import_task_xml(dialog)
        finally:
            shortcut_manager.os.remove(path)
        self.assertEqual([action["program_path"] for action in dialog.actions], ["one.exe", "two.exe"])
        dialog.execution_mode.set.assert_called_once_with("sequential")
        dialog._replace_entry.assert_called_once_with(dialog.name, "Imported Task")
        dialog._refresh_action_list.assert_called_once_with(0)

    def test_shortcut_dialog_export_writes_every_action(self):
        actions = [
            {"name": "Command", "command": "echo ok", "start_in": ""},
            {"name": "Program", "action_mode": ACTION_MODE_PROGRAM,
             "program_path": "tool.exe", "arguments": "--go", "start_in": ""},
        ]
        dialog = SimpleNamespace(
            name=mock.Mock(), folder=mock.Mock(), color_var=mock.Mock(),
            execution_mode=mock.Mock(), actions=actions, shortcut={},
            name_error=mock.Mock(), actions_error=mock.Mock(), action_list=mock.Mock(),
        )
        dialog.name.get.return_value = "Exported Task"
        dialog.folder.get.return_value = "General"
        dialog.color_var.get.return_value = ""
        dialog.execution_mode.get.return_value = "parallel"
        with tempfile.TemporaryDirectory() as directory:
            destination = shortcut_manager.os.path.join(directory, "task.xml")
            with mock.patch("shortcut_manager.filedialog.asksaveasfilename", return_value=destination), \
                    mock.patch("shortcut_manager.messagebox.showinfo") as showinfo:
                shortcut_manager.ShortcutDialog._export_task_xml(dialog)
            with open(destination, "r", encoding="utf-8") as task_file:
                parsed = parse_task_scheduler_shortcut_xml(task_file.read())
        self.assertEqual(len(parsed["actions"]), 2)
        self.assertEqual(parsed["actions"][0]["program_path"], "cmd.exe")
        self.assertEqual(parsed["actions"][1]["program_path"], "tool.exe")
        showinfo.assert_called_once()

    def test_exit_application_cancels_all_monitors_before_destroy(self):
        manager = shortcut_manager.ShortcutManager.__new__(shortcut_manager.ShortcutManager)
        manager._exiting = False
        manager.root = mock.Mock()
        manager.tray_icon = None
        manager._stop_restore_hotkey_listener = mock.Mock()
        events = {"one": threading.Event(), "two": threading.Event()}
        manager._active_runs = events
        manager.exit_application()
        self.assertTrue(all(event.is_set() for event in events.values()))
        self.assertEqual(manager._active_runs, {})
        manager.root.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
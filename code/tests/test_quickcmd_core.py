import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from quickcmd_core import (
    ACTION_MODE_COMMAND_LINE,
    ACTION_MODE_PROGRAM,
    EXECUTION_MODE_PARALLEL,
    EXECUTION_MODE_SEQUENTIAL,
    ConfigError,
    GENERAL_FOLDER,
    TaskSchedulerError,
    ValidationError,
    build_batch_script,
    build_task_scheduler_shortcut_xml,
    build_task_scheduler_xml,
    build_terminal_argv,
    command_preview,
    current_platform,
    default_settings,
    executable_base_dir,
    filter_shortcuts,
    legacy_config_candidates,
    load_config,
    normalize_config,
    normalize_action_input,
    normalize_restore_hotkey_setting,
    normalize_shortcut_color,
    normalize_shortcut_input,
    normalize_folder,
    parse_task_scheduler_xml,
    parse_task_scheduler_shortcut_xml,
    resource_base_dir,
    save_config,
    shortcut_action_mode,
    shortcut_actions,
    shortcut_actions_preview,
    shortcut_command,
    shortcut_execution_mode,
    shortcut_folder,
    unique_shortcut_folders,
    user_config_path,
)


class ConfigTests(unittest.TestCase):
    def test_platform_names_and_defaults(self):
        self.assertEqual(current_platform("win32"), "windows")
        self.assertEqual(current_platform("darwin"), "macos")
        self.assertEqual(default_settings("win32")["terminal_path"], "cmd.exe")
        self.assertEqual(default_settings("darwin")["terminal_path"], "/bin/zsh")
        self.assertEqual(default_settings()["restore_hotkey"], "")

    def test_user_config_path_uses_local_app_data(self):
        with tempfile.TemporaryDirectory() as local_app_data:
            self.assertEqual(
                user_config_path(local_app_data),
                os.path.join(local_app_data, "FlashCMD", "shortcuts.json"),
            )
            self.assertEqual(
                user_config_path(local_app_data, app_name="QuickCMD"),
                os.path.join(local_app_data, "QuickCMD", "shortcuts.json"),
            )

    def test_user_config_paths_cover_macos_and_xdg(self):
        self.assertEqual(
            user_config_path(platform="darwin", home="/Users/demo"),
            "/Users/demo/Library/Application Support/FlashCMD/shortcuts.json",
        )
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/config"}):
            self.assertEqual(
                user_config_path(platform="linux", home="/home/demo"),
                "/tmp/config/FlashCMD/shortcuts.json",
            )

    def test_resource_and_executable_bases_stay_separate_when_frozen(self):
        frozen = SimpleNamespace(
            frozen=True, _MEIPASS=r"C:\Temp\_MEI123", executable=r"C:\Apps\FlashCmd.exe",
        )
        self.assertEqual(resource_base_dir(sys_module=frozen), r"C:\Temp\_MEI123")
        self.assertEqual(executable_base_dir(sys_module=frozen), r"C:\Apps")
        source = SimpleNamespace(frozen=False)
        expected = os.path.abspath(os.path.join("sample", "package"))
        self.assertEqual(
            resource_base_dir(os.path.join("sample", "package", "module.py"), source),
            expected,
        )

    def test_source_bases_use_parent_of_code_directory(self):
        source = SimpleNamespace(frozen=False)
        module_file = os.path.join("sample", "code", "module.py")
        expected = os.path.abspath("sample")
        self.assertEqual(resource_base_dir(module_file, source), expected)
        self.assertEqual(executable_base_dir(module_file, source), expected)

    def test_legacy_candidates_are_windows_only_and_ordered(self):
        windows = legacy_config_candidates(
            platform="win32", home=r"C:\Users\demo",
            local_app_data=r"C:\Users\demo\AppData\Local", executable_dir=r"D:\Portable",
        )
        self.assertEqual(windows, (
            r"C:\Users\demo\AppData\Local/FlashCMD/shortcuts.json".replace("/", os.sep),
            r"C:\Users\demo\AppData\Local/FlashCmd/shortcuts.json".replace("/", os.sep),
            r"C:\Users\demo\AppData\Local/QuickCMD/shortcuts.json".replace("/", os.sep),
            r"D:\Portable/shortcuts.json".replace("/", os.sep),
        ))
        macos = legacy_config_candidates(platform="darwin", home="/Users/demo")
        self.assertEqual(macos, (
            "/Users/demo/Library/Application Support/FlashCMD/shortcuts.json",
            "/Users/demo/Library/Application Support/FlashCmd/shortcuts.json",
            "/Users/demo/Library/Application Support/QuickCMD/shortcuts.json",
        ))

    def test_current_config_defaults_and_preserves_unknown_fields(self):
        raw = {
            "shortcuts": [{"name": "Build", "command": "go", "mode": "external"}],
            "settings": {"theme": "system"},
        }
        result = normalize_config(raw)
        self.assertEqual(result["settings"]["terminal_path"], "cmd.exe")
        self.assertEqual(result["settings"]["theme"], "system")
        self.assertEqual(result["shortcuts"][0]["mode"], "external")

    def test_normalization_accepts_deterministic_platform(self):
        self.assertEqual(normalize_config({}, platform="darwin")["settings"]["terminal_path"], "/bin/zsh")

    def test_legacy_list_is_accepted_and_input_is_not_mutated(self):
        raw = [{"name": "One", "command": "echo 1", "nested": {"value": 1}}]
        result = normalize_config(raw)
        result["shortcuts"][0]["nested"]["value"] = 2
        self.assertEqual(raw[0]["nested"]["value"], 1)
        self.assertEqual(result["settings"], {
            "terminal_path": "cmd.exe", "theme": "light", "primary_color": "blue", "restore_hotkey": ""
        })

    def test_restore_hotkey_setting_is_trimmed_or_disabled(self):
        self.assertEqual(normalize_restore_hotkey_setting(" Ctrl+Alt+F "), "Ctrl+Alt+F")
        self.assertEqual(normalize_restore_hotkey_setting(None), "")

    def test_shortcut_color_is_normalized_and_invalid_values_are_removed(self):
        self.assertEqual(normalize_shortcut_color(" #a1b2c3 "), "#A1B2C3")
        self.assertEqual(normalize_shortcut_color("blue"), "")
        result = normalize_config({"shortcuts": [
            {"name": "Good", "color": "#abcdef"},
            {"name": "Bad", "color": "not-a-color"},
        ]})
        self.assertEqual(result["shortcuts"][0]["color"], "#ABCDEF")
        self.assertNotIn("color", result["shortcuts"][1])

    def test_terminal_args_is_removed_without_mutating_input(self):
        raw = {"settings": {"terminal_path": "cmd.exe", "terminal_args": ["/k"]}}
        result = normalize_config(raw)
        self.assertNotIn("terminal_args", result["settings"])
        self.assertIn("terminal_args", raw["settings"])

    def test_malformed_sections_raise_config_error(self):
        invalid = (None, "text", 4, {"shortcuts": {}}, {"settings": []}, ["bad"])
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ConfigError):
                normalize_config(raw)

    def test_missing_file_loads_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            result = load_config(os.path.join(directory, "missing.json"))
        self.assertEqual(result, {"shortcuts": [], "settings": {
            "terminal_path": "cmd.exe", "theme": "light", "primary_color": "blue", "restore_hotkey": ""
        }})

    def test_utf8_multiline_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "QuickCMD", "shortcuts.json")
            shortcuts = [{"name": "Café", "command": "echo α\necho β", "mode": "external"}]
            settings = {
                "terminal_path": "cmd.exe", "theme": "dark",
                "primary_color": "orange", "custom": True,
            }
            save_config(path, shortcuts, settings)
            loaded = load_config(path)
            self.assertEqual(loaded["shortcuts"], shortcuts)
            self.assertEqual(loaded["settings"], {**settings, "restore_hotkey": ""})
            with open(path, "r", encoding="utf-8") as saved:
                self.assertIn("Café", saved.read())

    def test_failed_replace_leaves_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "shortcuts.json")
            original = {"shortcuts": [{"name": "Old", "command": "old"}], "settings": {}}
            with open(path, "w", encoding="utf-8") as config_file:
                json.dump(original, config_file)
            with mock.patch("quickcmd_core.os.replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    save_config(path, [{"name": "New", "command": "new"}], {})
            with open(path, "r", encoding="utf-8") as config_file:
                self.assertEqual(json.load(config_file), original)
            self.assertEqual(os.listdir(directory), ["shortcuts.json"])


class ShortcutHelperTests(unittest.TestCase):
    def setUp(self):
        self.shortcuts = [
            {"name": "Build API", "command": "python app.py", "start_in": "C:/Work/API", "folder": "Development"},
            {"name": "Docs", "command": "mkdocs serve", "start_in": "C:/Work/Docs", "folder": "Documentation"},
        ]

    def test_input_is_trimmed_and_newlines_are_normalized(self):
        result = normalize_shortcut_input("  Demo  ", " echo one\r\necho two\r ", " C:/Work ")
        self.assertEqual(result, {
            "name": "Demo", "action_mode": ACTION_MODE_COMMAND_LINE,
            "command": "echo one\necho two", "start_in": "C:/Work", "folder": "General",
        })

    def test_program_input_stores_separate_fields(self):
        result = normalize_shortcut_input(
            " Backup ", "ignored", " C:/Work ", ACTION_MODE_PROGRAM,
            r" C:\Tools\backup.exe ", ' --target "Daily Files" ',
        )
        self.assertEqual(result, {
            "name": "Backup", "action_mode": ACTION_MODE_PROGRAM,
            "program_path": r"C:\Tools\backup.exe",
            "arguments": '--target "Daily Files"', "start_in": "C:/Work", "folder": "General",
        })

    def test_folder_is_trimmed_and_defaults_to_general(self):
        result = normalize_shortcut_input(
            "Demo", "echo ok", "", folder=" Work ",
        )
        self.assertEqual(result["folder"], "Work")
        self.assertEqual(normalize_folder("  "), GENERAL_FOLDER)
        self.assertEqual(normalize_folder(" general "), GENERAL_FOLDER)

    def test_shortcut_input_includes_only_a_selected_valid_color(self):
        colored = normalize_shortcut_input("Demo", "echo ok", "", color=" #2563eb ")
        plain = normalize_shortcut_input("Demo", "echo ok", "", color="invalid")
        self.assertEqual(colored["color"], "#2563EB")
        self.assertNotIn("color", plain)

    def test_program_input_requires_program_path(self):
        with self.assertRaises(ValidationError) as raised:
            normalize_shortcut_input("Backup", "", "", ACTION_MODE_PROGRAM, "", "--all")
        self.assertEqual(raised.exception.field, "program_path")

    def test_program_command_quotes_executable_and_keeps_raw_arguments(self):
        shortcut = {
            "action_mode": ACTION_MODE_PROGRAM,
            "program_path": r"C:\Program Files\Tool\tool.exe",
            "arguments": '--name "Daily Files"',
        }
        self.assertEqual(
            shortcut_command(shortcut, "win32"),
            r'"C:\Program Files\Tool\tool.exe" --name "Daily Files"',
        )
        self.assertEqual(shortcut_action_mode({"command": "echo old"}), ACTION_MODE_COMMAND_LINE)

    def test_missing_required_fields_identify_the_field(self):
        for values, field in (((' ', 'go', ''), 'name'), (('Demo', '\r\n', ''), 'command')):
            with self.subTest(field=field), self.assertRaises(ValidationError) as raised:
                normalize_shortcut_input(*values)
            self.assertEqual(raised.exception.field, field)

    def test_filter_blank_returns_all_source_pairs(self):
        self.assertEqual(filter_shortcuts(self.shortcuts, "  "), list(enumerate(self.shortcuts)))

    def test_filter_is_case_insensitive_across_all_fields(self):
        self.assertEqual([i for i, _ in filter_shortcuts(self.shortcuts, "api")], [0])
        self.assertEqual([i for i, _ in filter_shortcuts(self.shortcuts, "MKDOCS")], [1])
        self.assertEqual([i for i, _ in filter_shortcuts(self.shortcuts, "work/docs")], [1])
        self.assertEqual([i for i, _ in filter_shortcuts(self.shortcuts, "DEVELOPMENT")], [0])
        program = [{"name": "Backup", "action_mode": ACTION_MODE_PROGRAM,
                    "program_path": "backup.exe", "arguments": "--daily"}]
        self.assertEqual([i for i, _ in filter_shortcuts(program, "daily")], [0])

    def test_filter_retains_source_index_and_order(self):
        matches = filter_shortcuts(self.shortcuts, "work")
        self.assertEqual([index for index, _ in matches], [0, 1])
        self.assertIs(matches[1][1], self.shortcuts[1])

    def test_legacy_first_tag_becomes_folder_and_missing_folder_is_general(self):
        self.assertEqual(shortcut_folder({"tags": ["Work", "Python"]}), "Work")
        self.assertEqual(shortcut_folder({"command": "echo ok"}), "General")

    def test_unique_folders_are_case_insensitive_with_general_first(self):
        shortcuts = self.shortcuts + [
            {"folder": "development"}, {"folder": "Admin"}, {},
        ]
        self.assertEqual(
            unique_shortcut_folders(shortcuts),
            ["General", "Admin", "Development", "Documentation"],
        )

    def test_preview_is_two_lines_with_deterministic_ellipsis(self):
        self.assertEqual(command_preview("one\r\ntwo\r\nthree"), "one\ntwo…")
        self.assertEqual(command_preview("x" * 101), "x" * 99 + "…")

    def test_legacy_projection_is_detached_and_does_not_migrate_source(self):
        legacy = {"name": "Build", "command": " echo ok ", "start_in": " C:/Work "}
        actions = shortcut_actions(legacy)
        self.assertEqual(actions, [{
            "name": "Build", "action_mode": ACTION_MODE_COMMAND_LINE,
            "command": "echo ok", "start_in": "C:/Work",
        }])
        actions[0]["name"] = "Changed"
        self.assertNotIn("actions", legacy)
        self.assertEqual(legacy["name"], "Build")

    def test_current_shortcut_round_trip_preserves_order_and_unknown_metadata(self):
        original = {
            "name": "Old", "command": "legacy", "action_mode": ACTION_MODE_COMMAND_LINE,
            "start_in": "old", "custom": {"kept": True}, "color": "#000000",
        }
        result = normalize_shortcut_input(
            " Development ", folder=" Work ", color=" #2563eb ",
            execution_mode=EXECUTION_MODE_PARALLEL,
            actions=[
                {"name": " API ", "command": " python app.py\r\n ", "start_in": " C:/API "},
                {"name": " Browser ", "action_mode": ACTION_MODE_PROGRAM,
                 "program_path": " browser.exe ", "arguments": " http://localhost ", "start_in": ""},
            ],
            existing=original,
        )
        self.assertEqual(result["execution_mode"], EXECUTION_MODE_PARALLEL)
        self.assertEqual([action["name"] for action in result["actions"]], ["API", "Browser"])
        self.assertEqual(result["actions"][0]["command"], "python app.py")
        self.assertEqual(result["custom"], {"kept": True})
        for field in ("command", "action_mode", "program_path", "arguments", "start_in"):
            self.assertNotIn(field, result)

    def test_action_validation_identifies_index_and_field(self):
        with self.assertRaises(ValidationError) as raised:
            normalize_shortcut_input("Demo", actions=[{"name": "First", "command": ""}])
        self.assertEqual(raised.exception.field, "actions[0].command")
        with self.assertRaises(ValidationError) as empty:
            normalize_shortcut_input("Demo", actions=[])
        self.assertEqual(empty.exception.field, "actions")
        with self.assertRaises(ValidationError) as unnamed:
            normalize_action_input({"name": " ", "command": "echo ok"})
        self.assertEqual(unnamed.exception.field, "name")

    def test_current_malformed_action_lists_fail_instead_of_running_nothing(self):
        for shortcut in ({"name": "Empty", "actions": []}, {"name": "Bad", "actions": ["no"]}):
            with self.subTest(shortcut=shortcut), self.assertRaises(ValidationError):
                shortcut_actions(shortcut)

    def test_execution_mode_defaults_and_preview_are_ordered(self):
        shortcut = {
            "name": "Demo", "execution_mode": "invalid",
            "actions": [
                {"name": "One", "command": "echo 1"},
                {"name": "Two", "action_mode": ACTION_MODE_PROGRAM, "program_path": "tool.exe"},
            ],
        }
        self.assertEqual(shortcut_execution_mode(shortcut), EXECUTION_MODE_SEQUENTIAL)
        self.assertEqual(shortcut_actions_preview(shortcut), "1. One (Command)\n2. Two (Program)")

    def test_nested_filter_searches_every_action_field(self):
        shortcuts = [{
            "name": "Development", "folder": "Work",
            "actions": [
                {"name": "API", "command": "python app.py", "start_in": "C:/Services"},
                {"name": "Browser", "action_mode": ACTION_MODE_PROGRAM,
                 "program_path": "browser.exe", "arguments": "localhost:8000"},
            ],
        }]
        for query in ("api", "services", "browser.exe", "localhost"):
            with self.subTest(query=query):
                self.assertEqual([index for index, _ in filter_shortcuts(shortcuts, query)], [0])

    def test_saving_does_not_canonicalize_unrelated_legacy_shortcut(self):
        legacy = {"name": "Legacy", "command": "echo old", "custom": "untouched"}
        current = normalize_shortcut_input(
            "Current", actions=[{"name": "Run", "command": "echo new"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "shortcuts.json")
            save_config(path, [legacy, current], {})
            loaded = load_config(path)["shortcuts"]
        self.assertEqual(loaded[0], legacy)
        self.assertNotIn("actions", loaded[0])


class TerminalHelperTests(unittest.TestCase):
    def test_cmd_variants_receive_only_k_and_batch(self):
        variants = ("cmd.exe", "cmd", "CMD.EXE", r"C:\\Windows\\System32\\CmD.ExE")
        for terminal in variants:
            with self.subTest(terminal=terminal):
                self.assertEqual(build_terminal_argv(terminal, r"C:\\Temp Files\\run.bat"), [
                    terminal, "/k", r"C:\\Temp Files\\run.bat"
                ])

    def test_custom_terminal_and_spaces_remain_single_arguments(self):
        terminal = r"C:\\Program Files\\Terminal\\terminal.exe"
        batch = r"C:\\Temp Files\\quick cmd.bat"
        self.assertEqual(build_terminal_argv(terminal, batch), [terminal, batch])

    def test_batch_script_has_exact_prefix_normalized_content_and_newline(self):
        self.assertEqual(build_batch_script(" echo one\r\necho two\r "), "@echo off\necho one\necho two\n")
        self.assertNotIn("/k", build_batch_script("echo ok"))


class TaskSchedulerXmlTests(unittest.TestCase):
    def test_export_and_import_round_trip_exec_fields(self):
        xml_text = build_task_scheduler_xml(
            "Nightly <Backup>", r"C:\Program Files\Backup\backup.exe",
            '--target "Daily & Weekly"', r"C:\Work Files",
        )
        self.assertIn("windows/2004/02/mit/task", xml_text)
        parsed = parse_task_scheduler_xml(xml_text)
        self.assertEqual(parsed, {
            "name": "Nightly <Backup>", "action_mode": ACTION_MODE_PROGRAM,
            "program_path": r"C:\Program Files\Backup\backup.exe",
            "arguments": '--target "Daily & Weekly"', "start_in": r"C:\Work Files",
        })

    def test_import_accepts_namespaced_task_scheduler_xml(self):
        xml_text = '''<?xml version="1.0"?>
        <Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <Actions><Exec><Command>tool.exe</Command><Arguments>--go</Arguments></Exec></Actions>
        </Task>'''
        self.assertEqual(parse_task_scheduler_xml(xml_text)["program_path"], "tool.exe")

    def test_import_rejects_missing_or_multiple_exec_actions(self):
        for xml_text in ("<Task />", "<Task><Exec/><Exec/></Task>"):
            with self.subTest(xml=xml_text), self.assertRaises(TaskSchedulerError):
                parse_task_scheduler_xml(xml_text)

    def test_multi_action_export_preserves_order_and_maps_commands_to_cmd(self):
        xml_text = build_task_scheduler_shortcut_xml("Development", [
            {"name": "API Server", "command": "python app.py\necho ready", "start_in": r"C:\API"},
            {"name": "Browser", "action_mode": ACTION_MODE_PROGRAM,
             "program_path": "browser.exe", "arguments": "http://localhost", "start_in": ""},
        ])
        parsed = parse_task_scheduler_shortcut_xml(xml_text)
        self.assertEqual(parsed["name"], "Development")
        self.assertEqual([action["name"] for action in parsed["actions"]], ["API_Server", "Browser"])
        self.assertEqual(parsed["actions"][0]["program_path"], "cmd.exe")
        self.assertIn("/d /c", parsed["actions"][0]["arguments"])
        self.assertIn("python app.py\necho ready", parsed["actions"][0]["arguments"])
        self.assertEqual(parsed["actions"][0]["start_in"], r"C:\API")
        self.assertEqual(parsed["actions"][1]["program_path"], "browser.exe")

    def test_multi_action_import_uses_exec_ids_or_ordered_fallback_names(self):
        xml_text = '''<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <RegistrationInfo><Description>Imported Task</Description></RegistrationInfo>
          <Actions>
            <Exec id="First"><Command>one.exe</Command></Exec>
            <Exec><Command>two.exe</Command><Arguments>--go</Arguments></Exec>
          </Actions>
        </Task>'''
        parsed = parse_task_scheduler_shortcut_xml(xml_text)
        self.assertEqual([action["name"] for action in parsed["actions"]], ["First", "Action 2"])
        self.assertTrue(all(action["action_mode"] == ACTION_MODE_PROGRAM for action in parsed["actions"]))
        self.assertEqual(parsed["actions"][1]["arguments"], "--go")

    def test_multi_action_import_identifies_invalid_exec_index(self):
        xml_text = "<Task><Actions><Exec><Command>ok.exe</Command></Exec><Exec /></Actions></Task>"
        with self.assertRaisesRegex(TaskSchedulerError, "action 2"):
            parse_task_scheduler_shortcut_xml(xml_text)


if __name__ == "__main__":
    unittest.main()
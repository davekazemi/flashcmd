"""Pure configuration, filtering, and launch helpers for FlashCMD."""

from copy import deepcopy
import json
import ntpath
import os
import posixpath
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


PREVIEW_LINE_LENGTH = 100
ACTION_MODE_COMMAND_LINE = "command_line"
ACTION_MODE_PROGRAM = "program"
GENERAL_FOLDER = "General"
TASK_SCHEDULER_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
APP_STORAGE_NAME = "FlashCMD"
LEGACY_STORAGE_NAMES = ("FlashCmd", "QuickCMD")


def current_platform(platform=None):
    """Return a stable platform name for runtime behavior and tests."""
    value = (platform or sys.platform).casefold()
    if value.startswith(("win", "cygwin", "msys")):
        return "windows"
    if value in ("darwin", "mac", "macos"):
        return "macos"
    return value


def default_terminal_path(platform=None):
    """Return the native command interpreter used for new settings."""
    system = current_platform(platform)
    if system == "windows":
        return "cmd.exe"
    if system == "macos":
        return "/bin/zsh"
    return os.environ.get("SHELL") or "/bin/sh"


def default_settings(platform=None):
    """Return a fresh settings mapping with platform-native defaults."""
    return {
        "terminal_path": default_terminal_path(platform),
        "theme": "light",
        "primary_color": "blue",
        "restore_hotkey": "",
    }


DEFAULT_SETTINGS = default_settings()


def resource_base_dir(module_file=__file__, sys_module=sys):
    """Return the source or PyInstaller extraction directory for assets."""
    if getattr(sys_module, "frozen", False) and getattr(sys_module, "_MEIPASS", None):
        return os.path.abspath(os.fspath(sys_module._MEIPASS))
    return os.path.dirname(os.path.abspath(os.fspath(module_file)))


def executable_base_dir(module_file=__file__, sys_module=sys):
    """Return the source or frozen executable directory for legacy files."""
    if getattr(sys_module, "frozen", False):
        return os.path.dirname(os.path.abspath(os.fspath(sys_module.executable)))
    return os.path.dirname(os.path.abspath(os.fspath(module_file)))


def user_config_path(local_app_data=None, app_name=APP_STORAGE_NAME, platform=None, home=None):
    """Return the app's persistent per-user configuration path."""
    system = current_platform(platform)
    home_dir = os.path.expanduser("~") if home is None else os.fspath(home)
    if system == "windows":
        path = ntpath
        base = local_app_data or os.environ.get("LOCALAPPDATA")
        if not base:
            base = path.join(home_dir, "AppData", "Local")
    elif system == "macos":
        path = posixpath
        base = path.join(home_dir, "Library", "Application Support")
    else:
        path = posixpath
        base = os.environ.get("XDG_CONFIG_HOME") or path.join(home_dir, ".config")
    return path.join(base, app_name, "shortcuts.json")


def legacy_config_candidates(
    platform=None, home=None, local_app_data=None, executable_dir=None,
):
    """Return config candidates in read precedence; saves never use fallbacks."""
    system = current_platform(platform)
    current = user_config_path(
        local_app_data, platform=system, home=home,
    )
    legacy_names = [name for name in LEGACY_STORAGE_NAMES if name != APP_STORAGE_NAME]
    legacy_users = tuple(
        user_config_path(local_app_data, app_name=name, platform=system, home=home)
        for name in legacy_names
    )
    if system != "windows":
        return (current, *legacy_users)
    legacy_executable = ntpath.join(
        executable_dir or executable_base_dir(), "shortcuts.json",
    )
    return (current, *legacy_users, legacy_executable)


class ConfigError(ValueError):
    """Raised when a configuration has an unsupported structure."""


class ValidationError(ValueError):
    """Raised when shortcut input is incomplete or invalid."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


class TaskSchedulerError(ValueError):
    """Raised when Task Scheduler XML cannot represent one program action."""


def _normalize_newlines(value):
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_legacy_tags(tags):
    """Normalize legacy tags so their first value can become a folder."""
    if isinstance(tags, str):
        values = tags.split(",")
    elif isinstance(tags, (list, tuple, set)):
        values = [part for value in tags if isinstance(value, str) for part in value.split(",")]
    else:
        values = []
    result = []
    seen = set()
    for value in values:
        clean = value.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def normalize_folder(folder):
    """Return one clean folder name, defaulting empty values to General."""
    clean = folder.strip() if isinstance(folder, str) else ""
    if not clean or clean.casefold() == GENERAL_FOLDER.casefold():
        return GENERAL_FOLDER
    return clean


def normalize_restore_hotkey_setting(value):
    """Store restore hotkeys as a simple trimmed string or disable them."""
    return value.strip() if isinstance(value, str) else ""


def normalize_config(raw, platform=None):
    """Return a detached, current-form configuration without writing it."""
    if isinstance(raw, list):
        shortcuts, settings = raw, {}
    elif isinstance(raw, dict):
        shortcuts = raw.get("shortcuts", [])
        settings = raw.get("settings", {})
    else:
        raise ConfigError("Configuration root must be an object or a list.")

    if not isinstance(shortcuts, list):
        raise ConfigError("The 'shortcuts' section must be a list.")
    if not isinstance(settings, dict):
        raise ConfigError("The 'settings' section must be an object.")
    if any(not isinstance(shortcut, dict) for shortcut in shortcuts):
        raise ConfigError("Every shortcut must be an object.")

    normalized_settings = default_settings(platform)
    normalized_settings.update(deepcopy(settings))
    normalized_settings.pop("terminal_args", None)
    normalized_settings["restore_hotkey"] = normalize_restore_hotkey_setting(
        normalized_settings.get("restore_hotkey", ""),
    )
    return {
        "shortcuts": deepcopy(shortcuts),
        "settings": normalized_settings,
    }


def load_config(path, platform=None):
    """Load and normalize a JSON config, or return defaults if absent."""
    if not os.path.exists(path):
        return normalize_config({}, platform=platform)
    with open(path, "r", encoding="utf-8") as config_file:
        return normalize_config(json.load(config_file), platform=platform)


def save_config(path, shortcuts, settings):
    """Atomically save a validated configuration beside its destination."""
    data = normalize_config({"shortcuts": shortcuts, "settings": settings})
    target = os.path.abspath(os.fspath(path))
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=f".{os.path.basename(target)}.", suffix=".tmp", delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def normalize_shortcut_input(
    name, command, start_in, action_mode=ACTION_MODE_COMMAND_LINE,
    program_path="", arguments="", folder=GENERAL_FOLDER,
):
    """Normalize user-entered shortcut fields and validate required values."""
    clean_name = name.strip() if isinstance(name, str) else ""
    clean_command = _normalize_newlines(command).strip() if isinstance(command, str) else ""
    clean_start = start_in.strip() if isinstance(start_in, str) else ""
    clean_program = program_path.strip() if isinstance(program_path, str) else ""
    clean_arguments = _normalize_newlines(arguments).strip() if isinstance(arguments, str) else ""
    clean_folder = normalize_folder(folder)
    if not clean_name:
        raise ValidationError("Enter a shortcut name.", "name")
    if action_mode == ACTION_MODE_PROGRAM:
        if not clean_program:
            raise ValidationError("Enter a program or script to run.", "program_path")
        return {
            "name": clean_name, "action_mode": ACTION_MODE_PROGRAM,
            "program_path": clean_program, "arguments": clean_arguments,
            "start_in": clean_start, "folder": clean_folder,
        }
    if action_mode != ACTION_MODE_COMMAND_LINE:
        raise ValidationError("Choose a supported action type.", "action_mode")
    if not clean_command:
        raise ValidationError("Enter a command to run.", "command")
    return {
        "name": clean_name, "action_mode": ACTION_MODE_COMMAND_LINE,
        "command": clean_command, "start_in": clean_start, "folder": clean_folder,
    }


def shortcut_action_mode(shortcut):
    """Return a valid action mode, defaulting legacy shortcuts to command line."""
    if shortcut.get("action_mode") == ACTION_MODE_PROGRAM:
        return ACTION_MODE_PROGRAM
    return ACTION_MODE_COMMAND_LINE


def shortcut_command(shortcut, platform=None):
    """Return the command line used by the native terminal launcher."""
    if shortcut_action_mode(shortcut) == ACTION_MODE_COMMAND_LINE:
        return str(shortcut.get("command", ""))
    program = str(shortcut.get("program_path", "")).strip()
    arguments = str(shortcut.get("arguments", "")).strip()
    executable = (
        subprocess.list2cmdline([program])
        if current_platform(platform) == "windows" else shlex.quote(program)
    )
    return f"{executable} {arguments}" if arguments else executable


def build_task_scheduler_xml(name, program_path, arguments="", working_directory=""):
    """Build importable Task Scheduler XML containing one Exec action."""
    command = program_path.strip() if isinstance(program_path, str) else ""
    if not command:
        raise TaskSchedulerError("Task Scheduler actions require a program or script.")
    ET.register_namespace("", TASK_SCHEDULER_NAMESPACE)
    tag = lambda value: f"{{{TASK_SCHEDULER_NAMESPACE}}}{value}"
    root = ET.Element(tag("Task"), {"version": "1.4"})
    registration = ET.SubElement(root, tag("RegistrationInfo"))
    ET.SubElement(registration, tag("Description")).text = str(name).strip() or "FlashCMD shortcut"
    ET.SubElement(root, tag("Triggers"))
    principals = ET.SubElement(root, tag("Principals"))
    principal = ET.SubElement(principals, tag("Principal"), {"id": "Author"})
    ET.SubElement(principal, tag("LogonType")).text = "InteractiveToken"
    ET.SubElement(principal, tag("RunLevel")).text = "LeastPrivilege"
    settings = ET.SubElement(root, tag("Settings"))
    for key, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("AllowHardTerminate", "true"),
        ("StartWhenAvailable", "true"),
        ("AllowStartOnDemand", "true"),
        ("Enabled", "true"), ("Hidden", "false"),
        ("ExecutionTimeLimit", "PT0S"), ("Priority", "7"),
    ):
        ET.SubElement(settings, tag(key)).text = value
    actions = ET.SubElement(root, tag("Actions"), {"Context": "Author"})
    execute = ET.SubElement(actions, tag("Exec"))
    ET.SubElement(execute, tag("Command")).text = command
    clean_arguments = str(arguments).strip()
    if clean_arguments:
        ET.SubElement(execute, tag("Arguments")).text = clean_arguments
    clean_directory = str(working_directory).strip()
    if clean_directory:
        ET.SubElement(execute, tag("WorkingDirectory")).text = clean_directory
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def parse_task_scheduler_xml(xml_text):
    """Parse one Task Scheduler Exec action into FlashCMD program fields."""
    if not isinstance(xml_text, (str, bytes)):
        raise TaskSchedulerError("Task Scheduler XML must be text or bytes.")
    probe = xml_text.decode("utf-8", "ignore") if isinstance(xml_text, bytes) else xml_text
    if "<!DOCTYPE" in probe.upper():
        raise TaskSchedulerError("Task Scheduler XML document types are not supported.")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise TaskSchedulerError(f"Invalid Task Scheduler XML: {error}") from error
    local_name = lambda element: element.tag.rsplit("}", 1)[-1]
    actions = [element for element in root.iter() if local_name(element) == "Exec"]
    if len(actions) != 1:
        raise TaskSchedulerError("Task Scheduler XML must contain exactly one Exec action.")
    values = {
        local_name(child): (child.text or "").strip() for child in actions[0]
    }
    if not values.get("Command"):
        raise TaskSchedulerError("The Task Scheduler Exec action has no Command.")
    descriptions = [
        (element.text or "").strip() for element in root.iter()
        if local_name(element) == "Description" and (element.text or "").strip()
    ]
    return {
        "name": descriptions[0] if descriptions else "",
        "action_mode": ACTION_MODE_PROGRAM,
        "program_path": values["Command"],
        "arguments": values.get("Arguments", ""),
        "start_in": values.get("WorkingDirectory", ""),
    }


def shortcut_folder(shortcut):
    """Return a shortcut folder, using the first legacy tag when necessary."""
    if "folder" in shortcut:
        return normalize_folder(shortcut.get("folder"))
    legacy_tags = _normalize_legacy_tags(shortcut.get("tags", []))
    return legacy_tags[0] if legacy_tags else GENERAL_FOLDER


def unique_shortcut_folders(shortcuts):
    """Return shortcut folders sorted with General first."""
    folders_by_key = {}
    for shortcut in shortcuts:
        folder = shortcut_folder(shortcut)
        folders_by_key.setdefault(folder.casefold(), folder)
    folders = sorted(folders_by_key.values(), key=lambda value: (value.casefold(), value))
    return sorted(folders, key=lambda value: value.casefold() != GENERAL_FOLDER.casefold())


def filter_shortcuts(shortcuts, query):
    """Return source pairs matching shortcut fields or their folder."""
    needle = (query or "").strip().casefold()
    pairs = list(enumerate(shortcuts))
    if not needle:
        return pairs
    fields = ("name", "command", "program_path", "arguments", "start_in")
    return [
        (index, shortcut) for index, shortcut in pairs
        if any(needle in str(shortcut.get(field, "")).casefold() for field in fields)
        or needle in shortcut_folder(shortcut).casefold()
    ]


def command_preview(command):
    """Return a deterministic preview limited to two bounded lines."""
    text = _normalize_newlines(command if isinstance(command, str) else "").strip()
    if not text:
        return ""
    lines = text.split("\n")
    preview = lines[:2]
    truncated_lines = len(lines) > 2
    result = []
    for position, line in enumerate(preview):
        needs_ellipsis = len(line) > PREVIEW_LINE_LENGTH
        if needs_ellipsis:
            line = line[: PREVIEW_LINE_LENGTH - 1].rstrip() + "…"
        if truncated_lines and position == len(preview) - 1 and not line.endswith("…"):
            line = line[: PREVIEW_LINE_LENGTH - 1].rstrip() + "…"
        result.append(line)
    return "\n".join(result)


def build_batch_script(command):
    """Build the exact batch-file body used by the external launcher."""
    normalized = _normalize_newlines(command if isinstance(command, str) else "").strip()
    return "@echo off\n" + normalized + "\n"


def build_terminal_argv(terminal_path, batch_path):
    """Build an argument vector, adding /k only for Windows cmd."""
    terminal = os.fspath(terminal_path)
    batch = os.fspath(batch_path)
    args = [terminal]
    if ntpath.basename(terminal).casefold() in ("cmd", "cmd.exe"):
        args.append("/k")
    args.append(batch)
    return args
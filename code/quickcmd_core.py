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
EXECUTION_MODE_SEQUENTIAL = "sequential"
EXECUTION_MODE_PARALLEL = "parallel"
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


def _source_base_dir(module_file):
    """Return the repository root when source modules live in ``code/``."""
    module_dir = os.path.dirname(os.path.abspath(os.fspath(module_file)))
    if os.path.basename(module_dir).casefold() == "code":
        return os.path.dirname(module_dir)
    return module_dir


def resource_base_dir(module_file=__file__, sys_module=sys):
    """Return the source or PyInstaller extraction directory for assets."""
    if getattr(sys_module, "frozen", False) and getattr(sys_module, "_MEIPASS", None):
        return os.path.abspath(os.fspath(sys_module._MEIPASS))
    return _source_base_dir(module_file)


def executable_base_dir(module_file=__file__, sys_module=sys):
    """Return the source or frozen executable directory for legacy files."""
    if getattr(sys_module, "frozen", False):
        return os.path.dirname(os.path.abspath(os.fspath(sys_module.executable)))
    return _source_base_dir(module_file)


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


def normalize_shortcut_color(color):
    """Return an uppercase #RRGGBB action color, or blank if invalid."""
    clean = color.strip().upper() if isinstance(color, str) else ""
    if len(clean) != 7 or not clean.startswith("#"):
        return ""
    try:
        int(clean[1:], 16)
    except ValueError:
        return ""
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

    normalized_shortcuts = deepcopy(shortcuts)
    for shortcut in normalized_shortcuts:
        color = normalize_shortcut_color(shortcut.get("color", ""))
        if color:
            shortcut["color"] = color
        else:
            shortcut.pop("color", None)
        actions = shortcut.get("actions")
        if isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict):
                    continue
                action_color = normalize_shortcut_color(action.get("color", ""))
                if action_color:
                    action["color"] = action_color
                else:
                    action.pop("color", None)

    normalized_settings = default_settings(platform)
    normalized_settings.update(deepcopy(settings))
    normalized_settings.pop("terminal_args", None)
    normalized_settings["restore_hotkey"] = normalize_restore_hotkey_setting(
        normalized_settings.get("restore_hotkey", ""),
    )
    return {
        "shortcuts": normalized_shortcuts,
        "settings": normalized_settings,
    }


def load_config(path, platform=None):
    """Load and normalize a JSON config, or return defaults if absent."""
    if not os.path.exists(path):
        return normalize_config({}, platform=platform)
    with open(path, "r", encoding="utf-8") as config_file:
        return normalize_config(json.load(config_file), platform=platform)


def save_config(path, shortcuts, settings):
    """Atomically save without canonicalizing unrelated shortcut records."""
    data = normalize_config({"shortcuts": shortcuts, "settings": settings})
    data["shortcuts"] = deepcopy(shortcuts)
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


def normalize_action_input(
    action=None, name="", action_mode=ACTION_MODE_COMMAND_LINE, command="",
    program_path="", arguments="", start_in="", color="",
):
    """Return one validated, detached action using only current action fields."""
    source = action if isinstance(action, dict) else {}
    raw_name = source.get("name", name)
    clean_name = raw_name.strip() if isinstance(raw_name, str) else ""
    mode = source.get("action_mode", action_mode)
    clean_command = _normalize_newlines(
        source.get("command", command) if isinstance(source.get("command", command), str) else ""
    ).strip()
    clean_start = source.get("start_in", start_in)
    clean_start = clean_start.strip() if isinstance(clean_start, str) else ""
    clean_program = source.get("program_path", program_path)
    clean_program = clean_program.strip() if isinstance(clean_program, str) else ""
    clean_arguments = source.get("arguments", arguments)
    clean_arguments = _normalize_newlines(clean_arguments).strip() if isinstance(clean_arguments, str) else ""
    clean_color = normalize_shortcut_color(source.get("color", color))
    if not clean_name:
        raise ValidationError("Enter an action name.", "name")
    if mode == ACTION_MODE_PROGRAM:
        if not clean_program:
            raise ValidationError("Enter a program or script to run.", "program_path")
        values = {
            "name": clean_name, "action_mode": ACTION_MODE_PROGRAM,
            "program_path": clean_program, "arguments": clean_arguments,
            "start_in": clean_start,
        }
        if clean_color:
            values["color"] = clean_color
        return values
    if mode != ACTION_MODE_COMMAND_LINE:
        raise ValidationError("Choose a supported action type.", "action_mode")
    if not clean_command:
        raise ValidationError("Enter a command to run.", "command")
    values = {
        "name": clean_name, "action_mode": ACTION_MODE_COMMAND_LINE,
        "command": clean_command, "start_in": clean_start,
    }
    if clean_color:
        values["color"] = clean_color
    return values


def shortcut_execution_mode(shortcut):
    """Return a valid execution mode, defaulting legacy values to sequential."""
    if isinstance(shortcut, dict) and shortcut.get("execution_mode") == EXECUTION_MODE_PARALLEL:
        return EXECUTION_MODE_PARALLEL
    return EXECUTION_MODE_SEQUENTIAL


def shortcut_actions(shortcut):
    """Return validated detached actions, lazily projecting one legacy action."""
    if not isinstance(shortcut, dict):
        raise ValidationError("Shortcut data must be an object.", "actions")
    if "actions" not in shortcut:
        legacy = {
            "name": str(shortcut.get("name", "")).strip(),
            "action_mode": shortcut_action_mode(shortcut),
            "start_in": shortcut.get("start_in", ""),
        }
        if legacy["action_mode"] == ACTION_MODE_PROGRAM:
            legacy.update({
                "program_path": shortcut.get("program_path", ""),
                "arguments": shortcut.get("arguments", ""),
            })
        else:
            legacy["command"] = shortcut.get("command", "")
        legacy["color"] = shortcut.get("color", "")
        return [normalize_action_input(legacy)]
    actions = shortcut.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValidationError("Add at least one action.", "actions")
    normalized = []
    legacy_color = normalize_shortcut_color(shortcut.get("color", ""))
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValidationError(
                f"Action {index + 1} must be an object.", f"actions[{index}]",
            )
        try:
            normalized_action = normalize_action_input(action)
            if legacy_color and "color" not in normalized_action:
                normalized_action["color"] = legacy_color
            normalized.append(normalized_action)
        except ValidationError as error:
            raise ValidationError(
                f"Action {index + 1}: {error}", f"actions[{index}].{error.field or 'action'}",
            ) from error
    return normalized


def first_action_color(shortcut):
    """Return the first valid projected action color in execution order."""
    for action in shortcut_actions(shortcut):
        color = normalize_shortcut_color(action.get("color", ""))
        if color:
            return color
    return ""


def normalize_shortcut_collection(raw):
    """Validate and detach an imported shortcut collection without saving it."""
    if isinstance(raw, dict):
        if "shortcuts" not in raw:
            raise ConfigError("The import file must contain a 'shortcuts' list.")
        shortcuts = raw.get("shortcuts")
    elif isinstance(raw, list):
        shortcuts = raw
    else:
        raise ConfigError("The import file must be an object or a shortcut list.")
    normalized = normalize_config({"shortcuts": shortcuts, "settings": {}})["shortcuts"]
    for index, shortcut in enumerate(normalized):
        name = shortcut.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"Shortcut {index + 1} must have a name.")
        try:
            shortcut_actions(shortcut)
        except ValidationError as error:
            raise ConfigError(f"Shortcut {index + 1} ({name.strip()}): {error}") from error
    return normalized


def normalize_shortcut_input(
    name, command="", start_in="", action_mode=ACTION_MODE_COMMAND_LINE,
    program_path="", arguments="", folder=GENERAL_FOLDER, color="",
    execution_mode=EXECUTION_MODE_SEQUENTIAL, actions=None, existing=None,
):
    """Normalize shortcut fields; ``actions`` opts into the current schema."""
    clean_name = name.strip() if isinstance(name, str) else ""
    clean_command = _normalize_newlines(command).strip() if isinstance(command, str) else ""
    clean_start = start_in.strip() if isinstance(start_in, str) else ""
    clean_program = program_path.strip() if isinstance(program_path, str) else ""
    clean_arguments = _normalize_newlines(arguments).strip() if isinstance(arguments, str) else ""
    clean_folder = normalize_folder(folder)
    clean_color = normalize_shortcut_color(color)
    if not clean_name:
        raise ValidationError("Enter a shortcut name.", "name")
    if actions is not None:
        if execution_mode not in (EXECUTION_MODE_SEQUENTIAL, EXECUTION_MODE_PARALLEL):
            raise ValidationError("Choose a supported execution mode.", "execution_mode")
        if not isinstance(actions, list) or not actions:
            raise ValidationError("Add at least one action.", "actions")
        normalized_actions = []
        legacy_color = normalize_shortcut_color(color)
        if not legacy_color and isinstance(existing, dict):
            legacy_color = normalize_shortcut_color(existing.get("color", ""))
        for index, action in enumerate(actions):
            try:
                normalized_action = normalize_action_input(action)
                if legacy_color and "color" not in normalized_action:
                    normalized_action["color"] = legacy_color
                normalized_actions.append(normalized_action)
            except ValidationError as error:
                raise ValidationError(
                    f"Action {index + 1}: {error}",
                    f"actions[{index}].{error.field or 'action'}",
                ) from error
        values = deepcopy(existing) if isinstance(existing, dict) else {}
        for key in (
            "action_mode", "command", "program_path", "arguments", "start_in",
            "name", "folder", "color", "actions", "execution_mode",
        ):
            values.pop(key, None)
        values.update({
            "name": clean_name, "folder": clean_folder,
            "execution_mode": execution_mode, "actions": normalized_actions,
        })
        return values
    if action_mode == ACTION_MODE_PROGRAM:
        if not clean_program:
            raise ValidationError("Enter a program or script to run.", "program_path")
        values = {
            "name": clean_name, "action_mode": ACTION_MODE_PROGRAM,
            "program_path": clean_program, "arguments": clean_arguments,
            "start_in": clean_start, "folder": clean_folder,
        }
        if clean_color:
            values["color"] = clean_color
        return values
    if action_mode != ACTION_MODE_COMMAND_LINE:
        raise ValidationError("Choose a supported action type.", "action_mode")
    if not clean_command:
        raise ValidationError("Enter a command to run.", "command")
    values = {
        "name": clean_name, "action_mode": ACTION_MODE_COMMAND_LINE,
        "command": clean_command, "start_in": clean_start, "folder": clean_folder,
    }
    if clean_color:
        values["color"] = clean_color
    return values


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


def action_preview(action):
    """Return a bounded type-relevant preview for one action."""
    if shortcut_action_mode(action) == ACTION_MODE_PROGRAM:
        return command_preview(shortcut_command(action))
    return command_preview(action.get("command", ""))


def shortcut_actions_preview(shortcut, limit=3):
    """Summarize ordered action names without flattening their commands."""
    actions = shortcut_actions(shortcut)
    count = max(1, int(limit))
    lines = [
        f"{index + 1}. {action['name']} ({'Program' if shortcut_action_mode(action) == ACTION_MODE_PROGRAM else 'Command'})"
        for index, action in enumerate(actions[:count])
    ]
    if len(actions) > count:
        lines.append(f"+{len(actions) - count} more")
    return "\n".join(lines)


def _task_scheduler_root(name):
    """Build the common Task Scheduler document around its Actions element."""
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
    return root, ET.SubElement(root, tag("Actions"), {"Context": "Author"}), tag


def _task_action_id(name, index, used):
    clean = "_".join(str(name).strip().split())
    clean = "".join(character for character in clean if character.isalnum() or character in "_.-")
    if not clean or not (clean[0].isalpha() or clean[0] == "_"):
        clean = f"Action_{index + 1}"
    candidate = clean
    suffix = 2
    while candidate in used:
        candidate = f"{clean}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def build_task_scheduler_shortcut_xml(name, actions):
    """Build Task Scheduler XML containing every FlashCMD action in order."""
    if not isinstance(actions, (list, tuple)) or not actions:
        raise TaskSchedulerError("Task Scheduler export requires at least one action.")
    root, actions_element, tag = _task_scheduler_root(name)
    used_ids = set()
    for index, raw_action in enumerate(actions):
        try:
            action = normalize_action_input(raw_action)
        except ValidationError as error:
            raise TaskSchedulerError(f"Action {index + 1}: {error}") from error
        execute = ET.SubElement(actions_element, tag("Exec"), {
            "id": _task_action_id(action["name"], index, used_ids),
        })
        if shortcut_action_mode(action) == ACTION_MODE_PROGRAM:
            command = action["program_path"]
            arguments = action.get("arguments", "")
        else:
            command = "cmd.exe"
            arguments = subprocess.list2cmdline(["/d", "/c", action["command"]])
        ET.SubElement(execute, tag("Command")).text = command
        if arguments:
            ET.SubElement(execute, tag("Arguments")).text = arguments
        if action.get("start_in"):
            ET.SubElement(execute, tag("WorkingDirectory")).text = action["start_in"]
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_task_scheduler_xml(name, program_path, arguments="", working_directory=""):
    """Backward-compatible single Program/Script Task Scheduler export."""
    return build_task_scheduler_shortcut_xml(name, [{
        "name": str(name).strip() or "Action 1",
        "action_mode": ACTION_MODE_PROGRAM,
        "program_path": program_path, "arguments": arguments,
        "start_in": working_directory,
    }])


def _parse_task_scheduler_document(xml_text):
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
    return root, local_name


def parse_task_scheduler_shortcut_xml(xml_text):
    """Parse every Task Scheduler Exec action into one shortcut projection."""
    root, local_name = _parse_task_scheduler_document(xml_text)
    execute_elements = [element for element in root.iter() if local_name(element) == "Exec"]
    if not execute_elements:
        raise TaskSchedulerError("Task Scheduler XML must contain at least one Exec action.")
    descriptions = [
        (element.text or "").strip() for element in root.iter()
        if local_name(element) == "Description" and (element.text or "").strip()
    ]
    actions = []
    for index, execute in enumerate(execute_elements):
        values = {local_name(child): (child.text or "").strip() for child in execute}
        if not values.get("Command"):
            raise TaskSchedulerError(
                f"Task Scheduler Exec action {index + 1} has no Command.",
            )
        actions.append({
            "name": execute.get("id") or execute.get("Id") or f"Action {index + 1}",
            "action_mode": ACTION_MODE_PROGRAM,
            "program_path": values["Command"],
            "arguments": values.get("Arguments", ""),
            "start_in": values.get("WorkingDirectory", ""),
        })
    return {"name": descriptions[0] if descriptions else "", "actions": actions}


def parse_task_scheduler_xml(xml_text):
    """Parse one Task Scheduler Exec action into FlashCMD program fields."""
    root, local_name = _parse_task_scheduler_document(xml_text)
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
    fields = ("name", "command", "program_path", "arguments", "start_in", "action_mode")
    result = []
    for index, shortcut in pairs:
        values = [shortcut.get(field, "") for field in fields]
        values.append(shortcut_folder(shortcut))
        try:
            for action in shortcut_actions(shortcut):
                values.extend(action.get(field, "") for field in fields)
        except ValidationError:
            pass
        if any(needle in str(value).casefold() for value in values):
            result.append((index, shortcut))
    return result


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
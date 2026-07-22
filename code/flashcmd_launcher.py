"""Narrow native launch abstraction for FlashCMD shortcuts."""

from dataclasses import dataclass
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from quickcmd_core import (
    ACTION_MODE_PROGRAM,
    EXECUTION_MODE_PARALLEL,
    EXECUTION_MODE_SEQUENTIAL,
    build_batch_script,
    build_terminal_argv,
    current_platform,
    normalize_shortcut_color,
    shortcut_action_mode,
)


MACOS_TERMINAL_APPLESCRIPT = """on run argv
    set terminalCommand to item 1 of argv
    tell application \"Terminal\"
        activate
        do script terminalCommand
    end tell
end run"""
WINDOWS_TERMINAL_BATCH_CLEANUP_DELAY = 5
DEFAULT_START_TIMEOUT = 10.0
RUN_DIRECTORY_PREFIX = "flashcmd-run-"
STALE_RUN_AGE_SECONDS = 7 * 24 * 60 * 60

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_LAUNCH_ERROR = "launch_error"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"


@dataclass(frozen=True)
class ActionResult:
    index: int
    name: str
    status: str
    exit_code: int | None = None
    detail: str = ""

    @property
    def succeeded(self):
        return self.status == STATUS_SUCCESS


@dataclass(frozen=True)
class ProgressEvent:
    run_id: str
    phase: str
    completed: int
    total: int
    action_index: int | None = None
    action_name: str = ""


@dataclass(frozen=True)
class RunResult:
    run_id: str
    execution_mode: str
    actions: tuple[ActionResult, ...]
    fallback_used: bool = False
    fallback_detail: str = ""
    cancelled: bool = False

    @property
    def success(self):
        return bool(self.actions) and all(action.succeeded for action in self.actions)

    @property
    def failures(self):
        return tuple(action for action in self.actions if not action.succeeded)


@dataclass
class _PreparedCommand:
    index: int
    action: dict
    payload_path: str
    wrapper_path: str
    started_path: str
    temporary_result_path: str
    result_path: str
    nonce: str
    process: object = None
    accepted: bool = False


def build_macos_terminal_command(shell_path, command, start_in):
    """Build the shell command passed as one opaque osascript argument."""
    shell = shlex.quote(os.fspath(shell_path))
    pieces = []
    if start_in:
        pieces.append(f"cd -- {shlex.quote(os.fspath(start_in))}")
    pieces.append(f"{shell} -lc {shlex.quote(command)}")
    pieces.append(f"exec {shell} -il")
    return "; ".join(pieces)


def build_macos_terminal_argv(shell_path, command, start_in):
    """Build static AppleScript invocation without source interpolation."""
    terminal_command = build_macos_terminal_command(shell_path, command, start_in)
    return ["/usr/bin/osascript", "-e", MACOS_TERMINAL_APPLESCRIPT, terminal_command]


def _cleanup_after_process(process, batch_path, delay=0):
    try:
        process.wait()
        if delay:
            time.sleep(delay)
    finally:
        try:
            os.remove(batch_path)
        except OSError:
            pass


def _is_windows_terminal(path):
    return os.path.basename(os.fspath(path)).casefold() in ("wt", "wt.exe")


def build_windows_terminal_argv(
    windows_terminal_path, shell_path, batch_path, title="", color="", start_in="",
    window_id="",
):
    """Build a Windows Terminal new-tab command using opaque arguments."""
    argv = [os.fspath(windows_terminal_path)]
    if window_id:
        argv.extend(("--window", str(window_id)))
    argv.append("new-tab")
    if start_in:
        argv.extend(("--startingDirectory", os.fspath(start_in)))
    if title:
        argv.extend(("--title", str(title), "--suppressApplicationTitle"))
    if color:
        argv.extend(("--tabColor", str(color)))
    argv.extend(build_terminal_argv(shell_path, batch_path))
    return argv


def _windows_tab_argv(wrapper):
    argv = ["new-tab"]
    start_in = wrapper.action.get("start_in", "")
    if start_in:
        argv.extend(("--startingDirectory", os.fspath(start_in)))
    name = wrapper.action.get("name", "")
    if name:
        argv.extend(("--title", str(name), "--suppressApplicationTitle"))
    color = normalize_shortcut_color(wrapper.action.get("color", ""))
    if color:
        argv.extend(("--tabColor", color))
    argv.extend(("cmd.exe", "/d", "/c", wrapper.wrapper_path))
    return argv


def build_compound_windows_terminal_argv(windows_terminal_path, window_id, wrappers):
    """Build one WT invocation containing one opaque tab command per wrapper."""
    argv = [os.fspath(windows_terminal_path), "--window", str(window_id)]
    for position, wrapper in enumerate(wrappers):
        if position:
            argv.append(";")
        argv.extend(_windows_tab_argv(wrapper))
    return argv


def _launch_windows(terminal_path, command, start_in, title="", color=""):
    batch_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False, encoding="utf-8",
        ) as batch_file:
            batch_file.write(build_batch_script(command))
            batch_path = batch_file.name
        configured_terminal = os.fspath(terminal_path)
        configured_is_wt = _is_windows_terminal(configured_terminal)
        windows_terminal = configured_terminal if configured_is_wt else shutil.which("wt.exe")
        shell_path = "cmd.exe" if configured_is_wt else configured_terminal
        cleanup_delay = 0
        if windows_terminal:
            try:
                process = subprocess.Popen(
                    build_windows_terminal_argv(
                        windows_terminal, shell_path, batch_path, title, color, start_in,
                    ),
                    shell=False, cwd=start_in or None,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                cleanup_delay = WINDOWS_TERMINAL_BATCH_CLEANUP_DELAY
            except OSError:
                process = subprocess.Popen(
                    build_terminal_argv(shell_path, batch_path), shell=False,
                    cwd=start_in or None,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
        else:
            process = subprocess.Popen(
                build_terminal_argv(shell_path, batch_path), shell=False,
                cwd=start_in or None,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        threading.Thread(
            target=_cleanup_after_process,
            args=(process, batch_path, cleanup_delay) if cleanup_delay else (process, batch_path),
            daemon=True,
        ).start()
        return process
    except Exception:
        if batch_path:
            try:
                os.remove(batch_path)
            except OSError:
                pass
        raise


def _launch_macos(shell_path, command, start_in):
    return subprocess.Popen(
        build_macos_terminal_argv(shell_path, command, start_in), shell=False,
    )


def launch_program(program_path, arguments="", start_in="", platform=None):
    """Launch a Program/Script action directly without opening a terminal."""
    system = current_platform(platform)
    program = os.fspath(program_path)
    if system == "windows":
        command_line = subprocess.list2cmdline([program])
        if arguments.strip():
            command_line = f"{command_line} {arguments.strip()}"
        return subprocess.Popen(
            command_line, shell=False, cwd=start_in or None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if system == "macos":
        argv = [program, *shlex.split(arguments)]
        return subprocess.Popen(argv, shell=False, cwd=start_in or None)
    raise NotImplementedError(f"FlashCMD program launching is unsupported on {system}.")


def _launch_legacy_shortcut(terminal_path, command, start_in="", platform=None, title="", color=""):
    """Compatibility launcher for the historical single-command API."""
    system = current_platform(platform)
    if system == "windows":
        return _launch_windows(terminal_path, command, start_in, title, color)
    if system == "macos":
        return _launch_macos(terminal_path, command, start_in)
    raise NotImplementedError(f"FlashCMD command launching is unsupported on {system}.")


def _write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as output:
        output.write(text)


def _windows_child_argv(shell_path, payload_path):
    base = os.path.basename(os.fspath(shell_path)).casefold()
    if base in ("cmd", "cmd.exe"):
        return [os.fspath(shell_path), "/d", "/c", os.fspath(payload_path)]
    if base in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        return [os.fspath(shell_path), "-NoLogo", "-NoProfile", "-File", os.fspath(payload_path)]
    return [os.fspath(shell_path), os.fspath(payload_path)]


def _prepare_command(run_directory, index, action, system, shell_path):
    stem = f"action-{index:03d}"
    nonce = uuid.uuid4().hex
    started = os.path.join(run_directory, stem + ".started")
    temporary = os.path.join(run_directory, stem + ".result.tmp")
    result = os.path.join(run_directory, stem + ".result")
    if system == "windows":
        shell_base = os.path.basename(os.fspath(shell_path)).casefold()
        if shell_base in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
            payload_suffix = ".ps1"
        elif shell_base in ("cmd", "cmd.exe"):
            payload_suffix = ".bat"
        else:
            payload_suffix = ".script"
        payload = os.path.join(run_directory, stem + ".payload" + payload_suffix)
        wrapper = os.path.join(run_directory, stem + ".wrapper.bat")
        command = str(action.get("command", "")).replace("\r\n", "\n").replace("\r", "\n")
        _write_text(
            payload,
            build_batch_script(command) if payload_suffix == ".bat" else command + "\n",
        )
        child = subprocess.list2cmdline(_windows_child_argv(shell_path, payload))
        if shell_base in ("cmd", "cmd.exe"):
            interactive = subprocess.list2cmdline([os.fspath(shell_path), "/k"])
        elif shell_base in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
            interactive = subprocess.list2cmdline([os.fspath(shell_path), "-NoExit"])
        else:
            interactive = subprocess.list2cmdline([os.fspath(shell_path)])
        body = (
            "@echo off\n"
            f">{subprocess.list2cmdline([started])} echo {nonce}\n"
            f"{child}\nset \"flashcmd_code=%errorlevel%\"\n"
            f">{subprocess.list2cmdline([temporary])} echo {nonce} %flashcmd_code%\n"
            f"move /y {subprocess.list2cmdline([temporary])} {subprocess.list2cmdline([result])} >nul\n"
            f"{interactive}\n"
        )
    else:
        payload = os.path.join(run_directory, stem + ".payload.sh")
        wrapper = os.path.join(run_directory, stem + ".wrapper.sh")
        command = str(action.get("command", "")).replace("\r\n", "\n").replace("\r", "\n")
        _write_text(payload, command + "\n")
        body = (
            "#!/bin/sh\n"
            f"printf '%s\\n' {shlex.quote(nonce)} > {shlex.quote(started)}\n"
            f"{shlex.quote(os.fspath(shell_path))} {shlex.quote(payload)}\n"
            "flashcmd_code=$?\n"
            f"printf '%s %s\\n' {shlex.quote(nonce)} \"$flashcmd_code\" > {shlex.quote(temporary)}\n"
            f"mv -f {shlex.quote(temporary)} {shlex.quote(result)}\n"
            f"exec {shlex.quote(os.fspath(shell_path))} -il\n"
        )
    _write_text(wrapper, body)
    return _PreparedCommand(
        index, action, payload, wrapper, started, temporary, result, nonce,
    )


def parse_result_marker(path, expected_nonce):
    """Return a signed marker exit code, or None for missing/malformed data."""
    try:
        with open(path, "r", encoding="utf-8") as marker:
            parts = marker.read().strip().split()
    except OSError:
        return None
    if len(parts) != 2 or parts[0] != expected_nonce:
        return None
    value = parts[1]
    digits = value[1:] if value.startswith(("+", "-")) else value
    return int(value) if digits.isdigit() else None


def _started(prepared):
    try:
        with open(prepared.started_path, "r", encoding="utf-8") as marker:
            return marker.read().strip() == prepared.nonce
    except OSError:
        return False


def _cancelled_result(prepared):
    return ActionResult(
        prepared.index, prepared.action.get("name", ""), STATUS_CANCELLED,
        detail="Monitoring cancelled.",
    )


def _monitor_command(prepared, cancel_event, start_timeout, completion_timeout=None):
    started_at = time.monotonic()
    while not _started(prepared):
        if cancel_event and cancel_event.is_set():
            return _cancelled_result(prepared)
        if time.monotonic() - started_at >= start_timeout:
            return ActionResult(
                prepared.index, prepared.action.get("name", ""), STATUS_TIMEOUT,
                detail="The terminal accepted the launch, but the action did not start in time.",
            )
        if prepared.process is not None and prepared.process.poll() is not None and not prepared.accepted:
            return ActionResult(
                prepared.index, prepared.action.get("name", ""), STATUS_LAUNCH_ERROR,
                detail="The command host exited before the action started.",
            )
        time.sleep(0.02)
    completion_started = time.monotonic()
    while True:
        code = parse_result_marker(prepared.result_path, prepared.nonce)
        if code is not None:
            return ActionResult(
                prepared.index, prepared.action.get("name", ""),
                STATUS_SUCCESS if code == 0 else STATUS_FAILED, code,
                "" if code == 0 else f"Exited with code {code}.",
            )
        if cancel_event and cancel_event.is_set():
            return _cancelled_result(prepared)
        if completion_timeout is not None and time.monotonic() - completion_started >= completion_timeout:
            return ActionResult(
                prepared.index, prepared.action.get("name", ""), STATUS_TIMEOUT,
                detail="The action did not finish in time.",
            )
        time.sleep(0.02)


def _wait_program(index, action, process, cancel_event, completion_timeout=None):
    started = time.monotonic()
    while process.poll() is None:
        if cancel_event and cancel_event.is_set():
            return ActionResult(
                index, action.get("name", ""), STATUS_CANCELLED,
                detail="Monitoring cancelled; the program was left running.",
            )
        if completion_timeout is not None and time.monotonic() - started >= completion_timeout:
            return ActionResult(
                index, action.get("name", ""), STATUS_TIMEOUT,
                detail="The program did not finish in time.",
            )
        time.sleep(0.02)
    code = process.returncode
    return ActionResult(
        index, action.get("name", ""), STATUS_SUCCESS if code == 0 else STATUS_FAILED,
        code, "" if code == 0 else f"Exited with code {code}.",
    )


def _launch_program_action(index, action, system):
    start_in = action.get("start_in", "")
    if start_in and not os.path.isdir(start_in):
        return None, ActionResult(
            index, action.get("name", ""), STATUS_LAUNCH_ERROR,
            detail=f"Start folder does not exist: {start_in}",
        )
    try:
        process = launch_program(
            action.get("program_path", ""), action.get("arguments", ""),
            start_in, platform=system,
        )
        return process, None
    except Exception as error:
        return None, ActionResult(
            index, action.get("name", ""), STATUS_LAUNCH_ERROR, detail=str(error),
        )


def _cleanup_run_directory(path, grace=0.1, retries=4):
    time.sleep(grace)
    for attempt in range(retries):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if attempt + 1 < retries:
                time.sleep(0.05 * (attempt + 1))
    return False


def cleanup_stale_run_directories(temp_root=None, now=None, max_age=STALE_RUN_AGE_SECONDS):
    """Delete only old, strictly prefixed FlashCMD run directories."""
    root = os.fspath(temp_root or tempfile.gettempdir())
    cutoff = (time.time() if now is None else now) - max_age
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    removed = 0
    for name in names:
        path = os.path.join(root, name)
        if not name.startswith(RUN_DIRECTORY_PREFIX) or not os.path.isdir(path):
            continue
        try:
            old = os.path.getmtime(path) < cutoff
        except OSError:
            continue
        if old and _cleanup_run_directory(path, grace=0):
            removed += 1
    return removed


def _notify(callback, run_id, phase, completed, total, index=None, name=""):
    if callback:
        callback(ProgressEvent(run_id, phase, completed, total, index, name))


def _result_for_launch_error(index, action, error):
    return ActionResult(index, action.get("name", ""), STATUS_LAUNCH_ERROR, detail=str(error))


def _shell_and_windows_terminal(terminal_path):
    configured = os.fspath(terminal_path)
    if _is_windows_terminal(configured):
        return "cmd.exe", configured
    return configured, shutil.which("wt.exe")


def _launch_fallback_command(item):
    item.process = subprocess.Popen(
        ["cmd.exe", "/d", "/c", item.wrapper_path], shell=False,
        cwd=item.action.get("start_in", "") or None,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def _launch_macos_command(item, shell_path):
    wrapper_command = " ".join((
        shlex.quote(os.fspath(shell_path)), shlex.quote(item.wrapper_path),
    ))
    item.process = subprocess.Popen(
        build_macos_terminal_argv(
            shell_path, wrapper_command,
            item.action.get("start_in", ""),
        ),
        shell=False,
    )
    item.accepted = True


def _parallel_commands(commands, system, shell_path, windows_terminal, window_id):
    """Launch prepared commands and return fallback metadata plus launch errors."""
    errors = {}
    fallback_used = False
    fallback_detail = ""
    if not commands:
        return errors, fallback_used, fallback_detail
    try:
        if system == "windows" and windows_terminal:
            process = subprocess.Popen(
                build_compound_windows_terminal_argv(
                    windows_terminal, window_id, commands,
                ),
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for item in commands:
                item.process, item.accepted = process, True
        elif system == "windows":
            raise FileNotFoundError("Windows Terminal is unavailable.")
        else:
            for item in commands:
                _launch_macos_command(item, shell_path)
    except OSError as error:
        if system != "windows":
            for item in commands:
                errors[item.index] = _result_for_launch_error(item.index, item.action, error)
            return errors, fallback_used, fallback_detail
        fallback_used = True
        fallback_detail = (
            "Windows Terminal features are unavailable; commands opened in "
            "separate console windows."
        )
        for item in commands:
            try:
                _launch_fallback_command(item)
            except OSError as fallback_error:
                errors[item.index] = _result_for_launch_error(
                    item.index, item.action, fallback_error,
                )
    return errors, fallback_used, fallback_detail


def _run_parallel(
    action_list, prepared, results, system, shell_path, windows_terminal,
    window_id, cancel_event, start_timeout, completion_timeout,
    on_progress, identifier,
):
    errors, fallback_used, fallback_detail = _parallel_commands(
        list(prepared.values()), system, shell_path, windows_terminal,
        window_id,
    )
    results.update(errors)
    programs = {}
    for index, action in enumerate(action_list):
        if index in results or shortcut_action_mode(action) != ACTION_MODE_PROGRAM:
            continue
        process, error_result = _launch_program_action(index, action, system)
        if error_result:
            results[index] = error_result
        else:
            programs[index] = (action, process)
    total = len(action_list)
    completed = queue.Queue()
    monitors = []

    def monitor(index, callback, arguments):
        completed.put((index, callback(*arguments)))

    for index, item in prepared.items():
        if index not in results:
            monitors.append(threading.Thread(
                target=monitor,
                args=(index, _monitor_command, (
                    item, cancel_event, start_timeout, completion_timeout,
                )),
                daemon=True,
            ))
    for index, (action, process) in programs.items():
        monitors.append(threading.Thread(
            target=monitor,
            args=(index, _wait_program, (
                index, action, process, cancel_event, completion_timeout,
            )),
            daemon=True,
        ))
    for thread in monitors:
        thread.start()
    for _thread in monitors:
        index, action_result = completed.get()
        results[index] = action_result
        _notify(
            on_progress, identifier, "running", len(results), total,
            index, action_list[index].get("name", ""),
        )
    return fallback_used, fallback_detail


def _run_sequential(
    action_list, prepared, results, system, shell_path, windows_terminal,
    window_id, cancel_event, start_timeout, completion_timeout,
    on_progress, identifier,
):
    fallback_used = system == "windows" and not windows_terminal
    fallback_detail = (
        "Windows Terminal features are unavailable; commands opened in separate "
        "console windows."
        if fallback_used else ""
    )
    force_fallback = fallback_used
    wt_accepted = False
    total = len(action_list)
    for index, action in enumerate(action_list):
        if index in results:
            continue
        if cancel_event.is_set():
            results[index] = ActionResult(
                index, action.get("name", ""), STATUS_CANCELLED,
                detail="Run cancelled before launch.",
            )
        elif shortcut_action_mode(action) == ACTION_MODE_PROGRAM:
            process, error_result = _launch_program_action(index, action, system)
            results[index] = error_result or _wait_program(
                index, action, process, cancel_event, completion_timeout,
            )
        else:
            item = prepared[index]
            try:
                if system == "windows" and not force_fallback:
                    item.process = subprocess.Popen(
                        build_windows_terminal_argv(
                            windows_terminal, "cmd.exe", item.wrapper_path,
                            action.get("name", ""),
                            normalize_shortcut_color(action.get("color", "")),
                            action.get("start_in", ""), window_id,
                        ),
                        shell=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    item.accepted = True
                    wt_accepted = True
                elif system == "windows":
                    _launch_fallback_command(item)
                else:
                    _launch_macos_command(item, shell_path)
                results[index] = _monitor_command(
                    item, cancel_event, start_timeout, completion_timeout,
                )
            except OSError as error:
                if system == "windows" and not wt_accepted and not force_fallback:
                    force_fallback = fallback_used = True
                    fallback_detail = (
                        "Windows Terminal features are unavailable; commands opened "
                        "in separate console windows."
                    )
                    try:
                        _launch_fallback_command(item)
                        results[index] = _monitor_command(
                            item, cancel_event, start_timeout, completion_timeout,
                        )
                    except OSError as fallback_error:
                        results[index] = _result_for_launch_error(
                            index, action, fallback_error,
                        )
                else:
                    results[index] = _result_for_launch_error(index, action, error)
        _notify(
            on_progress, identifier, "running", len(results), total,
            index, action.get("name", ""),
        )
    return fallback_used, fallback_detail


def launch_shortcut(
    terminal_path, actions, execution_mode=EXECUTION_MODE_SEQUENTIAL,
    platform=None, color="", run_id=None, cancel_event=None,
    on_progress=None, start_timeout=DEFAULT_START_TIMEOUT,
    completion_timeout=None, title="",
):
    """Synchronously orchestrate named actions and return an immutable RunResult.

    Passing a command string retains the historical asynchronous single-action API.
    """
    if isinstance(actions, str):
        start_in = (
            execution_mode
            if execution_mode not in (
                EXECUTION_MODE_SEQUENTIAL, EXECUTION_MODE_PARALLEL,
            )
            else ""
        )
        return _launch_legacy_shortcut(
            terminal_path, actions, start_in, platform, title, color,
        )
    system = current_platform(platform)
    if system not in ("windows", "macos"):
        raise NotImplementedError(
            f"FlashCMD command launching is unsupported on {system}.",
        )
    if execution_mode not in (EXECUTION_MODE_SEQUENTIAL, EXECUTION_MODE_PARALLEL):
        execution_mode = EXECUTION_MODE_SEQUENTIAL
    if not isinstance(actions, (list, tuple)) or not actions:
        raise ValueError("A shortcut run requires at least one action.")
    if any(not isinstance(action, dict) for action in actions):
        raise ValueError("Every shortcut action must be an object.")
    action_list = [dict(action) for action in actions]
    identifier = str(run_id or uuid.uuid4().hex)
    window_id = f"flashcmd-{identifier.replace('-', '')}"
    cancel_event = cancel_event or threading.Event()
    cleanup_stale_run_directories()
    run_directory = tempfile.mkdtemp(prefix=RUN_DIRECTORY_PREFIX)
    total = len(action_list)
    results = {}
    if system == "windows":
        shell_path, windows_terminal = _shell_and_windows_terminal(terminal_path)
    else:
        shell_path, windows_terminal = os.fspath(terminal_path), None
    prepared = {}
    try:
        for index, action in enumerate(action_list):
            start_in = action.get("start_in", "")
            if start_in and not os.path.isdir(start_in):
                results[index] = ActionResult(
                    index, action.get("name", ""), STATUS_LAUNCH_ERROR,
                    detail=f"Start folder does not exist: {start_in}",
                )
            elif shortcut_action_mode(action) != ACTION_MODE_PROGRAM:
                prepared[index] = _prepare_command(
                    run_directory, index, action, system, shell_path,
                )
        _notify(on_progress, identifier, "launching", 0, total)
        run_arguments = (
            action_list, prepared, results, system, shell_path,
            windows_terminal, window_id, cancel_event, start_timeout,
            completion_timeout, on_progress, identifier,
        )
        if execution_mode == EXECUTION_MODE_PARALLEL:
            fallback_used, fallback_detail = _run_parallel(*run_arguments)
        else:
            fallback_used, fallback_detail = _run_sequential(*run_arguments)
        ordered = tuple(
            results.get(
                index,
                ActionResult(
                    index, action.get("name", ""), STATUS_CANCELLED,
                    detail="Run did not complete.",
                ),
            )
            for index, action in enumerate(action_list)
        )
        result = RunResult(
            identifier, execution_mode, ordered, fallback_used,
            fallback_detail, cancel_event.is_set(),
        )
        _notify(on_progress, identifier, "completed", len(ordered), total)
        return result
    finally:
        _cleanup_run_directory(run_directory)
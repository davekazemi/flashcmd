"""Narrow native launch abstraction for FlashCMD shortcuts."""

import os
import shlex
import subprocess
import tempfile
import threading

from quickcmd_core import build_batch_script, build_terminal_argv, current_platform


MACOS_TERMINAL_APPLESCRIPT = """on run argv
    set terminalCommand to item 1 of argv
    tell application \"Terminal\"
        activate
        do script terminalCommand
    end tell
end run"""


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


def _cleanup_after_process(process, batch_path):
    try:
        process.wait()
    finally:
        try:
            os.remove(batch_path)
        except OSError:
            pass


def _launch_windows(terminal_path, command, start_in):
    batch_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False, encoding="utf-8",
        ) as batch_file:
            batch_file.write(build_batch_script(command))
            batch_path = batch_file.name
        process = subprocess.Popen(
            build_terminal_argv(terminal_path, batch_path), shell=False,
            cwd=start_in or None,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        threading.Thread(
            target=_cleanup_after_process, args=(process, batch_path), daemon=True,
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


def launch_shortcut(terminal_path, command, start_in="", platform=None):
    """Launch a shortcut with native behavior and return the host process."""
    system = current_platform(platform)
    if system == "windows":
        return _launch_windows(terminal_path, command, start_in)
    if system == "macos":
        return _launch_macos(terminal_path, command, start_in)
    raise NotImplementedError(f"FlashCMD command launching is unsupported on {system}.")
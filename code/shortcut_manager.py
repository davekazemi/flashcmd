import sys

from flashcmd_version import APP_NAME, __version__


if __name__ == "__main__" and sys.argv[1:] == ["--version"]:
    if sys.stdout is not None:
        print(f"{APP_NAME} {__version__}")
    raise SystemExit(0)


from json import JSONDecodeError
from copy import deepcopy
import hashlib
import importlib
import json
import ntpath
import os
import posixpath
import queue
import shutil
import socket
import threading
import tkinter as tk
import uuid
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

if sys.platform == "win32":
    import ctypes
    import pystray
else:
    ctypes = pystray = None

from flashcmd_launcher import launch_program, launch_shortcut
from quickcmd_core import (
    ACTION_MODE_COMMAND_LINE,
    ACTION_MODE_PROGRAM,
    ConfigError,
    DEFAULT_SETTINGS,
    EXECUTION_MODE_PARALLEL,
    EXECUTION_MODE_SEQUENTIAL,
    GENERAL_FOLDER,
    TaskSchedulerError,
    ValidationError,
    build_task_scheduler_shortcut_xml,
    build_task_scheduler_xml,
    command_preview,
    current_platform,
    executable_base_dir,
    filter_shortcuts,
    first_action_color,
    legacy_config_candidates,
    load_config,
    normalize_shortcut_color,
    normalize_shortcut_collection,
    normalize_action_input,
    normalize_shortcut_input,
    parse_task_scheduler_shortcut_xml,
    parse_task_scheduler_xml,
    resource_base_dir,
    save_config,
    shortcut_action_mode,
    shortcut_actions,
    shortcut_actions_preview,
    shortcut_command,
    shortcut_execution_mode,
    shortcut_folder,
    unique_shortcut_folders,
)


PLATFORM = current_platform()
RESOURCE_DIR = resource_base_dir()
EXECUTABLE_DIR = executable_base_dir()
CONFIG_CANDIDATES = legacy_config_candidates(
    platform=PLATFORM, executable_dir=EXECUTABLE_DIR,
)
CONFIG_FILE = CONFIG_CANDIDATES[0]
BRANDING_DIR = os.path.join(RESOURCE_DIR, "code", "docs", "branding")
APP_ICON_FILE = os.path.join(BRANDING_DIR, "FlashCmd.ico")
HEADER_ICON_FILE = os.path.join(BRANDING_DIR, "icon-badge.png")
BMC_BUTTON_FILE = os.path.join(BRANDING_DIR, "bmc-button.png")
PRIMARY_COLORS = {
    "blue": ("Blue", "#2563EB"),
    "cyan": ("Cyan", "#0E7490"),
    "teal": ("Teal", "#0F766E"),
    "green": ("Green", "#15803D"),
    "purple": ("Purple", "#7C3AED"),
    "pink": ("Pink", "#BE185D"),
    "orange": ("Orange", "#C2410C"),
    "red": ("Red", "#DC2626"),
}
THEMES = {
    "light": {
        "background": "#F4F6F9", "card": "#FFFFFF", "border": "#E2E8F0",
        "text": "#0F172A", "secondary": "#64748B", "hover": "#F8FAFC",
        "header": "#0F172A", "header_tile": "#1E293B", "disabled": "#94A3B8",
        "danger_surface": "#FEF2F2", "danger_pressed": "#FEE2E2",
    },
    "dark": {
        "background": "#0B1120", "card": "#111827", "border": "#334155",
        "text": "#F8FAFC", "secondary": "#94A3B8", "hover": "#1E293B",
        "header": "#020617", "header_tile": "#1E293B", "disabled": "#64748B",
        "danger_surface": "#3F1D24", "danger_pressed": "#521B25",
    },
}
COLORS = {}
FONTS = {
    "body": ("Segoe UI", 10), "small": ("Segoe UI", 9),
    "heading": ("Segoe UI", 15, "bold"), "title": ("Segoe UI", 20, "bold"),
    "folder": ("Segoe UI", 11, "bold"), "card_title": ("Segoe UI", 10, "bold"),
    "command": ("Consolas", 10),
}
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 20, "xl": 24}
INSTANCE_HOST = "127.0.0.1"
INSTANCE_MESSAGE_RESTORE = b"restore\n"
INSTANCE_BACKLOG = 5
BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/davoodkazemi"
HOTKEY_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Cmd")
HOTKEY_MODIFIER_ALIASES = {
    "ctrl": ("Ctrl", "<ctrl>"), "control": ("Ctrl", "<ctrl>"), "ctl": ("Ctrl", "<ctrl>"),
    "alt": ("Alt", "<alt>"), "option": ("Alt", "<alt>"), "opt": ("Alt", "<alt>"),
    "shift": ("Shift", "<shift>"),
    "cmd": ("Cmd", "<cmd>"), "command": ("Cmd", "<cmd>"), "win": ("Cmd", "<cmd>"),
    "windows": ("Cmd", "<cmd>"), "super": ("Cmd", "<cmd>"), "meta": ("Cmd", "<cmd>"),
}
HOTKEY_CAPTURE_MODIFIERS = {
    "control_l": "Ctrl", "control_r": "Ctrl", "control": "Ctrl",
    "alt_l": "Alt", "alt_r": "Alt", "alt": "Alt", "option_l": "Alt", "option_r": "Alt",
    "shift_l": "Shift", "shift_r": "Shift", "shift": "Shift",
    "command": "Cmd", "command_l": "Cmd", "command_r": "Cmd",
    "super_l": "Cmd", "super_r": "Cmd", "meta_l": "Cmd", "meta_r": "Cmd",
    "win_l": "Cmd", "win_r": "Cmd",
}
HOTKEY_SPECIAL_KEYS = {
    "space": ("Space", "<space>"), "tab": ("Tab", "<tab>"),
    "enter": ("Enter", "<enter>"), "return": ("Enter", "<enter>"),
    "esc": ("Esc", "<esc>"), "escape": ("Esc", "<esc>"),
    "delete": ("Delete", "<delete>"), "del": ("Delete", "<delete>"),
    "backspace": ("Backspace", "<backspace>"),
    "home": ("Home", "<home>"), "end": ("End", "<end>"),
    "pageup": ("Page Up", "<page_up>"), "pagedown": ("Page Down", "<page_down>"),
    "pgup": ("Page Up", "<page_up>"), "pgdn": ("Page Down", "<page_down>"),
    "insert": ("Insert", "<insert>"), "ins": ("Insert", "<insert>"),
    "up": ("Up", "<up>"), "down": ("Down", "<down>"),
    "left": ("Left", "<left>"), "right": ("Right", "<right>"),
}


def _blend(first, second, first_weight):
    values = []
    for offset in (1, 3, 5):
        one, two = int(first[offset:offset + 2], 16), int(second[offset:offset + 2], 16)
        values.append(round(one * first_weight + two * (1 - first_weight)))
    return "#" + "".join(f"{value:02X}" for value in values)


def set_appearance(theme, primary_color):
    theme = theme if theme in THEMES else "light"
    primary_color = primary_color if primary_color in PRIMARY_COLORS else "blue"
    palette = dict(THEMES[theme])
    primary = PRIMARY_COLORS[primary_color][1]
    palette.update({
        "theme": theme, "primary_name": primary_color, "primary": primary,
        "primary_hover": _blend(primary, "#000000", 0.82),
        "primary_tint": _blend(primary, palette["card"], 0.16 if theme == "light" else 0.28),
        "white": "#FFFFFF", "danger": "#DC2626",
        "header_subtext": "#CBD5E1",
    })
    COLORS.clear()
    COLORS.update(palette)
    return theme, primary_color


set_appearance("light", "blue")


def is_windows(platform=None):
    return current_platform(platform) == "windows"


def is_macos(platform=None):
    return current_platform(platform) == "macos"


def apply_window_icon(window):
    """Apply the native Tk icon without leaking a PhotoImage reference."""
    try:
        if is_windows():
            window.iconbitmap(APP_ICON_FILE)
        else:
            image = tk.PhotoImage(file=HEADER_ICON_FILE)
            window.iconphoto(True, image)
            window._flashcmd_icon_image = image
        return True
    except (OSError, tk.TclError):
        return False


def executable_path_is_valid(path, platform=None):
    """Validate a command name or native absolute executable path."""
    system = current_platform(platform)
    path_module = ntpath if system == "windows" else posixpath
    explicit = path_module.isabs(path) or bool(path_module.dirname(path))
    if explicit:
        valid = os.path.isfile(path)
        return valid and (system == "windows" or os.access(path, os.X_OK))
    return shutil.which(path) is not None


def ensure_icon():
    """Return whether the bundled icon is available; never generate files."""
    return os.path.isfile(APP_ICON_FILE)


def configure_styles(root):
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.option_add("*Font", FONTS["body"])
    root.option_add("*insertBackground", COLORS["text"])
    style.configure("App.TFrame", background=COLORS["background"])
    style.configure("CardList.TFrame", background=COLORS["background"])
    style.configure("Dialog.TFrame", background=COLORS["card"])
    style.configure("DialogFooter.TFrame", background=COLORS["hover"])
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("Vertical.TScrollbar", background=COLORS["border"], troughcolor=COLORS["background"], bordercolor=COLORS["background"], arrowcolor=COLORS["text"])
    style.map("Vertical.TScrollbar", background=[("active", COLORS["secondary"]), ("pressed", COLORS["primary"])])
    style.configure("Heading.TLabel", background=COLORS["background"], foreground=COLORS["text"], font=FONTS["heading"])
    style.configure("Secondary.TLabel", background=COLORS["background"], foreground=COLORS["secondary"], font=FONTS["small"])
    style.configure("Dialog.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Helper.TLabel", background=COLORS["card"], foreground=COLORS["secondary"], font=FONTS["small"])
    style.configure("Error.TLabel", background=COLORS["card"], foreground=COLORS["danger"], font=FONTS["small"])
    style.configure("Status.TLabel", background=COLORS["card"], foreground=COLORS["secondary"], padding=(16, 7))
    style.configure("Search.TEntry", fieldbackground=COLORS["card"], foreground=COLORS["text"], insertcolor=COLORS["text"], bordercolor=COLORS["border"], selectbackground=COLORS["primary"], padding=7)
    style.configure("Dialog.TEntry", fieldbackground=COLORS["card"], foreground=COLORS["text"], insertcolor=COLORS["text"], bordercolor=COLORS["border"], selectbackground=COLORS["primary"], padding=7)
    style.configure("Dialog.TCombobox", fieldbackground=COLORS["card"], foreground=COLORS["text"], bordercolor=COLORS["border"], padding=6)
    style.configure("Dialog.TRadiobutton", background=COLORS["card"], foreground=COLORS["text"], indicatorcolor=COLORS["card"], padding=(8, 5))
    style.map("Dialog.TRadiobutton", background=[("active", COLORS["hover"])], indicatorcolor=[("selected", COLORS["primary"])])
    style.configure("Primary.TButton", background=COLORS["primary"], foreground=COLORS["white"], borderwidth=0, padding=(14, 8), font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("disabled", COLORS["disabled"]), ("pressed", COLORS["primary_hover"]), ("active", COLORS["primary_hover"])], foreground=[("disabled", COLORS["hover"])])
    style.configure("Secondary.TButton", background=COLORS["card"], foreground=COLORS["text"], bordercolor=COLORS["border"], padding=(12, 7))
    style.map("Secondary.TButton", background=[("pressed", COLORS["border"]), ("active", COLORS["hover"])] , foreground=[("disabled", COLORS["disabled"])])
    style.configure("Ghost.TButton", background=COLORS["background"], foreground=COLORS["primary"], borderwidth=0, padding=(8, 7))
    style.map("Ghost.TButton", background=[("active", COLORS["primary_tint"]), ("pressed", COLORS["border"])])
    style.configure(
        "CompactToggle.Toolbutton",
        background=COLORS["background"], foreground=COLORS["text"],
        bordercolor=COLORS["border"], lightcolor=COLORS["border"],
        darkcolor=COLORS["border"], borderwidth=1, relief="solid",
        padding=(4, 3), font=("Segoe UI Symbol", 11),
    )
    style.map(
        "CompactToggle.Toolbutton",
        background=[("selected", COLORS["primary_tint"]), ("active", COLORS["hover"])],
        foreground=[("selected", COLORS["primary"])],
        bordercolor=[("selected", COLORS["primary"])],
    )
    style.configure("Danger.TButton", background=COLORS["card"], foreground=COLORS["danger"], bordercolor="#FECACA", padding=(12, 7))
    style.map("Danger.TButton", background=[("active", COLORS["danger_surface"]), ("pressed", COLORS["danger_pressed"])], foreground=[("disabled", COLORS["disabled"])])
    style.configure("Header.TButton", background=COLORS["header_tile"], foreground=COLORS["white"], bordercolor="#334155", padding=(12, 7))
    style.map("Header.TButton", background=[("active", "#334155"), ("pressed", COLORS["primary"])])
    style.configure(
        "HeaderIcon.TButton",
        background=COLORS["header_tile"], foreground=COLORS["white"],
        bordercolor="#64748B", lightcolor="#64748B", darkcolor="#64748B",
        borderwidth=1, relief="solid", padding=(10, 1),
        font=("Segoe UI Symbol", 16, "bold"),
    )
    style.map("HeaderIcon.TButton", background=[("active", "#334155"), ("pressed", COLORS["primary"])])
    return style


def instance_port(config_file=CONFIG_FILE):
    """Return a stable per-user loopback port for single-instance signaling."""
    seed = os.path.normcase(os.path.abspath(os.fspath(config_file))).encode("utf-8", "surrogatepass")
    digest = hashlib.sha256(seed).digest()
    return 41000 + (int.from_bytes(digest[:2], "big") % 20000)


def notify_existing_instance(port, host=INSTANCE_HOST, timeout=1.0):
    """Ask the already-running instance to restore its window."""
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(INSTANCE_MESSAGE_RESTORE)
    return True


class SingleInstanceEndpoint:
    """Serve simple loopback restore requests for the primary process."""

    def __init__(self, port, host=INSTANCE_HOST):
        self.host = host
        self._restore_callback = None
        self._pending_restore = False
        self._closed = threading.Event()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if is_windows() and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif hasattr(socket, "SO_REUSEADDR"):
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket.listen(INSTANCE_BACKLOG)
        self._socket.settimeout(0.5)
        self.port = self._socket.getsockname()[1]
        self._thread = threading.Thread(
            target=self._serve, name="FlashCMDInstanceServer", daemon=True,
        )
        self._thread.start()

    def set_restore_callback(self, callback):
        self._restore_callback = callback
        if self._pending_restore and callback is not None:
            self._pending_restore = False
            callback()

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._socket.close()
        except OSError:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _serve(self):
        while not self._closed.is_set():
            try:
                connection, _address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                try:
                    message = connection.recv(64)
                except OSError:
                    continue
                if message.strip().lower() == INSTANCE_MESSAGE_RESTORE.strip():
                    if self._restore_callback is None:
                        self._pending_restore = True
                    else:
                        self._restore_callback()


def _normalize_hotkey_main_token(token):
    clean = token.strip()
    key = clean.casefold().replace(" ", "")
    if len(key) == 1 and key.isalnum():
        return (key.upper() if key.isalpha() else key, key.lower())
    if key in HOTKEY_SPECIAL_KEYS:
        return HOTKEY_SPECIAL_KEYS[key]
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return (f"F{number}", f"<f{number}>")
    raise ValueError(
        "Use a letter, number, function key, or a key such as Enter, Space, or Escape.",
    )


def hotkey_modifier_from_keysym(keysym):
    """Map a Tk keysym to one canonical modifier display name."""
    return HOTKEY_CAPTURE_MODIFIERS.get(str(keysym).strip().casefold())


def capture_restore_hotkey(keysym, active_modifiers):
    """Build one canonical restore hotkey from a Tk keysym and held modifiers."""
    main_display, _expression = _normalize_hotkey_main_token(str(keysym))
    ordered_modifiers = [
        display for display in HOTKEY_MODIFIER_ORDER if display in set(active_modifiers)
    ]
    if not ordered_modifiers:
        raise ValueError("Include at least one modifier key such as Ctrl, Alt, Shift, or Cmd.")
    return "+".join([*ordered_modifiers, main_display])


def parse_restore_hotkey(value):
    """Return canonical display and pynput hotkey expressions."""
    text = "" if value is None else str(value).strip()
    if not text:
        return "", ""
    parts = [part.strip() for part in text.replace(",", "+").split("+")]
    if any(not part for part in parts):
        raise ValueError("Use plus signs between keys, for example Ctrl+Alt+F.")
    modifiers = {}
    main_display = main_expression = ""
    for part in parts:
        key = part.casefold().replace(" ", "")
        if key in HOTKEY_MODIFIER_ALIASES:
            display, expression = HOTKEY_MODIFIER_ALIASES[key]
            if display in modifiers:
                raise ValueError("Do not repeat the same modifier key.")
            modifiers[display] = expression
            continue
        if main_expression:
            raise ValueError("Use exactly one non-modifier key in the restore hotkey.")
        main_display, main_expression = _normalize_hotkey_main_token(part)
    if not modifiers:
        raise ValueError("Include at least one modifier key such as Ctrl, Alt, Shift, or Cmd.")
    if not main_expression:
        raise ValueError("Add a final key such as F, F12, Enter, or Space.")
    ordered_modifiers = [
        (display, modifiers[display]) for display in HOTKEY_MODIFIER_ORDER if display in modifiers
    ]
    display = "+".join([*(display for display, _expression in ordered_modifiers), main_display])
    expression = "+".join([*(_expression for _display, _expression in ordered_modifiers), main_expression])
    return display, expression


def _load_hotkey_backend():
    try:
        return importlib.import_module("pynput.keyboard"), None
    except Exception as error:
        return None, str(error)


def create_restore_hotkey_listener(expression, callback, keyboard_module=None):
    """Create and start a pynput global hotkey listener."""
    keyboard_module = keyboard_module or _load_hotkey_backend()[0]
    keyboard_module.HotKey.parse(expression)
    listener = keyboard_module.GlobalHotKeys({expression: callback})
    listener.start()
    if hasattr(listener, "wait"):
        listener.wait()
    return listener


class ScrollableCardList(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style="CardList.TFrame")
        self.canvas = tk.Canvas(self, bg=COLORS["background"], highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interior = tk.Frame(self.canvas, bg=COLORS["background"])
        self.window_id = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._empty = False
        self.interior.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        for widget in (self.canvas, self.interior):
            widget.bind("<Enter>", self._enable_wheel)
            widget.bind("<Leave>", self._disable_wheel)

    def _sync_scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width, height=event.height if self._empty else 0)

    def _enable_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _disable_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        divisor = 1 if is_macos() else 120
        units = -int(event.delta / divisor) if event.delta else 0
        if units:
            self.canvas.yview_scroll(units, "units")
        return "break"

    def clear(self):
        for child in self.interior.winfo_children():
            child.destroy()
        self.set_empty(False)
        self.canvas.yview_moveto(0)

    def set_empty(self, value):
        self._empty = value
        height = self.canvas.winfo_height() if value else 0
        self.canvas.itemconfigure(self.window_id, height=height)

    def apply_appearance(self):
        self.canvas.configure(bg=COLORS["background"])
        self.interior.configure(bg=COLORS["background"])


class ShortcutCard(tk.Frame):
    def __init__(
        self, parent, source_index, shortcut, on_select, on_edit,
        on_context=None, compact=False,
    ):
        super().__init__(parent, bg=COLORS["card"], highlightthickness=1, takefocus=True, cursor="hand2")
        self.source_index = source_index
        self.on_select = on_select
        self.on_edit = on_edit
        self.on_context = on_context
        self.selected = False
        self.hovered = False
        self.compact = bool(compact)
        self.shortcut_color = ""
        self.accent = tk.Frame(self, width=4, bg=COLORS["card"])
        self.accent.pack(side="left", fill="y")
        content = tk.Frame(self, bg=COLORS["card"], padx=12, pady=4 if self.compact else 8)
        content.pack(side="left", fill="both", expand=True)
        self.name_label = tk.Label(content, text=str(shortcut.get("name", "")), anchor="w", bg=COLORS["card"], fg=COLORS["text"], font=FONTS["card_title"])
        self.name_label.pack(fill="x")
        try:
            actions = shortcut_actions(shortcut)
            self.shortcut_color = first_action_color(shortcut)
            preview = shortcut_actions_preview(shortcut)
        except ValidationError:
            actions, preview = [], "Invalid action list"
        self.command_label = self.details_label = None
        colored_widgets = [content, self.name_label]
        if not self.compact:
            self.command_label = tk.Label(content, text=preview, anchor="w", justify="left", bg=COLORS["card"], fg=COLORS["text"], font=FONTS["command"], pady=3)
            self.command_label.pack(fill="x")
            details = [f"Folder: {shortcut_folder(shortcut)}"]
            mode_label = "All at once" if shortcut_execution_mode(shortcut) == EXECUTION_MODE_PARALLEL else "One by one"
            details.append(f"{len(actions)} action{'s' if len(actions) != 1 else ''}")
            details.append(mode_label)
            self.details_label = tk.Label(content, text="  •  ".join(details), anchor="w", bg=COLORS["card"], fg=COLORS["secondary"], font=FONTS["small"])
            self.details_label.pack(fill="x")
            colored_widgets.extend((self.command_label, self.details_label))
        self._colored_widgets = tuple(colored_widgets)
        for widget in (self, self.accent, *self._colored_widgets):
            widget.bind("<Button-1>", self._select)
            widget.bind("<Double-Button-1>", self._edit)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            if self.on_context:
                widget.bind("<Button-3>", self._context)
                widget.bind("<Control-Button-1>", self._context)
        self.bind("<FocusIn>", self._focus)
        self.bind("<space>", self._select)
        self.set_visual_state(False, False)

    def _select(self, _event=None):
        self.focus_set()
        self.on_select(self.source_index)
        return "break"

    def _edit(self, _event=None):
        self.on_select(self.source_index)
        self.on_edit()
        return "break"

    def _context(self, event):
        self.on_select(self.source_index)
        self.on_context(event, self.source_index)
        return "break"

    def _focus(self, _event=None):
        self.on_select(self.source_index)

    def _enter(self, _event=None):
        self.hovered = True
        self.set_visual_state(self.selected, True)

    def _leave(self, _event=None):
        self.after_idle(self._check_hover)

    def _check_hover(self):
        x, y = self.winfo_pointerx(), self.winfo_pointery()
        inside = self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width() and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()
        self.hovered = inside
        self.set_visual_state(self.selected, inside)

    def set_visual_state(self, selected, hovered):
        self.selected, self.hovered = selected, hovered
        if selected:
            background, border = COLORS["primary_tint"], COLORS["primary"]
            accent = self.shortcut_color or COLORS["primary"]
        elif hovered:
            background = COLORS["hover"]
            border = self.shortcut_color or COLORS["primary"]
            accent = self.shortcut_color or COLORS["hover"]
        else:
            background, border = COLORS["card"], COLORS["border"]
            accent = self.shortcut_color or COLORS["card"]
        self.configure(bg=background, highlightbackground=border, highlightcolor=border)
        self.accent.configure(bg=accent)
        for widget in self._colored_widgets:
            widget.configure(bg=background)

class _Dialog(tk.Toplevel):
    def __init__(self, parent, title, width, primary_text="Save", minimum_height=1, resizable=False):
        super().__init__(parent)
        self.parent = parent
        self.main_window = parent.winfo_toplevel()
        self.result = None
        self.withdraw()
        self.title(title)
        self.configure(bg=COLORS["card"])
        self.transient(self.main_window)
        self.resizable(resizable, resizable)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        apply_window_icon(self)
        self.body = ttk.Frame(self, padding=SPACE["xl"], style="Dialog.TFrame")
        self.body.grid(row=0, column=0, sticky="nsew")
        self.frame = self.body
        self.footer = ttk.Frame(self, padding=(SPACE["xl"], SPACE["md"]), style="DialogFooter.TFrame")
        self.footer.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._build()
        ttk.Button(self.footer, text="Cancel", command=self._cancel, style="Secondary.TButton").pack(side="right")
        ttk.Button(self.footer, text=primary_text, command=self._save, style="Primary.TButton").pack(side="right", padx=(0, SPACE["sm"]))
        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Return>", self._on_return)
        self.bind("<Control-Return>", lambda _event: self._save() or "break")
        self.update_idletasks()
        height = max(minimum_height, self.winfo_reqheight())
        self.geometry(f"{width}x{height}")
        minimum_dialog_height = minimum_height if resizable else min(height, 280)
        self.minsize(min(width, 420), minimum_dialog_height)
        self._center_on_parent(width, height)
        self.wm_positionfrom("user")
        self.deiconify()
        self.wait_visibility()
        self._center_on_parent(width, height)
        self.lift(self.main_window)
        self.grab_set()
        focus = self.initial_focus()
        if focus:
            focus.focus_set()
        self.wait_window(self)

    def _center_on_parent(self, width, height):
        self.main_window.update_idletasks()
        x = self.main_window.winfo_x() + (self.main_window.winfo_width() - width) // 2
        y = self.main_window.winfo_y() + (self.main_window.winfo_height() - height) // 2
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        self.geometry(f"+{x}+{y}")

    def _on_return(self, _event=None):
        if isinstance(self.focus_get(), tk.Text):
            return None
        self._save()
        return "break"

    def _cancel(self):
        self.result = None
        self.destroy()

    def initial_focus(self):
        return None


class _LegacyShortcutDialog(_Dialog):
    def __init__(self, parent, title, shortcut=None, available_folders=None):
        self.shortcut = shortcut or {}
        folders = list(available_folders or ())
        self.available_folders = [GENERAL_FOLDER, *[
            folder for folder in folders if folder.casefold() != GENERAL_FOLDER.casefold()
        ]]
        primary_text = "Save changes" if shortcut else "Add shortcut"
        super().__init__(parent, title, 620, primary_text, minimum_height=680, resizable=True)

    def _build(self):
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(8, weight=1)
        ttk.Label(self.body, text="Name", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.body, text="A short label that is easy to scan.", style="Helper.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 6))
        self.name = ttk.Entry(self.body, style="Dialog.TEntry")
        self.name.grid(row=2, column=0, sticky="ew")
        self.name_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.name_error, style="Error.TLabel").grid(row=3, column=0, sticky="w", pady=(2, 10))

        ttk.Label(self.body, text="Action Type", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w")
        mode_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        mode_frame.grid(row=5, column=0, sticky="w", pady=(5, 12))
        self.action_mode = tk.StringVar(value=shortcut_action_mode(self.shortcut))
        ttk.Radiobutton(
            mode_frame, text="Command Line", value=ACTION_MODE_COMMAND_LINE,
            variable=self.action_mode, command=self._change_action_mode,
            style="Dialog.TRadiobutton",
        ).pack(side="left")
        ttk.Radiobutton(
            mode_frame, text="Program/Script", value=ACTION_MODE_PROGRAM,
            variable=self.action_mode, command=self._change_action_mode,
            style="Dialog.TRadiobutton",
        ).pack(side="left", padx=(SPACE["sm"], 0))

        self.program_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        self.program_frame.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        self.program_frame.columnconfigure(0, weight=1)
        ttk.Label(self.program_frame, text="Program/script", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.program_frame, text="Executable, script, or document to run.", style="Helper.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 6))
        program_input = ttk.Frame(self.program_frame, style="Dialog.TFrame")
        program_input.grid(row=2, column=0, sticky="ew")
        program_input.columnconfigure(0, weight=1)
        self.program = ttk.Entry(program_input, style="Dialog.TEntry")
        self.program.grid(row=0, column=0, sticky="ew")
        ttk.Button(program_input, text="Browse...", command=self._browse_program, style="Secondary.TButton").grid(row=0, column=1, padx=(SPACE["sm"], 0))
        self.program_error = tk.StringVar()
        ttk.Label(self.program_frame, textvariable=self.program_error, style="Error.TLabel").grid(row=3, column=0, sticky="w", pady=(2, 0))

        self.command_title = ttk.Label(self.body, text="Command", style="Dialog.TLabel", font=("Segoe UI", 10, "bold"))
        self.command_title.grid(row=7, column=0, sticky="w")
        command_frame = tk.Frame(self.body, bg=COLORS["border"], padx=1, pady=1)
        command_frame.grid(row=8, column=0, sticky="nsew", pady=(6, 0))
        command_frame.rowconfigure(0, weight=1)
        command_frame.columnconfigure(0, weight=1)
        self.cmd = tk.Text(command_frame, height=6, wrap="word", undo=True, relief="flat", bd=0, padx=9, pady=8, bg=COLORS["card"], fg=COLORS["text"], insertbackground=COLORS["text"], font=FONTS["command"])
        self.cmd.grid(row=0, column=0, sticky="nsew")
        command_scroll = ttk.Scrollbar(command_frame, orient="vertical", command=self.cmd.yview)
        command_scroll.grid(row=0, column=1, sticky="ns")
        self.cmd.configure(yscrollcommand=command_scroll.set)
        self.command_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.command_error, style="Error.TLabel").grid(row=9, column=0, sticky="w", pady=(2, 10))

        ttk.Label(self.body, text="Start in", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=10, column=0, sticky="w")
        ttk.Label(self.body, text="Optional existing folder used as the working directory.", style="Helper.TLabel").grid(row=11, column=0, sticky="w", pady=(2, 6))
        start_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        start_frame.grid(row=12, column=0, sticky="ew")
        start_frame.columnconfigure(0, weight=1)
        self.start = ttk.Entry(start_frame, style="Dialog.TEntry")
        self.start.grid(row=0, column=0, sticky="ew")
        ttk.Button(start_frame, text="Browse…", command=self._browse, style="Secondary.TButton").grid(row=0, column=1, padx=(SPACE["sm"], 0))
        self.start_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.start_error, style="Error.TLabel").grid(row=13, column=0, sticky="w", pady=(2, 0))

        ttk.Label(self.body, text="Folder", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=14, column=0, sticky="w", pady=(10, 0))
        ttk.Label(self.body, text="Choose an existing folder or type a new folder name.", style="Helper.TLabel").grid(row=15, column=0, sticky="w", pady=(2, 6))
        self.folder = ttk.Combobox(
            self.body, values=self.available_folders, style="Dialog.TCombobox",
        )
        self.folder.grid(row=16, column=0, sticky="ew")

        ttk.Label(self.body, text="Shortcut color", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=17, column=0, sticky="w", pady=(14, 0))
        ttk.Label(self.body, text="Used for the card accent and Windows Terminal tab.", style="Helper.TLabel").grid(row=18, column=0, sticky="w", pady=(2, 6))
        current_color = normalize_shortcut_color(self.shortcut.get("color", ""))
        self.color_var = tk.StringVar(value=current_color)
        color_frame = tk.Frame(self.body, bg=COLORS["card"])
        color_frame.grid(row=19, column=0, sticky="w")
        self.color_preview = tk.Button(
            color_frame, command=self._choose_shortcut_color, width=14,
            font=("Segoe UI", 9, "bold"), padx=8, pady=5,
            relief=tk.RAISED, overrelief=tk.RIDGE, bd=1,
            highlightthickness=1, highlightbackground=COLORS["border"],
            cursor="hand2", takefocus=True,
        )
        self.color_preview.pack(side="left")
        self.clear_color_button = ttk.Button(
            color_frame, text="Clear", command=self._clear_shortcut_color,
            style="Secondary.TButton",
        )
        self.clear_color_button.pack(side="left", padx=(SPACE["sm"], 0))
        self._update_color_preview()

        task_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        task_frame.grid(row=20, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(task_frame, text="Import from Task Scheduler XML", command=self._import_task_xml, style="Secondary.TButton").pack(side="left")
        ttk.Button(task_frame, text="Export as Task Scheduler XML", command=self._export_task_xml, style="Secondary.TButton").pack(side="left", padx=(SPACE["sm"], 0))

        self.name.insert(0, str(self.shortcut.get("name", "")))
        self.program.insert(0, str(self.shortcut.get("program_path", "")))
        self.start.insert(0, str(self.shortcut.get("start_in", "")))
        self.folder.insert(0, shortcut_folder(self.shortcut))
        self._mode_text = {
            ACTION_MODE_COMMAND_LINE: str(self.shortcut.get("command", "")),
            ACTION_MODE_PROGRAM: str(self.shortcut.get("arguments", "")),
        }
        self._displayed_mode = self.action_mode.get()
        self.cmd.insert("1.0", self._mode_text[self._displayed_mode])
        self._update_action_mode_ui()

    def initial_focus(self):
        return self.name

    def _choose_shortcut_color(self):
        initial = normalize_shortcut_color(self.color_var.get()) or PRIMARY_COLORS["blue"][1]
        _rgb, selected = colorchooser.askcolor(
            color=initial, parent=self, title="Choose shortcut color",
        )
        selected = normalize_shortcut_color(selected)
        if selected:
            self.color_var.set(selected)
            self._update_color_preview()

    def _clear_shortcut_color(self):
        self.color_var.set("")
        self._update_color_preview()

    def _update_color_preview(self):
        selected = normalize_shortcut_color(self.color_var.get())
        background = selected or COLORS["card"]
        if selected:
            red, green, blue = (int(selected[offset:offset + 2], 16) for offset in (1, 3, 5))
            foreground = "#0F172A" if red * 299 + green * 587 + blue * 114 > 150000 else COLORS["white"]
        else:
            foreground = COLORS["text"]
        self.color_preview.configure(
            text=selected or "Choose color…", bg=background, fg=foreground,
            activebackground=background, activeforeground=foreground,
        )
        self.clear_color_button.state(["!disabled"] if selected else ["disabled"])

    def _browse(self):
        current = self.start.get().strip()
        options = {"parent": self, "title": "Choose working directory"}
        if current and os.path.isdir(current):
            options["initialdir"] = current
        folder = filedialog.askdirectory(**options)
        if folder:
            self.start.delete(0, tk.END)
            self.start.insert(0, folder)
            self.start_error.set("")

    def _browse_program(self):
        current = self.program.get().strip()
        filetypes = (
            (("Programs and scripts", "*.exe *.com *.bat *.cmd *.ps1 *.py"), ("All files", "*.*"))
            if is_windows() else (("All files", "*"),)
        )
        options = {
            "parent": self, "title": "Choose a program or script",
            "filetypes": filetypes,
        }
        if current and os.path.isfile(current):
            options["initialdir"] = os.path.dirname(current)
        selected = filedialog.askopenfilename(**options)
        if selected:
            self._replace_entry(self.program, selected)
            self.program_error.set("")

    @staticmethod
    def _replace_entry(entry, value):
        entry.delete(0, tk.END)
        entry.insert(0, value)

    def _replace_command_text(self, value):
        self.cmd.delete("1.0", tk.END)
        self.cmd.insert("1.0", value)
        self.cmd.mark_set("insert", "1.0")
        self.cmd.see("1.0")
        self.cmd.update_idletasks()

    def _ensure_action_editor_visible(self):
        """Grow and repaint the dialog after Program/Script controls appear."""
        self.update_idletasks()
        required_height = self.winfo_reqheight()
        current_height = self.winfo_height()
        if self.winfo_viewable() and required_height > current_height:
            maximum_height = max(280, self.winfo_screenheight() - 40)
            self.geometry(f"{self.winfo_width()}x{min(required_height, maximum_height)}")
            self.update_idletasks()
        self.cmd.see("1.0")
        self.cmd.update_idletasks()

    def _capture_mode_text(self):
        self._mode_text[self._displayed_mode] = self.cmd.get("1.0", "end-1c")

    def _change_action_mode(self):
        self._capture_mode_text()
        self._displayed_mode = self.action_mode.get()
        self._update_action_mode_ui()
        self._replace_command_text(self._mode_text[self._displayed_mode])
        self._ensure_action_editor_visible()

    def _update_action_mode_ui(self):
        if self.action_mode.get() == ACTION_MODE_PROGRAM:
            self.program_frame.grid()
            self.command_title.configure(text="Add arguments (optional)")
        else:
            self.program_frame.grid_remove()
            self.command_title.configure(text="Command")
        self.program_error.set("")
        self.command_error.set("")

    def _import_task_xml(self):
        selected = filedialog.askopenfilename(
            parent=self, title="Import Task Scheduler XML",
            filetypes=(("Task Scheduler XML", "*.xml"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            with open(selected, "rb") as task_file:
                values = parse_task_scheduler_xml(task_file.read())
        except (OSError, TaskSchedulerError) as error:
            messagebox.showerror("Task Scheduler Import", str(error), parent=self)
            return
        self._capture_mode_text()
        self.action_mode.set(ACTION_MODE_PROGRAM)
        self._displayed_mode = ACTION_MODE_PROGRAM
        self._mode_text[ACTION_MODE_PROGRAM] = values["arguments"]
        self._update_action_mode_ui()
        self._replace_command_text(values["arguments"])
        self._replace_entry(self.program, values["program_path"])
        self._replace_entry(self.start, values["start_in"])
        if values["name"] and not self.name.get().strip():
            self._replace_entry(self.name, values["name"])
        self._ensure_action_editor_visible()
        self.cmd.focus_set()

    def _export_task_xml(self):
        if self.action_mode.get() != ACTION_MODE_PROGRAM:
            messagebox.showwarning(
                "Task Scheduler Export", "Choose Program/Script before exporting.", parent=self,
            )
            return
        try:
            values = normalize_shortcut_input(
                self.name.get(), "", self.start.get(), ACTION_MODE_PROGRAM,
                self.program.get(), self.cmd.get("1.0", "end-1c"),
            )
            xml_text = build_task_scheduler_xml(
                values["name"], values["program_path"], values["arguments"], values["start_in"],
            )
        except (ValidationError, TaskSchedulerError) as error:
            if isinstance(error, ValidationError) and error.field == "name":
                self.name_error.set(str(error))
                self.name.focus_set()
            else:
                self.program_error.set(str(error))
                self.program.focus_set()
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_ " else "_"
            for character in values["name"]
        ).strip() or "FlashCMD Task"
        destination = filedialog.asksaveasfilename(
            parent=self, title="Export Task Scheduler XML",
            defaultextension=".xml", initialfile=f"{safe_name}.xml",
            filetypes=(("Task Scheduler XML", "*.xml"), ("All files", "*.*")),
        )
        if not destination:
            return
        try:
            with open(destination, "w", encoding="utf-8", newline="\n") as task_file:
                task_file.write(xml_text)
                task_file.write("\n")
        except OSError as error:
            messagebox.showerror("Task Scheduler Export", str(error), parent=self)
            return
        messagebox.showinfo("Task Scheduler Export", f"Exported task XML to:\n{destination}", parent=self)

    def _save(self):
        self.name_error.set("")
        self.command_error.set("")
        self.program_error.set("")
        self.start_error.set("")
        try:
            values = normalize_shortcut_input(
                self.name.get(), self.cmd.get("1.0", "end-1c"), self.start.get(),
                self.action_mode.get(), self.program.get(), self.cmd.get("1.0", "end-1c"),
                self.folder.get(), self.color_var.get(),
            )
        except ValidationError as error:
            targets = {"name": self.name, "program_path": self.program, "command": self.cmd}
            errors = {"name": self.name_error, "program_path": self.program_error, "command": self.command_error}
            target = targets.get(error.field, self.cmd)
            errors.get(error.field, self.command_error).set(str(error))
            target.focus_set()
            return
        if values["start_in"] and not os.path.isdir(values["start_in"]):
            self.start_error.set("Choose an existing directory.")
            self.start.focus_set()
            return
        self.result = dict(self.shortcut)
        for key in ("action_mode", "command", "program_path", "arguments", "tags", "folder", "color"):
            self.result.pop(key, None)
        self.result.update(values)
        self.destroy()


class ActionDialog(_LegacyShortcutDialog):
    """Editor for one named command or direct program action."""

    def __init__(self, parent, title, action=None, focus_field=None):
        self.shortcut = deepcopy(action) if isinstance(action, dict) else {}
        self.focus_field = focus_field
        _Dialog.__init__(self, parent, title, 600, "Save action", minimum_height=580, resizable=True)

    def _build(self):
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(7, weight=1)
        ttk.Label(self.body, text="Action name", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.name = ttk.Entry(self.body, style="Dialog.TEntry")
        self.name.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.name_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.name_error, style="Error.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 10))

        ttk.Label(self.body, text="Action type", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w")
        mode_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        mode_frame.grid(row=4, column=0, sticky="w", pady=(5, 12))
        self.action_mode = tk.StringVar(value=shortcut_action_mode(self.shortcut))
        ttk.Radiobutton(mode_frame, text="Command Line", value=ACTION_MODE_COMMAND_LINE, variable=self.action_mode, command=self._change_action_mode, style="Dialog.TRadiobutton").pack(side="left")
        ttk.Radiobutton(mode_frame, text="Program/Script", value=ACTION_MODE_PROGRAM, variable=self.action_mode, command=self._change_action_mode, style="Dialog.TRadiobutton").pack(side="left", padx=(SPACE["sm"], 0))

        self.program_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        self.program_frame.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        self.program_frame.columnconfigure(0, weight=1)
        ttk.Label(self.program_frame, text="Program/script", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        program_input = ttk.Frame(self.program_frame, style="Dialog.TFrame")
        program_input.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        program_input.columnconfigure(0, weight=1)
        self.program = ttk.Entry(program_input, style="Dialog.TEntry")
        self.program.grid(row=0, column=0, sticky="ew")
        ttk.Button(program_input, text="Browse…", command=self._browse_program, style="Secondary.TButton").grid(row=0, column=1, padx=(SPACE["sm"], 0))
        self.program_error = tk.StringVar()
        ttk.Label(self.program_frame, textvariable=self.program_error, style="Error.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 0))

        self.command_title = ttk.Label(self.body, text="Command", style="Dialog.TLabel", font=("Segoe UI", 10, "bold"))
        self.command_title.grid(row=6, column=0, sticky="w")
        command_frame = tk.Frame(self.body, bg=COLORS["border"], padx=1, pady=1)
        command_frame.grid(row=7, column=0, sticky="nsew", pady=(6, 0))
        command_frame.rowconfigure(0, weight=1)
        command_frame.columnconfigure(0, weight=1)
        self.cmd = tk.Text(command_frame, height=6, wrap="word", undo=True, relief="flat", bd=0, padx=9, pady=8, bg=COLORS["card"], fg=COLORS["text"], insertbackground=COLORS["text"], font=FONTS["command"])
        self.cmd.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(command_frame, orient="vertical", command=self.cmd.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.cmd.configure(yscrollcommand=scrollbar.set)
        self.command_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.command_error, style="Error.TLabel").grid(row=8, column=0, sticky="w", pady=(2, 10))

        ttk.Label(self.body, text="Start in", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=9, column=0, sticky="w")
        start_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        start_frame.grid(row=10, column=0, sticky="ew", pady=(5, 0))
        start_frame.columnconfigure(0, weight=1)
        self.start = ttk.Entry(start_frame, style="Dialog.TEntry")
        self.start.grid(row=0, column=0, sticky="ew")
        ttk.Button(start_frame, text="Browse…", command=self._browse, style="Secondary.TButton").grid(row=0, column=1, padx=(SPACE["sm"], 0))
        self.start_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.start_error, style="Error.TLabel").grid(row=11, column=0, sticky="w", pady=(2, 0))

        ttk.Label(self.body, text="Action color", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=12, column=0, sticky="w", pady=(14, 0))
        ttk.Label(self.body, text="Used for this action's Windows Terminal tab and the shortcut card accent.", style="Helper.TLabel").grid(row=13, column=0, sticky="w", pady=(2, 6))
        self.color_var = tk.StringVar(value=normalize_shortcut_color(self.shortcut.get("color", "")))
        color_frame = tk.Frame(self.body, bg=COLORS["card"])
        color_frame.grid(row=14, column=0, sticky="w")
        self.color_preview = tk.Button(
            color_frame, command=self._choose_action_color, width=14,
            font=("Segoe UI", 9, "bold"), padx=8, pady=5, cursor="hand2",
        )
        self.color_preview.pack(side="left")
        self.clear_color_button = ttk.Button(
            color_frame, text="Clear", command=self._clear_action_color,
            style="Secondary.TButton",
        )
        self.clear_color_button.pack(side="left", padx=(SPACE["sm"], 0))
        self._update_color_preview()

        self.name.insert(0, str(self.shortcut.get("name", "")))
        self.program.insert(0, str(self.shortcut.get("program_path", "")))
        self.start.insert(0, str(self.shortcut.get("start_in", "")))
        self._mode_text = {
            ACTION_MODE_COMMAND_LINE: str(self.shortcut.get("command", "")),
            ACTION_MODE_PROGRAM: str(self.shortcut.get("arguments", "")),
        }
        self._displayed_mode = self.action_mode.get()
        self.cmd.insert("1.0", self._mode_text[self._displayed_mode])
        self._update_action_mode_ui()
        error_variables = {
            "name": self.name_error, "program_path": self.program_error,
            "command": self.command_error, "start_in": self.start_error,
        }
        if self.focus_field in error_variables:
            error_variables[self.focus_field].set("This field needs attention.")

    def initial_focus(self):
        return {
            "name": self.name, "program_path": self.program,
            "command": self.cmd, "start_in": self.start,
        }.get(self.focus_field, self.name)

    def _choose_action_color(self):
        initial = normalize_shortcut_color(self.color_var.get()) or PRIMARY_COLORS["blue"][1]
        _rgb, selected = colorchooser.askcolor(
            color=initial, parent=self, title="Choose action color",
        )
        selected = normalize_shortcut_color(selected)
        if selected:
            self.color_var.set(selected)
            self._update_color_preview()

    def _clear_action_color(self):
        self.color_var.set("")
        self._update_color_preview()

    def _save(self):
        self.name_error.set("")
        self.command_error.set("")
        self.program_error.set("")
        self.start_error.set("")
        try:
            values = normalize_action_input(
                name=self.name.get(), action_mode=self.action_mode.get(),
                command=self.cmd.get("1.0", "end-1c"),
                program_path=self.program.get(),
                arguments=self.cmd.get("1.0", "end-1c"),
                start_in=self.start.get(),
                color=self.color_var.get(),
            )
        except ValidationError as error:
            targets = {"name": self.name, "program_path": self.program, "command": self.cmd}
            errors = {"name": self.name_error, "program_path": self.program_error, "command": self.command_error}
            errors.get(error.field, self.command_error).set(str(error))
            targets.get(error.field, self.cmd).focus_set()
            return
        if values["start_in"] and not os.path.isdir(values["start_in"]):
            self.start_error.set("Choose an existing directory.")
            self.start.focus_set()
            return
        self.result = values
        self.destroy()


class ShortcutDialog(_LegacyShortcutDialog):
    """Editor for shortcut metadata and its ordered collection of actions."""

    def __init__(self, parent, title, shortcut=None, available_folders=None):
        self.shortcut = shortcut or {}
        folders = list(available_folders or ())
        self.available_folders = [GENERAL_FOLDER, *[
            folder for folder in folders
            if folder.casefold() != GENERAL_FOLDER.casefold()
        ]]
        if shortcut:
            try:
                self.actions = shortcut_actions(self.shortcut)
            except ValidationError:
                raw_actions = self.shortcut.get("actions", [])
                self.actions = deepcopy(raw_actions) if isinstance(raw_actions, list) else []
        else:
            self.actions = [{
                "name": "", "action_mode": ACTION_MODE_COMMAND_LINE,
                "command": "", "start_in": "",
            }]
        primary_text = "Save changes" if shortcut else "Add shortcut"
        _Dialog.__init__(self, parent, title, 680, primary_text, minimum_height=620, resizable=True)

    def _build(self):
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(6, weight=1)
        ttk.Label(self.body, text="Name", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.name = ttk.Entry(self.body, style="Dialog.TEntry")
        self.name.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.name_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.name_error, style="Error.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 8))

        metadata = ttk.Frame(self.body, style="Dialog.TFrame")
        metadata.grid(row=3, column=0, sticky="ew")
        metadata.columnconfigure((0, 1), weight=1)
        ttk.Label(metadata, text="Folder", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(metadata, text="Execution mode", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(SPACE["lg"], 0))
        self.folder = ttk.Combobox(metadata, values=self.available_folders, style="Dialog.TCombobox")
        self.folder.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.execution_mode = tk.StringVar(value=shortcut_execution_mode(self.shortcut))
        mode_frame = ttk.Frame(metadata, style="Dialog.TFrame")
        mode_frame.grid(row=1, column=1, sticky="w", padx=(SPACE["lg"], 0), pady=(5, 0))
        ttk.Radiobutton(mode_frame, text="One by one", value=EXECUTION_MODE_SEQUENTIAL, variable=self.execution_mode, style="Dialog.TRadiobutton").pack(side="left")
        ttk.Radiobutton(mode_frame, text="All at once", value=EXECUTION_MODE_PARALLEL, variable=self.execution_mode, style="Dialog.TRadiobutton").pack(side="left", padx=(SPACE["sm"], 0))

        ttk.Label(self.body, text="Actions", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(16, 0))
        ttk.Label(self.body, text="Actions run in the order shown.", style="Helper.TLabel").grid(row=5, column=0, sticky="w", pady=(2, 6))
        list_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        list_frame.grid(row=6, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.action_list = ttk.Treeview(list_frame, columns=("sequence", "name", "type"), show="headings", height=8, selectmode="browse")
        self.action_list.heading("sequence", text="#")
        self.action_list.heading("name", text="Action name")
        self.action_list.heading("type", text="Type")
        self.action_list.column("sequence", width=42, anchor="center", stretch=False)
        self.action_list.column("name", width=360)
        self.action_list.column("type", width=120, stretch=False)
        self.action_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.action_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.action_list.configure(yscrollcommand=scrollbar.set)
        self.action_list.bind("<<TreeviewSelect>>", lambda _event: self._update_action_buttons())
        self.action_list.bind("<Double-Button-1>", lambda _event: self._edit_action())

        controls = ttk.Frame(self.body, style="Dialog.TFrame")
        controls.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.add_action_button = ttk.Button(controls, text="Add action", command=self._add_action, style="Secondary.TButton")
        self.add_action_button.pack(side="left")
        self.edit_action_button = ttk.Button(controls, text="Edit", command=self._edit_action, style="Secondary.TButton")
        self.edit_action_button.pack(side="left", padx=(SPACE["xs"], 0))
        self.clone_action_button = ttk.Button(controls, text="Clone", command=self._clone_action, style="Secondary.TButton")
        self.clone_action_button.pack(side="left", padx=(SPACE["xs"], 0))
        self.delete_action_button = ttk.Button(controls, text="Delete", command=self._delete_action, style="Secondary.TButton")
        self.delete_action_button.pack(side="left", padx=(SPACE["xs"], 0))
        self.up_action_button = ttk.Button(controls, text="Move up", command=lambda: self._move_action(-1), style="Secondary.TButton")
        self.up_action_button.pack(side="left", padx=(SPACE["xs"], 0))
        self.down_action_button = ttk.Button(controls, text="Move down", command=lambda: self._move_action(1), style="Secondary.TButton")
        self.down_action_button.pack(side="left", padx=(SPACE["xs"], 0))

        task_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        task_frame.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(task_frame, text="Import from Task Scheduler XML", command=self._import_task_xml, style="Secondary.TButton").pack(side="left")
        ttk.Button(task_frame, text="Export as Task Scheduler XML", command=self._export_task_xml, style="Secondary.TButton").pack(side="left", padx=(SPACE["sm"], 0))
        ttk.Label(task_frame, text="Exported tasks run actions one by one.", style="Helper.TLabel").pack(side="left", padx=(SPACE["sm"], 0))
        self.actions_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.actions_error, style="Error.TLabel").grid(row=9, column=0, sticky="w", pady=(3, 0))

        self.name.insert(0, str(self.shortcut.get("name", "")))
        self.folder.insert(0, shortcut_folder(self.shortcut))
        self._refresh_action_list(0 if self.actions else None)

    def initial_focus(self):
        return self.name

    def _selected_action_index(self):
        selection = self.action_list.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (TypeError, ValueError):
            return None

    def _refresh_action_list(self, selected=None):
        self.action_list.delete(*self.action_list.get_children())
        for index, action in enumerate(self.actions):
            mode = "Program/Script" if shortcut_action_mode(action) == ACTION_MODE_PROGRAM else "Command Line"
            self.action_list.insert("", "end", iid=str(index), values=(index + 1, action.get("name", ""), mode))
        if selected is not None and 0 <= selected < len(self.actions):
            self.action_list.selection_set(str(selected))
            self.action_list.focus(str(selected))
            self.action_list.see(str(selected))
        self._update_action_buttons()

    def _update_action_buttons(self):
        index = self._selected_action_index()
        selected = index is not None
        self.edit_action_button.state(["!disabled"] if selected else ["disabled"])
        self.clone_action_button.state(["!disabled"] if selected else ["disabled"])
        self.delete_action_button.state(["!disabled"] if selected and len(self.actions) > 1 else ["disabled"])
        self.up_action_button.state(["!disabled"] if selected and index > 0 else ["disabled"])
        self.down_action_button.state(["!disabled"] if selected and index < len(self.actions) - 1 else ["disabled"])

    def _add_action(self):
        self.actions.append({"name": "", "action_mode": ACTION_MODE_COMMAND_LINE, "command": "", "start_in": ""})
        self._refresh_action_list(len(self.actions) - 1)
        self._edit_action()

    def _edit_action(self, index=None, focus_field=None):
        selected = self._selected_action_index() if index is None else index
        if selected is None or not 0 <= selected < len(self.actions):
            return
        dialog = ActionDialog(
            self, "Edit Action", self.actions[selected], focus_field=focus_field,
        )
        if dialog.result:
            self.actions[selected] = dialog.result
            self.actions_error.set("")
            self._refresh_action_list(selected)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _clone_action(self):
        index = self._selected_action_index()
        if index is None or not 0 <= index < len(self.actions):
            return
        target = index + 1
        self.actions.insert(target, deepcopy(self.actions[index]))
        self.actions_error.set("")
        self._refresh_action_list(target)

    def _delete_action(self):
        index = self._selected_action_index()
        if index is None or len(self.actions) <= 1:
            return
        del self.actions[index]
        self._refresh_action_list(min(index, len(self.actions) - 1))

    def _move_action(self, offset):
        index = self._selected_action_index()
        target = index + offset if index is not None else -1
        if index is None or target < 0 or target >= len(self.actions):
            return
        self.actions[index], self.actions[target] = self.actions[target], self.actions[index]
        self._refresh_action_list(target)

    def _import_task_xml(self):
        selected = filedialog.askopenfilename(
            parent=self, title="Import Task Scheduler XML",
            filetypes=(("Task Scheduler XML", "*.xml"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            with open(selected, "rb") as task_file:
                values = parse_task_scheduler_shortcut_xml(task_file.read())
        except (OSError, TaskSchedulerError) as error:
            messagebox.showerror("Task Scheduler Import", str(error), parent=self)
            return
        self.actions = deepcopy(values["actions"])
        self.execution_mode.set(EXECUTION_MODE_SEQUENTIAL)
        if values["name"] and not self.name.get().strip():
            self._replace_entry(self.name, values["name"])
        self.actions_error.set("")
        self._refresh_action_list(0)

    def _export_task_xml(self):
        self.name_error.set("")
        self.actions_error.set("")
        try:
            values = normalize_shortcut_input(
                self.name.get(), folder=self.folder.get(),
                execution_mode=self.execution_mode.get(), actions=self.actions,
                existing=self.shortcut,
            )
            xml_text = build_task_scheduler_shortcut_xml(
                values["name"], values["actions"],
            )
        except (ValidationError, TaskSchedulerError) as error:
            if isinstance(error, ValidationError) and error.field == "name":
                self.name_error.set(str(error))
                self.name.focus_set()
            else:
                self.actions_error.set(str(error))
                self.action_list.focus_set()
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_ " else "_"
            for character in values["name"]
        ).strip() or "FlashCMD Task"
        destination = filedialog.asksaveasfilename(
            parent=self, title="Export Task Scheduler XML",
            defaultextension=".xml", initialfile=f"{safe_name}.xml",
            filetypes=(("Task Scheduler XML", "*.xml"), ("All files", "*.*")),
        )
        if not destination:
            return
        try:
            with open(destination, "w", encoding="utf-8", newline="\n") as task_file:
                task_file.write(xml_text)
                task_file.write("\n")
        except OSError as error:
            messagebox.showerror("Task Scheduler Export", str(error), parent=self)
            return
        messagebox.showinfo(
            "Task Scheduler Export",
            f"Exported {len(values['actions'])} actions to:\n{destination}",
            parent=self,
        )

    def _save(self):
        self.name_error.set("")
        self.actions_error.set("")
        try:
            self.result = normalize_shortcut_input(
                self.name.get(), folder=self.folder.get(),
                execution_mode=self.execution_mode.get(), actions=self.actions,
                existing=self.shortcut,
            )
        except ValidationError as error:
            if error.field == "name":
                self.name_error.set(str(error))
                self.name.focus_set()
                return
            self.actions_error.set(str(error))
            if error.field and error.field.startswith("actions["):
                try:
                    index = int(error.field.split("[", 1)[1].split("]", 1)[0])
                except (ValueError, IndexError):
                    index = 0
                self._refresh_action_list(index)
                field = error.field.rsplit(".", 1)[-1]
                self._edit_action(index, field)
            self.result = None
            return
        self.destroy()


class SettingsDialog(_Dialog):
    def __init__(
        self, parent, title, settings, shortcut_provider=None,
        shortcut_importer=None,
    ):
        self.settings = settings
        self.shortcut_provider = shortcut_provider or (lambda: ())
        self.shortcut_importer = shortcut_importer
        self.swatch_buttons = {}
        self._capture_modifiers = set()
        super().__init__(parent, title, 620, "Save settings", minimum_height=650)

    def _build(self):
        self.body.columnconfigure(0, weight=1)
        field_name = "Terminal executable" if is_windows() else "Shell executable"
        example = "cmd.exe" if is_windows() else "/bin/zsh"
        ttk.Label(self.body, text=field_name, style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.body, text=f"Use a command such as {example} or browse to an executable.", style="Helper.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 8))
        path_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        path_frame.grid(row=2, column=0, sticky="ew")
        path_frame.columnconfigure(0, weight=1)
        self.path = ttk.Entry(path_frame, style="Dialog.TEntry")
        self.path.grid(row=0, column=0, sticky="ew")
        self.path.insert(0, str(self.settings.get("terminal_path", DEFAULT_SETTINGS["terminal_path"])))
        ttk.Button(path_frame, text="Browse…", command=self._browse, style="Secondary.TButton").grid(row=0, column=1, padx=(SPACE["sm"], 0))
        self.path_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.path_error, style="Error.TLabel").grid(row=3, column=0, sticky="w", pady=(3, 0))

        ttk.Separator(self.body).grid(row=4, column=0, sticky="ew", pady=(14, 16))
        ttk.Label(self.body, text="Appearance", style="Dialog.TLabel", font=("Segoe UI", 11, "bold")).grid(row=5, column=0, sticky="w")
        ttk.Label(self.body, text="Choose the interface theme and primary action color.", style="Helper.TLabel").grid(row=6, column=0, sticky="w", pady=(2, 10))

        self.theme_var = tk.StringVar(value=self.settings.get("theme", "light") if self.settings.get("theme") in THEMES else "light")
        theme_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        theme_frame.grid(row=7, column=0, sticky="w")
        ttk.Radiobutton(theme_frame, text="Light", value="light", variable=self.theme_var, style="Dialog.TRadiobutton").pack(side="left")
        ttk.Radiobutton(theme_frame, text="Dark", value="dark", variable=self.theme_var, style="Dialog.TRadiobutton").pack(side="left", padx=(SPACE["sm"], 0))

        ttk.Label(self.body, text="Primary color", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, sticky="w", pady=(18, 2))
        ttk.Label(self.body, text="Used for primary buttons, selection borders, and focus accents.", style="Helper.TLabel").grid(row=9, column=0, sticky="w", pady=(0, 8))
        current_color = self.settings.get("primary_color", "blue")
        self.primary_var = tk.StringVar(value=current_color if current_color in PRIMARY_COLORS else "blue")
        swatch_frame = tk.Frame(self.body, bg=COLORS["card"])
        swatch_frame.grid(row=10, column=0, sticky="ew")
        for column in range(4):
            swatch_frame.columnconfigure(column, weight=1)
        for position, (key, (label, color)) in enumerate(PRIMARY_COLORS.items()):
            swatch = tk.Radiobutton(
                swatch_frame, text=label, value=key, variable=self.primary_var,
                command=self._update_swatch_states, indicatoron=False, width=9,
                bg=color, fg=COLORS["white"], activebackground=color,
                activeforeground=COLORS["white"], selectcolor=color,
                font=("Segoe UI", 9, "bold"), padx=7, pady=7,
                relief=tk.RAISED, offrelief=tk.RAISED, overrelief=tk.RIDGE,
                bd=1, highlightthickness=2, highlightbackground=COLORS["card"],
                highlightcolor=COLORS["text"], cursor="hand2", takefocus=True,
            )
            swatch.grid(row=position // 4, column=position % 4, sticky="ew", padx=4, pady=4)
            self.swatch_buttons[key] = swatch
        self._update_swatch_states()

        ttk.Separator(self.body).grid(row=11, column=0, sticky="ew", pady=(14, 16))
        ttk.Label(self.body, text="Global restore hotkey", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=12, column=0, sticky="w")
        ttk.Label(
            self.body,
            text=(
                f"Leave blank to disable. Click the field and press a shortcut such as Ctrl+Alt+F. "
                f"Use this to bring {APP_NAME} to the front."
            ),
            style="Helper.TLabel",
            wraplength=550,
        ).grid(row=13, column=0, sticky="w", pady=(2, 8))
        hotkey_frame = ttk.Frame(self.body, style="Dialog.TFrame")
        hotkey_frame.grid(row=14, column=0, sticky="ew")
        hotkey_frame.columnconfigure(0, weight=1)
        self.hotkey_var = tk.StringVar(value=str(self.settings.get("restore_hotkey", DEFAULT_SETTINGS["restore_hotkey"])))
        self.hotkey = ttk.Entry(hotkey_frame, textvariable=self.hotkey_var, style="Dialog.TEntry")
        self.hotkey.grid(row=0, column=0, sticky="ew")
        self.hotkey.bind("<KeyPress>", self._capture_hotkey_keypress, add="+")
        self.hotkey.bind("<KeyRelease>", self._capture_hotkey_keyrelease, add="+")
        self.hotkey.bind("<FocusOut>", self._reset_hotkey_capture, add="+")
        ttk.Button(hotkey_frame, text="Clear", command=self._clear_hotkey_capture, style="Secondary.TButton").grid(
            row=0, column=1, padx=(SPACE["sm"], 0),
        )
        self.hotkey_error = tk.StringVar()
        ttk.Label(self.body, textvariable=self.hotkey_error, style="Error.TLabel").grid(row=15, column=0, sticky="w", pady=(3, 0))

        ttk.Separator(self.body).grid(row=16, column=0, sticky="ew", pady=(14, 12))
        ttk.Label(self.body, text="Shortcut storage", style="Dialog.TLabel", font=("Segoe UI", 10, "bold")).grid(row=17, column=0, sticky="w")
        ttk.Label(
            self.body, text=CONFIG_FILE, style="Helper.TLabel", wraplength=550,
        ).grid(row=18, column=0, sticky="w", pady=(3, 0))
        storage_actions = ttk.Frame(self.body, style="Dialog.TFrame")
        storage_actions.grid(row=19, column=0, sticky="w", pady=(10, 0))
        ttk.Button(
            storage_actions, text="Download shortcuts…", command=self._export_shortcuts,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            storage_actions, text="Upload shortcuts…", command=self._import_shortcuts,
            style="Secondary.TButton",
        ).pack(side="left", padx=(SPACE["sm"], 0))
        self.storage_status = tk.StringVar()
        ttk.Label(
            self.body, textvariable=self.storage_status, style="Helper.TLabel",
            wraplength=550,
        ).grid(row=20, column=0, sticky="w", pady=(5, 0))

    def initial_focus(self):
        return self.path

    def _browse(self):
        current = self.path.get().strip()
        options = {
            "parent": self,
            "title": "Choose terminal executable" if is_windows() else "Choose shell executable",
            "filetypes": (
                (("Applications", "*.exe"), ("All files", "*.*"))
                if is_windows() else (("Executable files", "*"), ("All files", "*"))
            ),
        }
        if current and os.path.isfile(current):
            options["initialdir"] = os.path.dirname(current)
        selected = filedialog.askopenfilename(**options)
        if selected:
            self.path.delete(0, tk.END)
            self.path.insert(0, selected)
            self.path_error.set("")

    def _export_shortcuts(self):
        destination = filedialog.asksaveasfilename(
            parent=self, title="Download shortcuts", defaultextension=".json",
            initialfile="FlashCMD-shortcuts.json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not destination:
            return
        payload = {
            "application": APP_NAME, "version": __version__,
            "shortcuts": deepcopy(list(self.shortcut_provider())),
        }
        try:
            with open(destination, "w", encoding="utf-8", newline="\n") as export_file:
                json.dump(payload, export_file, ensure_ascii=False, indent=2)
                export_file.write("\n")
        except (OSError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Download Shortcuts", f"Shortcuts could not be downloaded:\n\n{error}",
                parent=self,
            )
            return
        self.storage_status.set(f"Downloaded {len(payload['shortcuts'])} shortcuts.")

    def _import_shortcuts(self):
        source = filedialog.askopenfilename(
            parent=self, title="Upload shortcuts",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not source:
            return
        try:
            with open(source, "r", encoding="utf-8") as import_file:
                shortcuts = normalize_shortcut_collection(json.load(import_file))
        except (ConfigError, JSONDecodeError, OSError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Upload Shortcuts", f"The selected file is not a valid shortcut backup:\n\n{error}",
                parent=self,
            )
            return
        existing_count = len(list(self.shortcut_provider()))
        confirmed = messagebox.askyesno(
            "Replace all shortcuts?",
            f"This will replace all {existing_count} existing shortcuts with "
            f"{len(shortcuts)} uploaded shortcuts.\n\nThis cannot be undone. Continue?",
            parent=self,
        )
        if not confirmed:
            return
        if self.shortcut_importer is None or not self.shortcut_importer(shortcuts):
            self.storage_status.set("Shortcuts were not replaced.")
            return
        self.storage_status.set(f"Replaced shortcuts with {len(shortcuts)} uploaded shortcuts.")

    def _update_swatch_states(self):
        selected = self.primary_var.get()
        for key, button in self.swatch_buttons.items():
            button.configure(
                relief=tk.SUNKEN if key == selected else tk.RAISED,
                highlightbackground=COLORS["text"] if key == selected else COLORS["card"],
            )

    def _reset_hotkey_capture(self, _event=None):
        self._capture_modifiers.clear()

    def _clear_hotkey_capture(self):
        self._capture_modifiers.clear()
        self.hotkey_var.set("")
        self.hotkey_error.set("")
        self.hotkey.focus_set()

    def _capture_hotkey_keypress(self, event):
        modifier = hotkey_modifier_from_keysym(event.keysym)
        if modifier:
            self._capture_modifiers.add(modifier)
            self.hotkey_error.set("")
            return "break"
        if event.keysym in ("BackSpace", "Delete"):
            self._clear_hotkey_capture()
            return "break"
        try:
            captured = capture_restore_hotkey(event.keysym, self._capture_modifiers)
            captured, _expression = parse_restore_hotkey(captured)
        except ValueError as error:
            self.hotkey_error.set(str(error))
            return "break"
        self.hotkey_var.set(captured)
        self.hotkey_error.set("")
        return "break"

    def _capture_hotkey_keyrelease(self, event):
        modifier = hotkey_modifier_from_keysym(event.keysym)
        if modifier:
            self._capture_modifiers.discard(modifier)
            return "break"
        return None

    def _save(self):
        self.path_error.set("")
        self.hotkey_error.set("")
        path = self.path.get().strip()
        noun = "terminal" if is_windows() else "shell"
        if not path:
            self.path_error.set(f"Enter a {noun} command or executable path.")
            self.path.focus_set()
            return
        if not executable_path_is_valid(path):
            self.path_error.set(f"The {noun} could not be found or is not executable.")
            self.path.focus_set()
            return
        try:
            hotkey, _expression = parse_restore_hotkey(self.hotkey_var.get())
        except ValueError as error:
            self.hotkey_error.set(str(error))
            self.hotkey.focus_set()
            return
        self.result = {
            "terminal_path": path,
            "theme": self.theme_var.get(),
            "primary_color": self.primary_var.get(),
            "restore_hotkey": hotkey,
        }
        self.destroy()


TerminalDialog = SettingsDialog

class ShortcutManager:
    def __init__(self, root, instance_endpoint=None):
        self.root = root
        self.instance_endpoint = instance_endpoint
        self.shortcuts = []
        self.settings = dict(DEFAULT_SETTINGS)
        self.selected_index = None
        self.matched_pairs = []
        self.visible_pairs = []
        self.cards = {}
        self.collapsed_folders = set()
        self.status_timer = None
        self._last_save_error = ""
        self.tray_icon = None
        self.tray_thread = None
        self.hotkey_listener = None
        self.active_restore_hotkey = ""
        self._tray_actions = queue.Queue() if is_windows() else None
        self._ui_events = queue.Queue()
        self._active_runs = {}
        self._exiting = False
        self.search_var = tk.StringVar()
        self.compact_cards_var = tk.BooleanVar(value=False)
        self.count_var = tk.StringVar()
        self.status_var = tk.StringVar()
        ensure_icon()
        self._configure_window()
        loaded = self.load()
        set_appearance(
            self.settings.get("theme", "light"),
            self.settings.get("primary_color", "blue"),
        )
        self.root.configure(bg=COLORS["background"])
        configure_styles(root)
        self._build_header()
        self.main = ttk.Frame(root, padding=(SPACE["xl"], SPACE["lg"]), style="App.TFrame")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_shortcut_area()
        self._build_action_bar()
        self.status_label = ttk.Label(root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        self.status_label.grid(row=2, column=0, sticky="ew")
        self._bind_shortcuts()
        if self.instance_endpoint is not None:
            self.instance_endpoint.set_restore_callback(self._queue_restore_request)
        if is_windows():
            self.root.after(100, self._process_tray_actions)
        self.root.after(100, self._process_ui_events)
        self.search_var.trace_add("write", self._on_search_changed)
        self.refresh_cards(preserve_selection=False)
        if not loaded:
            self._set_status("Configuration could not be loaded", transient=True)
        hotkey_error = self._apply_restore_hotkey(notify=False)
        if hotkey_error:
            self._set_status(hotkey_error, transient=True)

    def _configure_window(self):
        self.root.title(APP_NAME)
        self.root.configure(bg=COLORS["background"])
        self.root.minsize(680, 520)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.root.protocol(
            "WM_DELETE_WINDOW", self.hide_to_tray if is_windows() else self.exit_application,
        )
        if is_windows():
            self.root.bind("<Unmap>", self._on_window_unmap, add="+")
        elif is_macos():
            self.root.createcommand("tk::mac::Quit", self.exit_application)
        apply_window_icon(self.root)
        width, height = 820, 640
        left, top, right, bottom = 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if is_windows():
            try:
                class Rect(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                work_area = Rect()
                if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0):
                    left, top, right, bottom = work_area.left, work_area.top, work_area.right, work_area.bottom
            except (AttributeError, OSError):
                pass
        x = left + max(0, (right - left - width) // 2)
        y = top + max(0, (bottom - top - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _on_window_unmap(self, event):
        if event.widget is self.root and not self._exiting:
            self.root.after(50, self._hide_if_minimized)

    def _hide_if_minimized(self):
        try:
            if self.root.state() == "iconic":
                self.hide_to_tray()
        except tk.TclError:
            pass

    def _ensure_tray_icon(self):
        if not is_windows():
            return
        if self.tray_icon is not None:
            return
        with Image.open(APP_ICON_FILE) as source:
            tray_image = source.convert("RGBA")
        menu = pystray.Menu(
            pystray.MenuItem(f"Open {APP_NAME}", self._request_tray_restore, default=True),
            pystray.MenuItem("Exit", self._request_tray_exit),
        )
        self.tray_icon = pystray.Icon("flashcmd", tray_image, APP_NAME, menu)
        self.tray_thread = threading.Thread(
            target=self.tray_icon.run, name="FlashCMDTray", daemon=True,
        )
        self.tray_thread.start()

    def hide_to_tray(self):
        if not is_windows():
            self.exit_application()
            return "break"
        if self._exiting:
            return "break"
        try:
            self._ensure_tray_icon()
        except Exception as error:
            messagebox.showerror(
                "System Tray Error", f"{APP_NAME} could not start its tray icon:\n\n{error}",
                parent=self.root,
            )
            return "break"
        self.root.withdraw()
        return "break"

    def _request_tray_restore(self, _icon=None, _item=None):
        self._tray_actions.put("restore")

    def _request_tray_exit(self, _icon=None, _item=None):
        self._tray_actions.put("exit")

    def _process_tray_actions(self):
        if not is_windows() or self._tray_actions is None:
            return
        try:
            while True:
                action = self._tray_actions.get_nowait()
                if action == "restore":
                    self.restore_from_tray()
                elif action == "exit":
                    self.exit_application()
                    return
        except queue.Empty:
            pass
        if not self._exiting:
            self.root.after(100, self._process_tray_actions)

    def restore_from_tray(self):
        if self._exiting:
            return
        try:
            self.root.deiconify()
            self.root.state("normal")
        except tk.TclError:
            return
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(150, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def exit_application(self):
        if self._exiting:
            return
        self._exiting = True
        self._stop_restore_hotkey_listener()
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        for cancel_event in self._active_runs.values():
            cancel_event.set()
        self._active_runs.clear()
        self.root.destroy()

    def _queue_restore_request(self):
        if self._exiting:
            return
        try:
            self.root.after(0, self.restore_from_tray)
        except tk.TclError:
            pass

    def _stop_restore_hotkey_listener(self):
        if self.hotkey_listener is None:
            return
        try:
            self.hotkey_listener.stop()
        except Exception:
            pass
        self.hotkey_listener = None
        self.active_restore_hotkey = ""

    def _hotkey_error_message(self, error):
        detail = str(error)
        if is_macos():
            return (
                f"Restore hotkey unavailable: {detail}\n\n"
                "macOS may require Accessibility permission for global keyboard monitoring."
            )
        return f"Restore hotkey unavailable: {detail}"

    def _apply_restore_hotkey(self, notify=False):
        self._stop_restore_hotkey_listener()
        hotkey = self.settings.get("restore_hotkey", "")
        try:
            display, expression = parse_restore_hotkey(hotkey)
        except ValueError as error:
            message = f"Restore hotkey disabled: {error}"
            if notify:
                messagebox.showwarning("Restore Hotkey", message, parent=self.root)
            return message
        if not expression:
            self.settings["restore_hotkey"] = ""
            return None
        keyboard_module, import_error = _load_hotkey_backend()
        if keyboard_module is None:
            message = self._hotkey_error_message(import_error or "pynput could not be imported.")
            if notify:
                messagebox.showwarning("Restore Hotkey", message, parent=self.root)
            return message
        try:
            self.hotkey_listener = create_restore_hotkey_listener(
                expression, self._queue_restore_request, keyboard_module,
            )
        except Exception as error:
            message = self._hotkey_error_message(error)
            if notify:
                messagebox.showwarning("Restore Hotkey", message, parent=self.root)
            return message
        self.settings["restore_hotkey"] = display
        self.active_restore_hotkey = display
        return None

    def _build_header(self):
        self.header = tk.Frame(self.root, bg=COLORS["header"], padx=SPACE["xl"], pady=15)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.columnconfigure(1, weight=1)
        with Image.open(HEADER_ICON_FILE) as icon_source:
            resized_icon = icon_source.convert("RGBA").resize((48, 48), Image.Resampling.LANCZOS)
        self.header_icon_image = ImageTk.PhotoImage(resized_icon)
        self.header_icon_label = tk.Label(
            self.header, image=self.header_icon_image, bg=COLORS["header"],
            bd=0, highlightthickness=0,
        )
        self.header_icon_label.grid(row=0, column=0, rowspan=2, padx=(0, SPACE["md"]))
        self.header_title = tk.Label(self.header, text=APP_NAME, bg=COLORS["header"], fg=COLORS["white"], font=FONTS["title"], anchor="w")
        self.header_title.grid(row=0, column=1, sticky="sw")
        self.header_subtitle = tk.Label(self.header, text="Launch saved commands without the repetitive setup.", bg=COLORS["header"], fg=COLORS["header_subtext"], font=FONTS["small"], anchor="w")
        self.header_subtitle.grid(row=1, column=1, sticky="nw")
        self.header_actions = tk.Frame(self.header, bg=COLORS["header"])
        self.header_actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self.header_actions.columnconfigure(0, weight=0)
        self.header_actions.columnconfigure(1, weight=0)
        with Image.open(BMC_BUTTON_FILE) as support_source:
            support_image = support_source.convert("RGBA")
            width, height = support_image.size
            target_height = 40
            target_width = max(1, round(width * (target_height / max(1, height))))
            resized_support = support_image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        self.support_button_image = ImageTk.PhotoImage(resized_support)
        self.support_button = tk.Button(
            self.header_actions, image=self.support_button_image,
            command=self.open_buy_me_a_coffee, cursor="hand2",
            bg=COLORS["header"], activebackground=COLORS["header"],
            bd=0, highlightthickness=0, relief="flat", takefocus=True,
        )
        self.support_button.grid(row=0, column=0, sticky="e")
        self.settings_button = ttk.Button(
            self.header_actions, text="⚙", width=2,
            command=self.open_settings, style="HeaderIcon.TButton",
        )
        self.settings_button.grid(row=0, column=1, sticky="e", padx=(SPACE["sm"], 0))

    def open_buy_me_a_coffee(self):
        try:
            webbrowser.open_new_tab(BUY_ME_A_COFFEE_URL)
        except Exception as error:
            messagebox.showerror(
                "Open link", f"{APP_NAME} could not open the support link:\n\n{error}",
                parent=self.root,
            )

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.main, style="App.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))
        toolbar.columnconfigure(0, weight=1)
        title_area = ttk.Frame(toolbar, style="App.TFrame")
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Shortcuts", style="Heading.TLabel").pack(side="left")
        ttk.Label(title_area, textvariable=self.count_var, style="Secondary.TLabel").pack(side="left", padx=(SPACE["sm"], 0), pady=(4, 0))
        search_area = ttk.Frame(toolbar, style="App.TFrame")
        search_area.grid(row=0, column=1, sticky="e", padx=(SPACE["md"], SPACE["sm"]))
        ttk.Label(search_area, text="Search", style="Secondary.TLabel").pack(side="left", padx=(0, 6))
        self.search_entry = ttk.Entry(search_area, textvariable=self.search_var, width=25, style="Search.TEntry")
        self.search_entry.pack(side="left")
        self.clear_search_button = ttk.Button(search_area, text="×", width=2, command=self.clear_search, style="Ghost.TButton")
        self.clear_search_button.pack(side="left", padx=(2, 0))
        self.compact_cards_toggle = ttk.Checkbutton(
            search_area, text="▦", width=2, variable=self.compact_cards_var,
            command=self._toggle_compact_cards, style="CompactToggle.Toolbutton",
            cursor="hand2", takefocus=True,
        )
        self.compact_cards_toggle.pack(side="left", padx=(SPACE["sm"], 0))
        self.clone_button = ttk.Button(toolbar, text="Clone", command=self.clone, style="Secondary.TButton")
        self.clone_button.grid(row=0, column=2, sticky="e", padx=(0, SPACE["sm"]))
        self.add_button = ttk.Button(toolbar, text="+ Add shortcut", command=self.add, style="Primary.TButton")
        self.add_button.grid(row=0, column=3, sticky="e")

    def _build_shortcut_area(self):
        self.card_list = ScrollableCardList(self.main)
        self.card_list.grid(row=1, column=0, sticky="nsew")
        self.shortcut_context_menu = tk.Menu(self.root, tearoff=False)
        self.shortcut_context_menu.add_command(label="Run", command=self.run)
        self.shortcut_context_menu.add_command(label="Edit", command=self.edit)
        self.shortcut_context_menu.add_command(label="Clone", command=self.clone)
        self.shortcut_context_menu.add_separator()
        self.shortcut_context_menu.add_command(label="Delete", command=self.delete)

    def _show_shortcut_context(self, event, source_index):
        self.select_shortcut(source_index)
        try:
            self.shortcut_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.shortcut_context_menu.grab_release()

    def _build_action_bar(self):
        action_bar = ttk.Frame(self.main, style="App.TFrame")
        action_bar.grid(row=2, column=0, sticky="ew", pady=(SPACE["md"], 0))
        action_bar.columnconfigure(2, weight=1)
        self.edit_button = ttk.Button(action_bar, text="Edit", command=self.edit, style="Secondary.TButton")
        self.edit_button.grid(row=0, column=0, sticky="w", padx=(0, SPACE["sm"]))
        self.delete_button = ttk.Button(action_bar, text="Delete", command=self.delete, style="Danger.TButton")
        self.delete_button.grid(row=0, column=1, sticky="w")
        self.run_button = ttk.Button(action_bar, text="Run selected", command=self.run, style="Primary.TButton")
        self.run_button.grid(row=0, column=3, sticky="e")

    def _bind_shortcuts(self):
        self.root.bind("<Control-n>", lambda _event: self.add() or "break")
        self.root.bind("<Control-f>", self._focus_search)
        self.root.bind("<Control-comma>", lambda _event: self.open_settings() or "break")
        self.root.bind("<Up>", lambda _event: self._move_selection(-1))
        self.root.bind("<Down>", lambda _event: self._move_selection(1))
        self.root.bind("<Return>", self._run_from_keyboard)
        self.root.bind("<F2>", lambda _event: self.edit() or "break")
        self.root.bind("<Delete>", self._delete_from_keyboard)
        self.root.bind("<Escape>", self._escape)
        if is_macos():
            self.root.bind("<Command-q>", lambda _event: self.exit_application() or "break")

    def load(self):
        source_path = next(
            (candidate for candidate in CONFIG_CANDIDATES if os.path.exists(candidate)),
            CONFIG_FILE,
        )
        try:
            data = load_config(source_path, platform=PLATFORM)
        except (ConfigError, JSONDecodeError, OSError) as error:
            self.shortcuts = []
            self.settings = dict(DEFAULT_SETTINGS)
            messagebox.showerror("Configuration Error", f"{APP_NAME} could not load {source_path}:\n\n{error}", parent=self.root)
            return False
        self.shortcuts = data["shortcuts"]
        self.settings = data["settings"]
        self.loaded_config_file = source_path
        return True

    def save(self):
        self._last_save_error = ""
        try:
            save_config(CONFIG_FILE, self.shortcuts, self.settings)
        except (ConfigError, OSError, TypeError, ValueError) as error:
            self._last_save_error = str(error)
            self._set_status("Changes could not be saved", transient=True)
            messagebox.showerror("Save Error", f"{APP_NAME} could not save {CONFIG_FILE}:\n\n{error}", parent=self.root)
            return False
        self.loaded_config_file = CONFIG_FILE
        return True

    def refresh_cards(self, preserve_selection=True):
        prior_selection = self.selected_index if preserve_selection else None
        self.matched_pairs = filter_shortcuts(self.shortcuts, self.search_var.get())
        self.visible_pairs = []
        self.card_list.clear()
        self.cards = {}
        if self.matched_pairs:
            matching_shortcuts = [shortcut for _index, shortcut in self.matched_pairs]
            for folder in unique_shortcut_folders(matching_shortcuts):
                pairs = [
                    pair for pair in self.matched_pairs
                    if shortcut_folder(pair[1]).casefold() == folder.casefold()
                ]
                self._build_folder_group(folder, pairs)
        else:
            self._build_empty_state()
        visible_indexes = {index for index, _shortcut in self.visible_pairs}
        self.selected_index = prior_selection if prior_selection in visible_indexes else None
        for index, card in self.cards.items():
            card.set_visual_state(index == self.selected_index, False)
        self._update_action_states()
        self._update_count()
        self._set_status()

    def _build_folder_group(self, folder, pairs):
        key = folder.casefold()
        collapsed = key in self.collapsed_folders
        section = tk.Frame(self.card_list.interior, bg=COLORS["background"])
        section.pack(fill="x", pady=(0, SPACE["sm"]))
        header = tk.Button(
            section, text=f"{'▸' if collapsed else '▾'}  {folder}  ({len(pairs)})",
            command=lambda: self._toggle_folder(folder), anchor="w", cursor="hand2",
            bg=COLORS["background"], fg=COLORS["text"], activebackground=COLORS["hover"],
            activeforeground=COLORS["text"], font=FONTS["folder"], relief="flat",
            bd=0, padx=SPACE["xs"], pady=SPACE["xs"], highlightthickness=0,
        )
        header.pack(fill="x", padx=(SPACE["xs"], SPACE["sm"]))
        header.bind("<Enter>", self.card_list._enable_wheel, add="+")
        if collapsed:
            return
        card_area = tk.Frame(section, bg=COLORS["background"])
        card_area.pack(fill="x")
        for source_index, shortcut in pairs:
            card = ShortcutCard(
                card_area, source_index, shortcut, self.select_shortcut, self.edit,
                self._show_shortcut_context, compact=self.compact_cards_var.get(),
            )
            card.pack(fill="x", padx=(SPACE["md"], SPACE["sm"]), pady=(0, SPACE["xs"]))
            for child in (card, *card.winfo_children()):
                child.bind("<Enter>", self.card_list._enable_wheel, add="+")
            self.cards[source_index] = card
            self.visible_pairs.append((source_index, shortcut))

    def _toggle_folder(self, folder):
        key = folder.casefold()
        if key in self.collapsed_folders:
            self.collapsed_folders.remove(key)
        else:
            self.collapsed_folders.add(key)
        self.refresh_cards(preserve_selection=True)

    def _toggle_compact_cards(self):
        self.refresh_cards(preserve_selection=True)

    def _build_empty_state(self):
        self.card_list.set_empty(True)
        empty = tk.Frame(self.card_list.interior, bg=COLORS["background"])
        empty.pack(fill="both", expand=True)
        content = tk.Frame(empty, bg=COLORS["background"])
        content.place(relx=0.5, rely=0.46, anchor="center")
        if not self.shortcuts:
            title, detail, button_text, command = (
                "No shortcuts yet", "Add a saved command to get started.",
                "+ Add shortcut", self.add,
            )
        else:
            title, detail, button_text, command = (
                "No shortcuts match the current search",
                "Try a different name, folder, command, or working directory.",
                "Clear search", self.clear_search,
            )
        tk.Label(content, text=title, bg=COLORS["background"], fg=COLORS["text"], font=FONTS["heading"], wraplength=520).pack()
        tk.Label(content, text=detail, bg=COLORS["background"], fg=COLORS["secondary"], font=FONTS["body"]).pack(pady=(5, 12))
        ttk.Button(content, text=button_text, command=command, style="Primary.TButton").pack()

    def select_shortcut(self, source_index):
        if source_index not in {index for index, _shortcut in self.visible_pairs}:
            self.selected_index = None
        else:
            self.selected_index = source_index
        for index, card in self.cards.items():
            card.set_visual_state(index == self.selected_index, card.hovered)
        self._update_action_states()

    def _selected_shortcut(self):
        visible_indexes = {index for index, _shortcut in self.visible_pairs}
        if self.selected_index is None or self.selected_index not in visible_indexes:
            return None
        if not 0 <= self.selected_index < len(self.shortcuts):
            return None
        return self.shortcuts[self.selected_index]

    def _update_action_states(self):
        state = ["!disabled"] if self._selected_shortcut() is not None else ["disabled"]
        for button in (self.run_button, self.edit_button, self.clone_button, self.delete_button):
            button.state(state)

    def _count_message(self):
        total, visible = len(self.shortcuts), len(self.matched_pairs)
        noun = "shortcut" if total == 1 else "shortcuts"
        if self.search_var.get().strip():
            return f"{visible} of {total} {noun}"
        return f"{total} {noun}"

    def _update_count(self):
        self.count_var.set(self._count_message())
        self.clear_search_button.state(["!disabled"] if self.search_var.get() else ["disabled"])

    def _set_status(self, message=None, transient=False):
        if self.status_timer is not None:
            self.root.after_cancel(self.status_timer)
            self.status_timer = None
        count = self._count_message()
        self.status_var.set(f"{count}  •  {message}" if message else count)
        if message and transient:
            self.status_timer = self.root.after(4500, self._restore_status)

    def _restore_status(self):
        self.status_timer = None
        self.status_var.set(self._count_message())

    def _on_search_changed(self, *_args):
        self.refresh_cards(preserve_selection=True)

    def clear_search(self):
        if self.search_var.get():
            self.search_var.set("")
        else:
            self.search_entry.focus_set()

    def _focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _move_selection(self, direction):
        indexes = [index for index, _shortcut in self.visible_pairs]
        if not indexes:
            return "break"
        if self.selected_index not in indexes:
            position = 0 if direction > 0 else len(indexes) - 1
        else:
            position = max(0, min(indexes.index(self.selected_index) + direction, len(indexes) - 1))
        source_index = indexes[position]
        self.select_shortcut(source_index)
        card = self.cards[source_index]
        card.focus_set()
        self.root.update_idletasks()
        top = card.winfo_rooty() - self.card_list.interior.winfo_rooty()
        bottom = top + card.winfo_height()
        view_top = self.card_list.canvas.canvasy(0)
        view_bottom = view_top + self.card_list.canvas.winfo_height()
        total_height = max(1, self.card_list.interior.winfo_height())
        if top < view_top:
            self.card_list.canvas.yview_moveto(top / total_height)
        elif bottom > view_bottom:
            self.card_list.canvas.yview_moveto(max(0, (bottom - self.card_list.canvas.winfo_height()) / total_height))
        return "break"

    def _run_from_keyboard(self, _event=None):
        if isinstance(self.root.focus_get(), tk.Text):
            return None
        if self._selected_shortcut() is not None:
            self.run()
        return "break"

    def _delete_from_keyboard(self, _event=None):
        focus = self.root.focus_get()
        if focus is not None and focus.winfo_class() in ("Entry", "TEntry", "Text"):
            return None
        if self._selected_shortcut() is not None:
            self.delete()
        return "break"

    def _escape(self, _event=None):
        if self.search_var.get():
            self.search_var.set("")
        elif self.selected_index is not None:
            self.selected_index = None
            for card in self.cards.values():
                card.set_visual_state(False, card.hovered)
            self._update_action_states()
        return "break"

    def add(self):
        dialog = ShortcutDialog(
            self.root, "Add Shortcut", available_folders=unique_shortcut_folders(self.shortcuts),
        )
        if not dialog.result:
            return
        self.shortcuts.append(dialog.result)
        self.selected_index = len(self.shortcuts) - 1
        saved = self.save()
        self.refresh_cards(preserve_selection=True)
        name = dialog.result.get("name", "shortcut")
        self._set_status(f"Added {name}" if saved else "Added locally, but changes were not saved", transient=True)

    def edit(self):
        shortcut = self._selected_shortcut()
        if shortcut is None:
            messagebox.showwarning("Selection Required", "Select a shortcut to edit.", parent=self.root)
            return
        source_index = self.selected_index
        dialog = ShortcutDialog(
            self.root, "Edit Shortcut", shortcut, unique_shortcut_folders(self.shortcuts),
        )
        if not dialog.result:
            return
        self.shortcuts[source_index] = dialog.result
        saved = self.save()
        self.refresh_cards(preserve_selection=True)
        name = dialog.result.get("name", "shortcut")
        self._set_status(f"Updated {name}" if saved else "Updated locally, but changes were not saved", transient=True)

    def clone(self):
        shortcut = self._selected_shortcut()
        if shortcut is None:
            messagebox.showwarning(
                "Selection Required", "Select a shortcut to clone.", parent=self.root,
            )
            return
        original_name = str(shortcut.get("name", "Shortcut")).strip() or "Shortcut"
        new_name = simpledialog.askstring(
            "Clone Shortcut", "Enter a name for the cloned shortcut:",
            initialvalue=f"{original_name} Copy", parent=self.root,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning(
                "Clone Shortcut", "Enter a name for the cloned shortcut.",
                parent=self.root,
            )
            return
        cloned = deepcopy(shortcut)
        cloned["name"] = new_name
        self.shortcuts.append(cloned)
        self.selected_index = len(self.shortcuts) - 1
        saved = self.save()
        self.refresh_cards(preserve_selection=True)
        self._set_status(
            f"Cloned {original_name} as {new_name}"
            if saved else "Cloned locally, but changes were not saved",
            transient=True,
        )

    def delete(self):
        shortcut = self._selected_shortcut()
        if shortcut is None:
            messagebox.showwarning("Selection Required", "Select a shortcut to delete.", parent=self.root)
            return
        name = str(shortcut.get("name", "this shortcut"))
        confirmed = messagebox.askyesno(
            "Delete Shortcut", f"Delete “{name}”?\n\nThis removes it from your saved shortcuts.",
            icon="warning", parent=self.root,
        )
        if not confirmed:
            return
        visible_indexes = [index for index, _shortcut in self.visible_pairs]
        old_position = visible_indexes.index(self.selected_index)
        del self.shortcuts[self.selected_index]
        self.selected_index = None
        saved = self.save()
        self.refresh_cards(preserve_selection=False)
        if self.visible_pairs:
            position = min(old_position, len(self.visible_pairs) - 1)
            self.select_shortcut(self.visible_pairs[position][0])
        self._set_status(f"Deleted {name}" if saved else "Deleted locally, but changes were not saved", transient=True)

    def open_settings(self):
        dialog = SettingsDialog(
            self.root, "Settings", self.settings,
            shortcut_provider=lambda: self.shortcuts,
            shortcut_importer=self._replace_shortcuts_from_import,
        )
        if not dialog.result:
            return
        self.settings.update(dialog.result)
        saved = self.save()
        self._apply_appearance()
        hotkey_error = self._apply_restore_hotkey(notify=True)
        self.refresh_cards(preserve_selection=True)
        message = "Settings saved" if saved else "Settings changed locally, but were not saved"
        if hotkey_error:
            message = "Settings saved, but the restore hotkey is unavailable" if saved else "Settings changed locally, but the restore hotkey is unavailable"
        self._set_status(message, transient=True)

    def _replace_shortcuts_from_import(self, shortcuts):
        previous_shortcuts = self.shortcuts
        previous_selection = self.selected_index
        self.shortcuts = deepcopy(shortcuts)
        self.selected_index = None
        if not self.save():
            self.shortcuts = previous_shortcuts
            self.selected_index = previous_selection
            return False
        self.refresh_cards(preserve_selection=False)
        self._set_status(f"Imported {len(self.shortcuts)} shortcuts", transient=True)
        return True

    def terminal_settings(self):
        """Backward-compatible entry point for opening the combined settings."""
        return self.open_settings()

    def _apply_appearance(self):
        theme, primary = set_appearance(
            self.settings.get("theme", "light"),
            self.settings.get("primary_color", "blue"),
        )
        self.settings["theme"], self.settings["primary_color"] = theme, primary
        configure_styles(self.root)
        self.root.configure(bg=COLORS["background"])
        self.header.configure(bg=COLORS["header"])
        self.header_actions.configure(bg=COLORS["header"])
        self.header_icon_label.configure(bg=COLORS["header"])
        self.header_title.configure(bg=COLORS["header"], fg=COLORS["white"])
        self.header_subtitle.configure(bg=COLORS["header"], fg=COLORS["header_subtext"])
        self.support_button.configure(bg=COLORS["header"], activebackground=COLORS["header"])
        self.card_list.apply_appearance()

    def _run_shortcut_worker(
        self, run_id, shortcut_name, terminal_path, actions, execution_mode,
        cancel_event,
    ):
        def progress(event):
            self._ui_events.put(("progress", shortcut_name, event))

        try:
            result = launch_shortcut(
                terminal_path, actions, execution_mode, platform=PLATFORM,
                run_id=run_id, cancel_event=cancel_event,
                on_progress=progress,
            )
        except Exception as error:
            self._ui_events.put(("error", run_id, shortcut_name, str(error)))
        else:
            self._ui_events.put(("result", run_id, shortcut_name, result))

    def _process_ui_events(self):
        if self._exiting:
            return
        while True:
            try:
                event = self._ui_events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "progress":
                _kind, shortcut_name, progress = event
                if progress.phase == "launching":
                    message = f"Launching {shortcut_name}: 0/{progress.total} completed"
                elif progress.phase == "completed":
                    message = f"Finishing {shortcut_name}: {progress.completed}/{progress.total} completed"
                else:
                    message = f"Running {shortcut_name}: {progress.completed}/{progress.total} completed"
                self._set_status(message)
            elif kind == "error":
                _kind, run_id, shortcut_name, detail = event
                self._active_runs.pop(run_id, None)
                self._set_status(f"{shortcut_name} could not be launched", transient=True)
                messagebox.showerror("Execution Error", detail, parent=self.root)
            elif kind == "result":
                _kind, run_id, shortcut_name, result = event
                self._active_runs.pop(run_id, None)
                if result.failures:
                    lines = [
                        f"• {failure.name}: {failure.detail or failure.status.replace('_', ' ')}"
                        for failure in result.failures
                    ]
                    self._set_status(
                        f"{shortcut_name} completed with {len(result.failures)} failure(s)",
                        transient=True,
                    )
                    messagebox.showerror(
                        "Shortcut completed with failures",
                        f"{shortcut_name} completed, but these actions failed:\n\n" + "\n".join(lines),
                        parent=self.root,
                    )
                else:
                    message = f"Completed {shortcut_name} ({len(result.actions)} actions)"
                    if result.fallback_used:
                        message += " using console fallback"
                    self._set_status(message, transient=True)
        if not self._exiting:
            self.root.after(100, self._process_ui_events)

    def run(self):
        item = self._selected_shortcut()
        if item is None:
            messagebox.showwarning("Selection Required", "Select a shortcut to run.", parent=self.root)
            return
        try:
            actions = shortcut_actions(item)
        except ValidationError as error:
            self._set_status("Shortcut actions are invalid", transient=True)
            messagebox.showerror("Execution Error", str(error), parent=self.root)
            return
        run_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        self._active_runs[run_id] = cancel_event
        shortcut_name = str(item.get("name", "shortcut")).strip() or "shortcut"
        worker = threading.Thread(
            target=self._run_shortcut_worker,
            args=(
                run_id, shortcut_name,
                self.settings.get("terminal_path", DEFAULT_SETTINGS["terminal_path"]),
                deepcopy(actions), shortcut_execution_mode(item),
                cancel_event,
            ),
            daemon=True,
        )
        worker.start()
        self._set_status(f"Launching {shortcut_name}: 0/{len(actions)} completed")

def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(f"{APP_NAME} {__version__}")
        return 0
    try:
        endpoint = SingleInstanceEndpoint(instance_port())
    except OSError:
        try:
            notify_existing_instance(instance_port())
            return 0
        except OSError as error:
            print(f"{APP_NAME} could not contact its running instance: {error}", file=sys.stderr)
            return 1
    try:
        root = tk.Tk()
        ShortcutManager(root, instance_endpoint=endpoint)
        root.mainloop()
        return 0
    finally:
        endpoint.close()


if __name__ == "__main__":
    raise SystemExit(main())


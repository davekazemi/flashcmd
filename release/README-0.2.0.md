# FlashCMD 0.2.0

FlashCMD is a desktop shortcut manager for Windows and macOS. It lets you save,
organize, search, clone, and launch ordered collections of commands, programs,
and scripts.

## Release files

- `FlashCMD-0.2.0-windows-x64.msi` — recommended Windows installer
- `FlashCMD-0.2.0-windows-x64.exe` — portable Windows application
- `FlashCMD-0.2.0-macos-<architecture>.dmg` — macOS package when available

## Highlights

- Optional colors belong to individual actions
- Shortcut card accents use the first valid action color in execution order
- Windows Terminal command tabs use each action's own color in sequential and
  parallel runs
- Program/Script actions still launch directly and never create Terminal tabs
- Legacy 0.1.0 shortcut colors retain their appearance through lazy projection
- The Windows installer offers an unchecked **Add FlashCMD to startup** option
- Required build, installer, and branding inputs are included under `code/`
- Optional compact cards show only each shortcut name and color accent
- Settings can download shortcut backups and validate uploaded replacements

## Color and execution behavior

Each action can store an optional `#RRGGBB` color. On Windows, a Command Line
action uses that color for its Windows Terminal tab when `wt.exe` is available.
Uncolored command actions omit the tab-color option. Program/Script actions may
store a color for card-accent selection, but launch directly and do not create
tabs.

The shortcut card scans actions in order and uses the first valid color it finds.
If no action is colored, the current theme's normal selected, hover, and default
card styling applies.

Native Windows console fallback windows and macOS Terminal launches do not have
FlashCMD-managed tab colors. Sequential and parallel execution semantics are
otherwise unchanged from 0.1.0.

## Compatibility

FlashCMD continues to read older single-action records and 0.1.0 records with a
top-level `color`. Loading a legacy record does not rewrite its file. In memory,
the legacy color is projected onto actions that do not already have a valid
color, preserving card and Windows Terminal appearance.

When that shortcut is intentionally edited and successfully saved through the
current editor, FlashCMD writes current fields: colors are stored on actions and
the top-level `color` is removed. Saving another shortcut does not canonicalize
unrelated legacy records.

## Installation

### Windows installer

Run the `.msi` and follow setup. **Add FlashCMD to startup** is unchecked on a
first install. If selected, setup creates a per-user startup entry and remembers
the choice across upgrades and repairs; uninstall removes the entry and installer
state. Startup remains installer-only and is not exposed in app Settings.

The final setup page still offers the independent option to open FlashCMD
immediately after installation.

### Windows portable

Run the versioned `.exe` directly. No installation or startup entry is required.

### macOS

Open the `.dmg`, then drag FlashCMD into Applications.

## User data

FlashCMD keeps personal shortcuts in the current user's application-data folder.
Installing a newer version or uninstalling the application does not remove that
personal shortcut file.

- Windows: `%LOCALAPPDATA%\FlashCMD\shortcuts.json`
- macOS: `~/Library/Application Support/FlashCMD/shortcuts.json`

## License

FlashCMD is distributed under the MIT License.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/davoodkazemi)
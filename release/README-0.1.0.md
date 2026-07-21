# FlashCMD 0.1.0

FlashCMD is a desktop shortcut manager for Windows and macOS. It lets you save,
organize, search, clone, and launch ordered collections of commands, programs,
and scripts.

## Release files

- `FlashCMD-0.1.0-windows-x64.msi` — recommended Windows installer
- `FlashCMD-0.1.0-windows-x64.exe` — portable Windows application
- `FlashCMD-0.1.0-macos-<architecture>.dmg` — macOS package when available

## Highlights

- Multiple named Command Line and Program/Script actions in each shortcut
- Ordered action editing, deletion, movement, and cloning
- **One by one** sequential execution and **All at once** parallel launching
- Complete shortcut cloning with a new user-provided name
- Collapsible shortcut folders and search
- Action-aware cards showing action count, order, and execution mode
- Per-action completion tracking with aggregated failure details
- Overlapping runs with independent execution state
- Windows system-tray support
- Configurable global restore hotkey
- Single-instance window restoration
- Light and dark themes with selectable accent colors
- Complete ordered Task Scheduler XML import and export

## Execution behavior

In **One by one** mode, FlashCMD waits for each immediate child process to finish
before starting the next action. A failed action is reported but does not prevent
later actions from running. In **All at once** mode, FlashCMD launches all actions
before monitoring their results.

When Windows Terminal is available, Command Line actions from one run open in a
new uniquely identified window with one named tab per action and the selected
shortcut color. Program/Script actions launch directly. If Windows Terminal is
unavailable, commands open in separate native console windows without grouped
tabs, tab titles, or tab colors.

## Task Scheduler XML

Import reads every ordered Task Scheduler `Exec` entry as a Program/Script
action. Export writes every shortcut action in order; Command Line actions are
represented as `cmd.exe /d /c` entries. Task Scheduler runs exported actions
sequentially even when the FlashCMD shortcut uses **All at once**.

## Compatibility

Existing single-action shortcut records remain readable without being rewritten
on load. Editing and successfully saving one of those shortcuts migrates only
that record to the current multi-action format.

## Installation

### Windows installer

Run the `.msi` file and follow the setup wizard. The final page can launch
FlashCMD immediately after installation.

### Windows portable

Run the versioned `.exe` directly. No installation is required.

### macOS

Open the `.dmg`, then drag FlashCMD into Applications.

## User data

FlashCMD keeps personal shortcuts in the current user's application-data folder.
Installing a newer version or uninstalling the application should not remove that
personal shortcut file.

- Windows: `%LOCALAPPDATA%\FlashCMD\shortcuts.json`
- macOS: `~/Library/Application Support/FlashCMD/shortcuts.json`

## License

FlashCMD is distributed under the MIT License.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/davoodkazemi)
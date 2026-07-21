![FlashCMD](https://storage.googleapis.com/general-geosynk/images/FlashCMD.png)

# FlashCMD

FlashCMD is a desktop shortcut manager for Windows and macOS. It helps you save,
organize, and launch commands or programs without retyping them every time.

## What FlashCMD does

- Save shortcuts for command-line actions or direct program/script launches
- Organize shortcuts into collapsible folders
- Search, edit, delete, and run saved shortcuts quickly
- Import and export Program/Script actions as Task Scheduler XML
- Restore the app from the tray or background using a configurable hotkey
- Keep a single running instance so repeated launches restore the same window

## Supported platforms

- Windows 10/11
- macOS

## How it works

Each shortcut can include:

- a name
- a command or program/script path
- optional arguments
- an optional working directory
- an optional folder for organization

On Windows, FlashCMD can minimize to the tray. In Settings, you can also choose
your terminal or shell, theme, accent color, and restore hotkey.

## Your data

FlashCMD stores your personal shortcut data per user:

- Windows: `%LOCALAPPDATA%\FlashCMD\shortcuts.json`
- macOS: `~/Library/Application Support/FlashCMD/shortcuts.json`

On Windows, FlashCMD can still read older data from legacy `FlashCmd` and
`QuickCMD` locations, but new saves go to the current `FlashCMD` path.

Your personal `shortcuts.json` and backup files are private local data. They are
ignored by Git and should never be uploaded or shared publicly.

## Notes

- There is no cloud sync
- There is no automatic updater
- Linux is not packaged at this time

If you are using the source repository, keep private shortcut files, generated
build output, and internal documentation out of public commits.

## Support

If FlashCMD is useful to you, you can support it here:

<a href="https://buymeacoffee.com/davoodkazemi" target="_blank" rel="noopener noreferrer">
  <img src="https://storage.googleapis.com/general-geosynk/images/bmc.png" alt="Buy Me a Coffee">
</a>
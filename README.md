
<h2 style="text-align: center">FlashCMD</h2>

<p style="text-align: center">
FlashCMD is a desktop shortcut manager for Windows and macOS. It helps you save,
organize, and launch ordered groups of commands or programs without retyping
them every time.
</p>




<p style="text-align: center"><img src="https://storage.googleapis.com/general-geosynk/flashcmd/main-logo-dark.png">
</p>


## What FlashCMD does
- Save each shortcut as one or more named Command Line or Program/Script actions
- Reorder actions and run them **One by one** or **All at once**
- Organize shortcuts into collapsible folders
- Search, edit, delete, and run saved shortcuts quickly
- Import and export Program/Script actions as Task Scheduler XML
- Restore the app from the tray or background using a configurable hotkey
- Keep a single running instance so repeated launches restore the same window
- Shortcuts can contain multiple named actions instead of only one command or
  program
- Actions can be added, edited, deleted, and reordered in the shortcut editor
- **One by one** execution waits for each action to finish and continues after
  failures; **All at once** launches every action before monitoring results
- Windows Terminal command actions open as individually named and colored tabs
  in one new window per shortcut run
- Program/Script actions continue to launch directly as external processes
- Completion tracking now reports individual exit codes, launch errors, missing
  working directories, start timeouts, and cancellation caused by app shutdown
- Multiple shortcut runs can overlap without sharing Terminal window identifiers
  or result files
- Existing single-action shortcuts remain readable and migrate only after they
  are edited and successfully saved
- Search and shortcut cards now include action names, action details, action
  count, order, and execution mode

![FlashCMD](https://storage.googleapis.com/general-geosynk/flashcmd/FlashCMD.png)

## Download

Download the latest FlashCMD release for Windows or macOS from
[GitHub Releases](https://github.com/davekazemi/flashcmd/releases).

## Creating and running a shortcut

1. Select **Add shortcut** and enter its name, folder, optional color, and
   execution mode.
2. Add one or more actions. Each action requires a name and can be either
   **Command Line** or **Program/Script**.
3. Use **Move up** and **Move down** to set the execution order.
4. Save the shortcut, select its card, and choose **Run**.

The status area shows launch and completion progress. When actions fail,
FlashCMD presents one summary containing every failed action and its available
exit or launch details; successful actions are not discarded.

## Supported platforms

- Windows 10/11
- macOS

## How it works

Each shortcut includes a name, folder, optional color, execution mode, and an
ordered list of actions. Every action has its own name and can be either:

- **Command Line** — a command and optional **Start in** working directory
- **Program/Script** — a program or script path, optional arguments, and optional
  **Start in** working directory

**One by one** waits for each action's real child process to finish before
starting the next action. A failed action is reported but does not prevent later
actions from running. **All at once** launches every action without waiting
between launches, then monitors all of them. Completion means the immediate
child finished; a command that deliberately starts or daemonizes another process
may therefore be considered complete while that detached process is still
running.

Task Scheduler XML import and export applies to the selected Program/Script
action only.

## Terminal behavior

On Windows, when Windows Terminal (`wt.exe`) is available, every Command Line
action in a run gets its own tab in one newly created, uniquely identified
window. Tabs use the action name, suppress application-title replacement, and
use the shortcut color when one is selected. Parallel command tabs are submitted
together so they join the same new window. Program/Script actions always launch
as direct external processes rather than Terminal tabs.

If Windows Terminal is unavailable or its initial launch fails, Command Line
actions remain usable in separate native console windows. One-window grouping,
tab titles, title suppression, and tab colors are unavailable in this fallback.
An accepted Windows Terminal launch that does not start in time is reported as a
timeout and is not retried, avoiding accidental duplicate commands.

On macOS, both execution modes and direct Program/Script actions are supported.
Command Line actions open through Terminal, but FlashCMD does not guarantee
Windows-style one-window grouping, per-tab colors, or title suppression there.
Closing FlashCMD stops result monitoring but does not terminate commands,
Terminal windows, or direct programs that were already launched.

On Windows, FlashCMD can minimize to the tray. In Settings, you can also choose
your terminal or shell, theme, accent color, and restore hotkey.

## Your data

FlashCMD stores your personal shortcut data per user:

- Windows: `%LOCALAPPDATA%\FlashCMD\shortcuts.json`
- macOS: `~/Library/Application Support/FlashCMD/shortcuts.json`

On Windows, FlashCMD can still read older data from legacy `FlashCmd` and
`QuickCMD` locations, but new saves go to the current `FlashCMD` path.

Existing single-action shortcut records are projected as one named action in
memory and are not rewritten merely because FlashCMD loaded them. Editing and
successfully saving that shortcut migrates only that record to the current
multi-action format; cancelling an edit or saving another shortcut leaves the
legacy record unchanged.

Your personal `shortcuts.json` and backup files are private local data. They are
ignored by Git and should never be uploaded or shared publicly.

## Notes

- There is no cloud sync
- There is no automatic updater
- Linux is not packaged at this time
- FlashCMD does not terminate external commands or programs when the app closes

If you are using the source repository, keep private shortcut files, generated
build output, and internal documentation out of public commits.

## Support

If FlashCMD is useful to you, you can support it here:
<p style="text-align: center">
<a href="https://buymeacoffee.com/davoodkazemi" target="_blank" rel="noopener noreferrer">
  <img src="https://storage.googleapis.com/general-geosynk/flashcmd/bmc.png" alt="Buy Me a Coffee">
</a>
</p>


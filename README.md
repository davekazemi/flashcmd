# FlashCmd

FlashCmd 0.1.0 is a small Tkinter shortcut manager for launching saved commands
without repeatedly opening a terminal and changing directories. It keeps the
existing JSON format and provides native packaging for Windows and macOS.

## Features and supported systems

- Save, search, edit, delete, and launch named multiline commands.
- Organize shortcuts into collapsible folders; unassigned shortcuts use General.
- Choose Command Line actions or separate Program/Script and argument fields.
- Import and export Program/Script actions as Windows Task Scheduler XML.
- Choose a theme, accent color, and terminal/shell executable.
- Windows 10/11: Command Line actions retain UTF-8 batch and `cmd.exe /k`
  behavior; Program/Script actions launch directly without an intermediate
  Command Prompt. The app retains its minimize/close-to-tray lifecycle.
- Currently maintained macOS versions: Command Line actions use Terminal.app,
  while Program/Script actions launch directly. The app follows normal Dock,
  close, and Command-Q behavior.
- Linux is not packaged; core path helpers use an XDG fallback for development.

There is no updater, cloud sync, command-format migration, or Linux release.

## Configuration and privacy

FlashCmd saves JSON per user:

- Windows: `%LOCALAPPDATA%\FlashCmd\shortcuts.json`
- macOS: `~/Library/Application Support/FlashCmd/shortcuts.json`

On Windows, reads fall back to `%LOCALAPPDATA%\QuickCMD\shortcuts.json` and
then an executable-adjacent `shortcuts.json`. Saves always go to the FlashCmd
path; legacy files are never changed or deleted. Uninstalling the MSI or
deleting `FlashCmd.app` leaves user configuration in place.

The root `shortcuts.json` and its backups are personal local data and are
ignored by Git. They must not be staged, packaged, or copied into releases.
Use the generic `examples/shortcuts.example.json` as format documentation.
Brand sources and historical files under `docs/` are documentation-only and
are excluded from application bundles.

## Source setup and tests

Prerequisites are Python 3.13 with Tkinter and a PyInstaller-compatible Python.
Inventory installed tools before changing the machine. Obtain explicit
permission before installing Python packages, WiX/.NET tools, Homebrew tools,
or other dependencies.

Runtime dependencies are declared in `requirements.txt`; build dependencies
are in `requirements-build.txt`. `pystray` is Windows-only. After dependencies
are already installed, run:

- Windows: `powershell -ExecutionPolicy Bypass -File scripts/test.ps1`
- macOS: `bash scripts/test.sh`
- Direct: `python -m unittest discover -s tests -v`
- Version smoke test: `python shortcut_manager.py --version`

## Local release builds

Windows packages must be built on Windows, and the DMG must be built on macOS.
PyInstaller does not cross-compile between these operating systems. Both build
scripts run the tests first and replace only generated `build/`, `dist/`, and
the matching files under `release/`.

### Windows

Use 64-bit Python 3.13 with Tkinter, the .NET 8 SDK, and WiX Toolset v4. A
first-time setup from PowerShell is:

```powershell
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
dotnet tool install --global wix --version "4.*"
$env:PATH += ";$env:USERPROFILE\.dotnet\tools"
wix --version
$env:PYTHON = "$PWD\.venv\Scripts\python.exe"
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

If WiX is already installed, use `dotnet tool update --global wix --version
"4.*"` when an update is intentionally required. The build command can be run
again without recreating the virtual environment.

The script tests, builds and smoke-tests a one-file windowed executable, builds
and validates a per-user x64 MSI, and emits:

- `release/FlashCmd-0.1.0-windows-x64.exe`
- `release/FlashCmd-0.1.0-windows-x64.msi`

The portable EXE can run from any user-writable directory. The MSI requires no
administrator access and installs under Local AppData Programs with a per-user
Start Menu shortcut. It owns only its executable and shortcut, not user JSON.
Optional signing uses a certificate already available in the Windows
certificate store via `FLASHCMD_WINDOWS_CERT_THUMBPRINT` and
`FLASHCMD_WINDOWS_TIMESTAMP_URL`; otherwise the output is explicitly unsigned.

### macOS

Use Python 3.13 with Tkinter and Xcode Command Line Tools for `sips`, `iconutil`,
`hdiutil`, `codesign`, and `xcrun notarytool`. A first-time setup in Terminal is:

```bash
xcode-select -p
python3.13 -m tkinter
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
PYTHON="$PWD/.venv/bin/python" bash scripts/build_macos.sh
```

If `xcode-select -p` fails, install Apple's Command Line Tools before building.
The `python3.13 -m tkinter` command should open a small Tk test window; close it
before continuing. Use the actual Python 3.13 command available on the Mac if
it has a different name.

The script regenerates the ICNS, tests, builds and smoke-tests `FlashCmd.app`,
then creates, verifies, mounts, checks, and detaches:

`release/FlashCmd-0.1.0-macos-<uname -m>.dmg`

Open the DMG and drag FlashCmd to its Applications link. The first command
launch may trigger macOS's Terminal automation permission prompt; grant access
only if you want FlashCmd to open Terminal windows.

For a preconfigured signing keychain, set `FLASHCMD_MACOS_SIGN_IDENTITY` plus
either `FLASHCMD_MACOS_NOTARY_PROFILE` or all three App Store Connect values:
`FLASHCMD_MACOS_NOTARY_KEY_PATH`, `FLASHCMD_MACOS_NOTARY_KEY_ID`, and
`FLASHCMD_MACOS_NOTARY_ISSUER`. Complete configuration enables hardened-runtime
signing, notarization, stapling, and verification. Partial/absent configuration
produces an unsigned DMG.

Unsigned builds may be blocked by Gatekeeper. Use Finder's **Open** command or
Privacy & Security's **Open Anyway** for a build you trust. Do not disable
Gatekeeper globally. For signed builds, verify with `codesign --verify --deep
--strict FlashCmd.app`; after notarization, use `spctl --assess --type execute
FlashCmd.app` and `xcrun stapler validate` on the DMG.

## Release process

1. Keep `flashcmd_version.py` as the single version source and run all tests.
2. Build on native Windows and macOS runners using the local scripts.
3. Audit EXE/MSI/DMG contents for personal JSON, backups, docs, examples,
   signing files, caches, and unexpected metadata.
4. Tag `v0.1.0` or manually dispatch the release workflow. It uploads Actions
   artifacts only; it does not create a GitHub Release or push tags.
5. Manually test portable/MSI install, tray and retained config on Windows, and
   DMG drag-install, Dock/quit, Terminal quoting, and permissions on macOS.

Generated contents of `build/`, `dist/`, and `release/` are disposable and
ignored; `release/.gitkeep` is the only source entry there. This repository is
not initialized or committed by the build scripts. Before a first `git init`,
verify the private JSON ignore rules with `git check-ignore`; initialize,
commit, push, tag, or publish only with separate authorization.

## Publishing the source repository on GitHub

### Include in the repository

- Application source: `shortcut_manager.py`, `quickcmd_core.py`,
  `flashcmd_launcher.py`, and `flashcmd_version.py`.
- Dependency declarations: `requirements.txt` and `requirements-build.txt`.
- Packaging and automation: `packaging/`, `installer/`, `scripts/`, and
  `.github/workflows/`.
- Runtime artwork under `icons/`, tests under `tests/`, `.gitignore`, and this
  README.
- The sanitized `examples/shortcuts.example.json` only—not a real user file.
- `release/.gitkeep`; generated packages belong in Actions or GitHub Releases.
- Public documentation/branding under `docs/` only after manually reviewing it
  for names, paths, screenshots, metadata, or other information not intended
  for publication.

Before making the repository public, choose and add an appropriate `LICENSE`.
GitHub source archives are generated automatically for every release, so source
ZIP files do not need to be uploaded manually.

### Never commit or upload

- `shortcuts.json`, `shortcuts.json.backup*`, or any real shortcut export.
- `build/`, `dist/`, generated `release/*`, `__pycache__/`, `*.pyc`, virtual
  environments, test caches, logs, or OS/editor temporary files.
- Certificates, private keys, provisioning profiles, `.env` files, passwords,
  tokens, notarization keys, certificate passwords, or GitHub credentials.
- A locally built `.app` directory; publish the DMG instead.
- Personal paths, commands, server names, usernames, or customer information in
  examples, screenshots, issue templates, logs, or release notes.

Keep signing values in the OS certificate store/keychain or GitHub Actions
Secrets. Secret values must never appear in workflow YAML, shell history,
commits, issue text, or release descriptions.

### Safe first-push checklist

Run these commands yourself after creating an empty GitHub repository. Review
the staged file list before committing or pushing:

```bash
git init
git check-ignore -v shortcuts.json shortcuts.json.backup-20260720
git add .
git status --short
git diff --cached --name-only
git commit -m "Initial FlashCmd 0.1.0 release"
git branch -M main
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

Do not continue if either private JSON file is staged. Replace `OWNER` and
`REPOSITORY` with the actual destination. Review `docs/` separately before
staging it if that directory is not intended to be public.

### Build with GitHub Actions

The release workflow installs Python dependencies and WiX on clean native
runners. It can be started from **Actions → Build release artifacts → Run
workflow**, or by pushing a version tag that exactly matches
`flashcmd_version.py`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

After both jobs succeed, download the `FlashCmd-windows-x64` and
`FlashCmd-macos` artifacts from the workflow run. The current workflow uploads
Actions artifacts but intentionally does not create a GitHub Release.

### What to attach to a GitHub Release

Create a release for the matching tag and attach only the end-user packages:

- `FlashCmd-0.1.0-windows-x64.exe`
- `FlashCmd-0.1.0-windows-x64.msi`
- `FlashCmd-0.1.0-macos-arm64.dmg` or the generated macOS architecture name
- Optional SHA-256 checksum text for those exact files

State clearly whether each artifact is signed/notarized or unsigned. Include
brief install instructions, supported operating systems, important changes,
known limitations, and the configuration-retention behavior. Do not attach
personal JSON, build directories, signing material, or intermediate `.app`
content.
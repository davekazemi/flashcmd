# Historical archive

These files are retained unchanged for project history and are excluded from
all application bundles and release artifacts.

Move map for rollback before a first commit:

- `QuickCMD_Logo_Presentation.html` moved from the repository root to this
  directory.
- `quickcmd.ico` moved from the repository root to this directory.
- `files.zip` moved from the repository root to this directory.

Before moving `files.zip`, its entry names were listed without extraction. It
contained only redundant branding files and no personal JSON or local data, so
it passed the archive safety gate. The move inventory was SHA-256 checked after
the move. Reverse the paths above to roll back; do not extract the ZIP into the
repository.
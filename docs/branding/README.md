# Branding sources

This directory contains documentation-only FlashCmd logo sources, rendered
variants, and mockups. They are never included in application bundles or
release artifacts.

Runtime derivatives live in `icons/`:

- `FlashCmd.ico` — Windows executable, Tk window, and tray icon.
- `icon-badge.png` — in-app header and macOS Tk window icon.
- `FlashCmd.icns` — Finder and Dock icon generated from `icon-badge.png` by
  `scripts/generate_macos_icon.sh`.

The editable badge source is `icon-badge.svg`. Regenerate and review PNG/ICO
derivatives deliberately; the macOS script only regenerates the ICNS file.

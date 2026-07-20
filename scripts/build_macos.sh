#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
PYTHON_BIN="${PYTHON:-python}"
VERSION="$("${PYTHON_BIN}" -c 'from flashcmd_version import __version__; print(__version__)')"
[[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid version" >&2; exit 1; }
ARCH="$(uname -m)"
DMG_PATH="${ROOT_DIR}/release/FlashCmd-${VERSION}-macos-${ARCH}.dmg"
APP_PATH="${ROOT_DIR}/dist/FlashCmd.app"
STAGING_DIR=""
MOUNT_POINT=""
ICON_BASELINE=""

cleanup() {
  if [[ -n "${MOUNT_POINT}" ]]; then
    hdiutil detach "${MOUNT_POINT}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${STAGING_DIR}" && "${STAGING_DIR}" == "${TMPDIR:-/tmp}"/flashcmd-dmg.* ]]; then
    rm -rf -- "${STAGING_DIR}"
  fi
  if [[ -n "${ICON_BASELINE}" && -f "${ICON_BASELINE}" ]]; then
    rm -f -- "${ICON_BASELINE}"
  fi
}
trap cleanup EXIT

safe_remove_generated() {
  local target="$1"
  case "${target}" in
    "${ROOT_DIR}/build"|"${ROOT_DIR}/dist"|"${DMG_PATH}")
      [[ ! -e "${target}" ]] || rm -rf -- "${target}" ;;
    *) echo "Refusing to remove unexpected path: ${target}" >&2; exit 1 ;;
  esac
}

bash scripts/test.sh
ICON_BASELINE="$(mktemp "${TMPDIR:-/tmp}/flashcmd-icon-baseline.XXXXXX")"
if [[ -f icons/FlashCmd.icns ]]; then cp icons/FlashCmd.icns "${ICON_BASELINE}"; fi
bash scripts/generate_macos_icon.sh
if [[ -s "${ICON_BASELINE}" ]] && cmp -s "${ICON_BASELINE}" icons/FlashCmd.icns; then
  echo "Generated ICNS matches the checked-in asset."
else
  echo "Generated ICNS refreshed from icons/icon-badge.png."
fi

safe_remove_generated "${ROOT_DIR}/build"
safe_remove_generated "${ROOT_DIR}/dist"
safe_remove_generated "${DMG_PATH}"
mkdir -p "${ROOT_DIR}/release"
"${PYTHON_BIN}" -m PyInstaller --clean --noconfirm packaging/flashcmd-macos.spec

REPORTED="$("${APP_PATH}/Contents/MacOS/FlashCmd" --version)"
[[ "${REPORTED}" == "FlashCmd ${VERSION}" ]] || { echo "Version smoke test failed: ${REPORTED}" >&2; exit 1; }

SIGN_IDENTITY="${FLASHCMD_MACOS_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${FLASHCMD_MACOS_NOTARY_PROFILE:-}"
NOTARY_KEY="${FLASHCMD_MACOS_NOTARY_KEY_PATH:-}"
NOTARY_KEY_ID="${FLASHCMD_MACOS_NOTARY_KEY_ID:-}"
NOTARY_ISSUER="${FLASHCMD_MACOS_NOTARY_ISSUER:-}"
if [[ -n "${SIGN_IDENTITY}" ]] && {
     [[ -n "${NOTARY_PROFILE}" ]] ||
     [[ -n "${NOTARY_KEY}" && -n "${NOTARY_KEY_ID}" && -n "${NOTARY_ISSUER}" ]];
   }; then
  codesign --force --deep --options runtime --timestamp --sign "${SIGN_IDENTITY}" "${APP_PATH}"
  codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
  SIGNED_BUILD=1
else
  echo "macOS signing/notary configuration is incomplete; building an unsigned DMG."
  SIGNED_BUILD=0
fi

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/flashcmd-dmg.XXXXXX")"
cp -R "${APP_PATH}" "${STAGING_DIR}/FlashCmd.app"
ln -s /Applications "${STAGING_DIR}/Applications"
hdiutil create -volname "FlashCmd" -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}"

if [[ "${SIGNED_BUILD}" -eq 1 ]]; then
  codesign --force --timestamp --sign "${SIGN_IDENTITY}" "${DMG_PATH}"
  if [[ -n "${NOTARY_PROFILE}" ]]; then
    xcrun notarytool submit "${DMG_PATH}" --keychain-profile "${NOTARY_PROFILE}" --wait
  else
    xcrun notarytool submit "${DMG_PATH}" --key "${NOTARY_KEY}" \
      --key-id "${NOTARY_KEY_ID}" --issuer "${NOTARY_ISSUER}" --wait
  fi
  xcrun stapler staple "${DMG_PATH}"
  xcrun stapler validate "${DMG_PATH}"
fi

hdiutil verify "${DMG_PATH}"
ATTACH_PLIST="$(hdiutil attach -nobrowse -readonly -plist "${DMG_PATH}")"
MOUNT_POINT="$(printf '%s' "${ATTACH_PLIST}" | "${PYTHON_BIN}" -c \
  'import plistlib,sys; p=plistlib.load(sys.stdin.buffer); print(next(e["mount-point"] for e in p["system-entities"] if "mount-point" in e))')"
[[ -d "${MOUNT_POINT}/FlashCmd.app" && -L "${MOUNT_POINT}/Applications" ]]
hdiutil detach "${MOUNT_POINT}"
MOUNT_POINT=""
echo "Built ${DMG_PATH}"
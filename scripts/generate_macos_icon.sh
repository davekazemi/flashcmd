#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_IMAGE="${ROOT_DIR}/docs/branding/icon-badge.png"
OUTPUT_IMAGE="${1:-${ROOT_DIR}/docs/branding/FlashCmd.icns}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/flashcmd-iconset.XXXXXX")"
ICONSET_DIR="${TEMP_DIR}/FlashCmd.iconset"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT
mkdir "${ICONSET_DIR}"

[[ -f "${SOURCE_IMAGE}" ]] || { echo "Missing ${SOURCE_IMAGE}" >&2; exit 1; }
command -v sips >/dev/null || { echo "sips is required" >&2; exit 1; }
command -v iconutil >/dev/null || { echo "iconutil is required" >&2; exit 1; }

for size in 16 32 128 256 512; do
  sips -z "${size}" "${size}" "${SOURCE_IMAGE}" \
    --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
  doubled=$((size * 2))
  sips -z "${doubled}" "${doubled}" "${SOURCE_IMAGE}" \
    --out "${ICONSET_DIR}/icon_${size}x${size}@2x.png" >/dev/null
done

mkdir -p "$(dirname "${OUTPUT_IMAGE}")"
iconutil -c icns "${ICONSET_DIR}" -o "${OUTPUT_IMAGE}"
echo "Generated ${OUTPUT_IMAGE}"

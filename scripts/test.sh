#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python}"
"${PYTHON_BIN}" -m unittest discover -s tests -v

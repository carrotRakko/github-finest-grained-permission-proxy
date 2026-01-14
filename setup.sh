#!/bin/bash
#
# fgp-proxy setup script
#
# devcontainer 内で fgh コマンドを使えるようにする
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FGH_PATH="${SCRIPT_DIR}/fgh"
FGH_SYMLINK="/usr/local/bin/fgh"

if [ -f "${FGH_PATH}" ]; then
  echo "[setup] Installing fgh as ${FGH_SYMLINK}"
  sudo ln -sf "${FGH_PATH}" "${FGH_SYMLINK}"
  echo "[setup] Done. You can now use 'fgh' from anywhere."
else
  echo "[setup] ERROR: ${FGH_PATH} not found" >&2
  exit 1
fi

#!/bin/bash
#
# fgh installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/install.sh | bash -s -- --replace
#

set -e

FGH_URL="https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/fgh"
INSTALL_DIR="/usr/local/bin"

REPLACE=false
for arg in "$@"; do
    case "$arg" in
        --replace) REPLACE=true ;;
        *) echo "[fgh] Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if $REPLACE; then
    TARGET_PATH="${INSTALL_DIR}/gh"

    EXISTING_GH=$(which gh 2>/dev/null || true)
    if [[ -n "$EXISTING_GH" && "$EXISTING_GH" != "$TARGET_PATH" ]]; then
        echo "[fgh] Removing existing gh at ${EXISTING_GH}..."
        sudo rm -f "${EXISTING_GH}"
    fi

    echo "[fgh] Installing as gh (replacing original)..."
    sudo curl -fsSL "${FGH_URL}" -o "${TARGET_PATH}"
    sudo chmod +x "${TARGET_PATH}"

    echo "[fgh] Installed to ${TARGET_PATH}"
    echo "[fgh] Done! 'gh' now routes through fgp proxy."
else
    TARGET_PATH="${INSTALL_DIR}/fgh"

    echo "[fgh] Downloading fgh..."
    sudo curl -fsSL "${FGH_URL}" -o "${TARGET_PATH}"
    sudo chmod +x "${TARGET_PATH}"

    echo "[fgh] Installed to ${TARGET_PATH}"
    echo "[fgh] Done! Run 'fgh --help' to get started."
fi

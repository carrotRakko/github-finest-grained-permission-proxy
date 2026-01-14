#!/bin/bash
#
# fgh installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/install.sh | bash
#

set -e

FGH_URL="https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/fgh"
INSTALL_DIR="/usr/local/bin"
FGH_PATH="${INSTALL_DIR}/fgh"

echo "[fgh] Downloading fgh..."
sudo curl -fsSL "${FGH_URL}" -o "${FGH_PATH}"
sudo chmod +x "${FGH_PATH}"

echo "[fgh] Installed to ${FGH_PATH}"
echo "[fgh] Done! Run 'fgh --help' to get started."

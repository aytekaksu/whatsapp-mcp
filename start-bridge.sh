#!/bin/sh
# Start the local Go bridge. Build once if no binary exists yet.
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BRIDGE_DIR="$REPO_DIR/whatsapp-bridge"
cd "$BRIDGE_DIR"

if [ ! -x ./whatsapp-bridge ]; then
  if ! command -v go >/dev/null 2>&1; then
    echo "Go is required to build the bridge" >&2
    exit 127
  fi
  go build -o whatsapp-bridge .
fi

export WHATSAPP_DEVICE_NAME="${WHATSAPP_DEVICE_NAME:-WhatsApp MCP}"
exec ./whatsapp-bridge "$@"

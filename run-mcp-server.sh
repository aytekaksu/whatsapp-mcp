#!/bin/sh
# Stdio launcher for OpenCode and Codex. Keep Python as the direct child of
# the MCP client so the server's parent watchdog can detect a dead client.
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SERVER_DIR="$REPO_DIR/whatsapp-mcp-server"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"

if [ -z "$UV_BIN" ]; then
  echo "uv is required; install it or set UV_BIN to its absolute path" >&2
  exit 127
fi

# Use a separate environment for each OS user. OpenCode and Codex can run as
# different users without either one changing the other's interpreter files.
REPO_KEY="$(printf '%s' "$REPO_DIR" | cksum | awk '{print $1}')"
VENV_DIR="${WHATSAPP_MCP_VENV:-${XDG_CACHE_HOME:-$HOME/.cache}/whatsapp-mcp/$REPO_KEY/.venv}"
PYTHON="$VENV_DIR/bin/python3"
SYNC_STAMP="$VENV_DIR/.whatsapp-mcp-sync"

if [ ! -x "$PYTHON" ] || [ ! -f "$SYNC_STAMP" ] ||
  [ "$SERVER_DIR/uv.lock" -nt "$SYNC_STAMP" ] ||
  [ "$SERVER_DIR/pyproject.toml" -nt "$SYNC_STAMP" ]; then
  UV_PROJECT_ENVIRONMENT="$VENV_DIR" "$UV_BIN" sync --locked --directory "$SERVER_DIR" >&2
  touch "$SYNC_STAMP"
fi

export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" "$SERVER_DIR/main.py"

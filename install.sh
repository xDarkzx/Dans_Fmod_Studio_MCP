#!/usr/bin/env bash
# FmodStudioMCP installer for macOS / Linux
set -euo pipefail

echo
echo "=== FmodStudioMCP installer ==="
echo

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.10+ not found. Install it first, then re-run."
  exit 1
fi

echo "[1/3] Installing package (editable)..."
"$PY" -m pip install -e .

echo "[2/3] Verifying the fmod-studio-mcp command..."
"$PY" -c "import fmod_mcp.main"

echo "[3/3] Next step: enable FMOD Studio's Script Server once."
echo '       Preferences > Interface > tick "Enable Script Server" > restart Studio.'
echo '       Then add to your MCP client:'
echo
echo '       "fmod-studio": { "command": "fmod-studio-mcp" }'
echo
echo "Done."
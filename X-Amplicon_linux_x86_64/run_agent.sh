#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_EXE="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
else
  printf 'ERROR Python was not found. Run ./setup_linux.sh first.\n' >&2
  exit 1
fi

export PATH="$ROOT_DIR/bin:$PATH"
exec "$PYTHON_EXE" agent_cli.py "$@"

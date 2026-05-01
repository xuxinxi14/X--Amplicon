#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BIND_HOST="127.0.0.1"
PORT="8765"
FRONTEND_PORT="5173"
DEV=0
BUILD_FRONTEND=0
NO_BUILD=0
NO_BROWSER=0
REPAIR_DEPS=0

usage() {
  cat <<'EOF'
Usage: ./start_webui.sh [options]

Start the local X-Amplicon Web UI on macOS.

Options:
  --host HOST           Bind host, default 127.0.0.1.
  --port PORT           Backend port, default 8765.
  --frontend-port PORT  Vite dev-server port, default 5173.
  --dev                 Start backend plus Vite dev server.
  --build-frontend      Build the frontend before starting.
  --no-build            Do not build frontend if dist is missing.
  --no-browser          Do not open a browser.
  --repair-deps         Run setup_macos.sh before starting.
  -h, --help            Show this help text.
EOF
}

fail() {
  printf 'ERROR %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || fail "--host requires a value."
      BIND_HOST="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || fail "--port requires a value."
      PORT="$2"
      shift 2
      ;;
    --frontend-port)
      [[ $# -ge 2 ]] || fail "--frontend-port requires a value."
      FRONTEND_PORT="$2"
      shift 2
      ;;
    --dev)
      DEV=1
      shift
      ;;
    --build-frontend)
      BUILD_FRONTEND=1
      shift
      ;;
    --no-build)
      NO_BUILD=1
      shift
      ;;
    --no-browser)
      NO_BROWSER=1
      shift
      ;;
    --repair-deps)
      REPAIR_DEPS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

if [[ "$REPAIR_DEPS" -eq 1 ]]; then
  ./setup_macos.sh
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_EXE="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
else
  fail "Python was not found. Run ./setup_macos.sh first."
fi

export PATH="$ROOT_DIR/bin:$PATH"
mkdir -p "$ROOT_DIR/.xamplicon_webui"

if ! "$PYTHON_EXE" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  printf 'Web UI backend dependencies are missing.\n' >&2
  printf 'Install them with: ./setup_macos.sh\n' >&2
  exit 1
fi

FRONTEND_DIR="$ROOT_DIR/webui/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist"

frontend_built() {
  [[ -f "$FRONTEND_DIST/index.html" ]]
}

build_frontend() {
  command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js 20+ or use a release with prebuilt webui/frontend/dist."
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    npm --prefix "$FRONTEND_DIR" install
  fi
  npm --prefix "$FRONTEND_DIR" run build
}

resolve_port() {
  "$PYTHON_EXE" - "$BIND_HOST" "$1" <<'PY'
import socket
import sys

host = sys.argv[1]
start = int(sys.argv[2])
for port in range(start, start + 20):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)
raise SystemExit(f"No available port found in range {start}-{start + 19}.")
PY
}

open_browser() {
  local url="$1"
  if [[ "$NO_BROWSER" -eq 1 ]]; then
    return
  fi
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

if [[ "$DEV" -eq 1 ]]; then
  command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js 20+ to use --dev."
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    npm --prefix "$FRONTEND_DIR" install
  fi

  BACKEND_PORT="$(resolve_port "$PORT")"
  RESOLVED_FRONTEND_PORT="$(resolve_port "$FRONTEND_PORT")"
  BACKEND_URL="http://$BIND_HOST:$BACKEND_PORT"
  FRONTEND_URL="http://$BIND_HOST:$RESOLVED_FRONTEND_PORT"

  printf 'Starting backend: %s\n' "$BACKEND_URL"
  "$PYTHON_EXE" -m uvicorn webui.backend.app:app --host "$BIND_HOST" --port "$BACKEND_PORT" \
    > "$ROOT_DIR/.xamplicon_webui/webui_backend.out.log" \
    2> "$ROOT_DIR/.xamplicon_webui/webui_backend.err.log" &
  BACKEND_PID="$!"

  cleanup() {
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT

  open_browser "$FRONTEND_URL"
  printf 'Starting frontend dev server: %s\n' "$FRONTEND_URL"
  npm --prefix "$FRONTEND_DIR" run dev -- --host "$BIND_HOST" --port "$RESOLVED_FRONTEND_PORT"
  exit $?
fi

if [[ "$BUILD_FRONTEND" -eq 1 || ( ! frontend_built && "$NO_BUILD" -eq 0 ) ]]; then
  build_frontend
fi

frontend_built || fail "Frontend build was not found: $FRONTEND_DIST. Run ./start_webui.sh --build-frontend or use --dev."

RESOLVED_PORT="$(resolve_port "$PORT")"
URL="http://$BIND_HOST:$RESOLVED_PORT"

printf '\nX-Amplicon Web UI\n'
printf 'Project root: %s\n' "$ROOT_DIR"
printf 'Python: %s\n' "$PYTHON_EXE"
printf 'URL: %s\n' "$URL"
printf 'Press Ctrl+C to stop the server.\n\n'

open_browser "$URL"
exec "$PYTHON_EXE" -m uvicorn webui.backend.app:app --host "$BIND_HOST" --port "$RESOLVED_PORT"

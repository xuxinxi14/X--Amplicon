#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

USE_CHINA_MIRROR=0
INSTALL_SKILLS=0
SKIP_PIP=0
DIAGNOSTICS_ONLY=0
RESET_SETTINGS=0
PYTHON_BIN="${PYTHON:-}"
PIP_INDEX_URL="${PIP_INDEX_URL:-}"

usage() {
  cat <<'EOF'
Usage: ./setup_macos.sh [options]

Prepare X-Amplicon for macOS.

Options:
  --python PATH          Use a specific Python 3.10+ executable.
  --china-mirror        Use the Tsinghua PyPI mirror.
  --pip-index-url URL   Use a custom PyPI index URL.
  --with-skills         Install optional agent skill dependencies.
  --skip-pip            Skip Python package installation.
  --diagnostics-only    Only check files and write diagnostics.
  --reset-settings      Rewrite .xamplicon_webui/settings.json.
  -h, --help            Show this help text.
EOF
}

log() {
  printf '\n==> %s\n' "$1"
}

ok() {
  printf 'OK  %s\n' "$1"
}

warn() {
  printf 'WARN %s\n' "$1"
}

fail() {
  printf 'ERROR %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || fail "--python requires a path."
      PYTHON_BIN="$2"
      shift 2
      ;;
    --china-mirror)
      USE_CHINA_MIRROR=1
      shift
      ;;
    --pip-index-url)
      [[ $# -ge 2 ]] || fail "--pip-index-url requires a URL."
      PIP_INDEX_URL="$2"
      shift 2
      ;;
    --with-skills)
      INSTALL_SKILLS=1
      shift
      ;;
    --skip-pip)
      SKIP_PIP=1
      shift
      ;;
    --diagnostics-only)
      DIAGNOSTICS_ONLY=1
      shift
      ;;
    --reset-settings)
      RESET_SETTINGS=1
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

check_python_version() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

find_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    [[ -x "$PYTHON_BIN" ]] || fail "Python executable is not executable: $PYTHON_BIN"
    check_python_version "$PYTHON_BIN" || fail "Python 3.10+ is required: $PYTHON_BIN"
    printf '%s\n' "$PYTHON_BIN"
    return
  fi

  local candidates=(python3.13 python3.12 python3.11 python3.10 python3)
  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && check_python_version "$candidate"; then
      command -v "$candidate"
      return
    fi
  done

  fail "Python 3.10+ was not found. Install Python 3 from python.org or Homebrew first."
}

write_diagnostics() {
  local python_exe="$1"
  mkdir -p run_logs
  "$python_exe" - "$ROOT_DIR" "$python_exe" "$INSTALL_SKILLS" "$SKIP_PIP" <<'PY'
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
python_exe = sys.argv[2]
install_skills = bool(int(sys.argv[3]))
skip_pip = bool(int(sys.argv[4]))

def probe(args, timeout=15):
    try:
        completed = subprocess.run(
            args,
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return completed.stdout.strip()
    except Exception as exc:
        return f"probe failed: {exc}"

def probe_version(path):
    for suffix in (["--version"], ["-version"], ["version"], []):
        try:
            completed = subprocess.run(
                [str(path), *suffix],
                cwd=str(root),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
                check=False,
            )
        except Exception as exc:
            last_error = f"probe failed: {exc}"
            continue
        text = completed.stdout.strip()
        if completed.returncode == 0 and text:
            return text
        if text:
            last_error = text
    return last_error if "last_error" in locals() else ""

def tool_status(path):
    if not path.is_file():
        return {"exists": False, "executable": False, "file": "", "version": ""}
    executable = os.access(path, os.X_OK)
    file_text = probe(["file", str(path)]) if shutil_which("file") else ""
    version = probe_version(path) if executable else ""
    return {
        "exists": True,
        "executable": executable,
        "file": file_text.splitlines()[0] if file_text else "",
        "version": version.splitlines()[0] if version else "",
    }

def shutil_which(name):
    from shutil import which
    return which(name)

report = {
    "schema_version": "1.0",
    "platform": platform.platform(),
    "machine": platform.machine(),
    "project_root": str(root),
    "python": {
        "requested": python_exe,
        "runtime": sys.executable,
        "version": platform.python_version(),
    },
    "options": {
        "install_skills": install_skills,
        "skip_pip": skip_pip,
    },
    "files": {
        "process_py": (root / "process.py").is_file(),
        "frontend_dist": (root / "webui" / "frontend" / "dist" / "index.html").is_file(),
        "rdp_database": (root / "database" / "rdp_16s_v18.fa").is_file(),
    },
    "tools": {
        "usearch": tool_status(root / "bin" / "usearch"),
        "usearch_arm64": tool_status(root / "bin" / "usearch_osx_m_12.0-beta"),
        "usearch_x86_64": tool_status(root / "bin" / "usearch_osx_x86_12.0-beta"),
        "vsearch": tool_status(root / "bin" / "vsearch"),
    },
}

out = root / "run_logs" / "macos_setup_diagnostics.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(out)
PY
}

log "Checking platform"
if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "This script is intended for macOS. Current system: $(uname -s)"
else
  ok "macOS detected: $(sw_vers -productVersion 2>/dev/null || uname -r)"
fi

ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  ok "Architecture: Apple Silicon arm64."
  warn "Bundled VSEARCH is x86_64; install Rosetta 2 if macOS cannot run it."
  warn "Rosetta command: softwareupdate --install-rosetta --agree-to-license"
else
  ok "Architecture: $ARCH"
fi

log "Checking release files"
[[ -f process.py ]] || fail "process.py is missing."
[[ -d src ]] || fail "src/ is missing."
[[ -d webui/backend ]] || fail "webui/backend/ is missing."
[[ -f requirements.txt ]] || fail "requirements.txt is missing."
[[ -f requirements-webui.txt ]] || fail "requirements-webui.txt is missing."
[[ -f database/rdp_16s_v18.fa ]] || fail "database/rdp_16s_v18.fa is missing."
[[ -f bin/usearch ]] || fail "bin/usearch is missing."
[[ -f bin/usearch_osx_m_12.0-beta ]] || fail "bin/usearch_osx_m_12.0-beta is missing."
[[ -f bin/usearch_osx_x86_12.0-beta ]] || fail "bin/usearch_osx_x86_12.0-beta is missing."
[[ -f bin/vsearch ]] || fail "bin/vsearch is missing."
ok "Required files are present."

log "Preparing executable permissions"
chmod +x bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine \
    bin/usearch \
    bin/usearch_osx_m_12.0-beta \
    bin/usearch_osx_x86_12.0-beta \
    bin/vsearch 2>/dev/null || true
fi
ok "USEARCH and VSEARCH are executable."

PYTHON_SOURCE="$(find_python)"
log "Using Python"
printf '%s\n' "$PYTHON_SOURCE"

if [[ ! -d .venv ]]; then
  log "Creating local virtual environment"
  "$PYTHON_SOURCE" -m venv .venv || fail "Failed to create .venv. Install Python with venv support."
fi

PYTHON_EXE="$ROOT_DIR/.venv/bin/python"
[[ -x "$PYTHON_EXE" ]] || fail "Virtual environment Python was not created: $PYTHON_EXE"

if [[ "$DIAGNOSTICS_ONLY" -eq 0 && "$SKIP_PIP" -eq 0 ]]; then
  log "Installing Python dependencies"
  pip_args=()
  if [[ -n "$PIP_INDEX_URL" ]]; then
    pip_args+=("-i" "$PIP_INDEX_URL")
  elif [[ "$USE_CHINA_MIRROR" -eq 1 ]]; then
    pip_args+=("-i" "https://pypi.tuna.tsinghua.edu.cn/simple")
  fi

  pip_install() {
    if [[ ${#pip_args[@]} -gt 0 ]]; then
      "$PYTHON_EXE" -m pip install "${pip_args[@]}" "$@"
    else
      "$PYTHON_EXE" -m pip install "$@"
    fi
  }

  pip_install --upgrade pip setuptools wheel
  pip_install -r requirements.txt -r requirements-webui.txt
  if [[ "$INSTALL_SKILLS" -eq 1 ]]; then
    pip_install -r requirements-skills.txt
  fi
  ok "Python dependencies are installed."
else
  warn "Skipped Python dependency installation."
fi

log "Preparing local configuration"
mkdir -p .xamplicon_webui run_logs
if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  ok "Created .env from .env.example."
fi

if [[ "$RESET_SETTINGS" -eq 1 || ! -f .xamplicon_webui/settings.json ]]; then
  "$PYTHON_EXE" - "$ROOT_DIR" "$PYTHON_EXE" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
python_exe = sys.argv[2]
settings = {
    "language": "Chinese",
    "python_executable": python_exe,
    "default_output_root": "work",
    "default_metadata_path": "metadata.txt",
    "default_seq_dir": "seq",
    "default_group_col": "Group",
    "default_sample_id_col": "SampleID",
    "usearch_path": "bin/usearch",
    "vsearch_path": "bin/vsearch",
    "default_plot_format": "html",
    "authorized_dirs": [str(root)],
}
path = root / ".xamplicon_webui" / "settings.json"
path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
PY
  ok "Prepared Web UI settings for macOS."
else
  ok "Existing Web UI settings kept."
fi

write_diagnostics "$PYTHON_EXE" >/dev/null
ok "Diagnostics written to run_logs/macos_setup_diagnostics.json."

log "Setup complete"
printf 'Start the Web UI with:\n'
printf '  ./start_webui.sh\n'
printf 'Run a pipeline check with:\n'
printf '  ./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml\n'

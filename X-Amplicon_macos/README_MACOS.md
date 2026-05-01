# X-Amplicon macOS Preview

This directory is the macOS release workspace for X-Amplicon. It contains the
X-Amplicon Python/Web UI code, the small RDP 16S reference database, and the
validated macOS USEARCH/VSEARCH binaries.

## Included Layout

```text
X-Amplicon_mac/
  bin/
    usearch
    vsearch
  database/
    rdp_16s_v18.fa
  src/
  webui/
  process.py
  agent_cli.py
  setup_macos.sh
  start_webui.sh
  run_process.sh
  run_agent.sh
  pipeline_params.macos.yaml
```

User FASTQ files, metadata, analysis outputs, API keys, and large SILVA
databases are not included by default.

## System Requirements

- macOS on Intel or Apple Silicon.
- Python 3.10 or newer.
- Optional: Node.js 20+ if you need to rebuild the Web UI frontend.

Recommended Python installation methods:

```bash
brew install python
```

or install Python from:

```text
https://www.python.org/downloads/macos/
```

On Apple Silicon, if the bundled binaries are Intel-only, install Rosetta 2:

```bash
softwareupdate --install-rosetta --agree-to-license
```

## Setup

From this directory:

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh bin/usearch bin/vsearch
./setup_macos.sh
```

If PyPI access is slow in China:

```bash
./setup_macos.sh --china-mirror
```

If you need optional RAG, tracing, and evaluation dependencies:

```bash
./setup_macos.sh --with-skills
```

The setup script creates `.venv/`, prepares `bin/usearch` and `bin/vsearch`,
removes macOS quarantine attributes when possible, writes macOS Web UI defaults
to `.xamplicon_webui/settings.json`, and writes diagnostics to:

```text
run_logs/macos_setup_diagnostics.json
```

## Web UI

Start the Web UI:

```bash
./start_webui.sh
```

Default URL:

```text
http://127.0.0.1:8765
```

If macOS blocks a binary because it came from the internet, run:

```bash
xattr -dr com.apple.quarantine bin/usearch bin/vsearch
chmod +x bin/usearch bin/vsearch
```

## CLI Pipeline Test

Place or upload test data as:

```text
X-Amplicon_mac/
  metadata.txt
  seq/
    KO1_1.fq.gz
    KO1_2.fq.gz
    ...
```

Check configuration:

```bash
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
```

Run the full workflow:

```bash
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
```

Expected final outputs:

```text
work/06_final/
  run_summary.json
  provenance.json
  report/
  plots/
```

## Agent CLI

Offline mode:

```bash
./run_agent.sh --offline
```

LLM-enabled mode requires `.env` configuration or Web UI settings for API key,
API base URL, and model.

## Notes

- `bin/usearch` and `bin/vsearch` are placed on `PATH` by the launcher scripts.
- `pipeline_params.macos.yaml` uses `bin/usearch` and `bin/vsearch`.
- The bundled Web UI frontend build is used when `webui/frontend/dist/index.html`
  exists. If it is missing, install Node.js 20+ and run:

```bash
./start_webui.sh --build-frontend
```

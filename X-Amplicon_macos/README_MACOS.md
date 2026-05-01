# X-Amplicon macOS Preview

This directory is the macOS release workspace for X-Amplicon. It contains the
X-Amplicon Python/Web UI code, the small RDP 16S reference database, validated
macOS USEARCH 12 binaries for Intel and Apple Silicon, and bundled VSEARCH.

## Included Layout

```text
X-Amplicon_macos/
  bin/
    usearch
    usearch_osx_m_12.0-beta
    usearch_osx_x86_12.0-beta
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
databases are not included by default and remain ignored by git.

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

On Apple Silicon, `bin/usearch` uses the bundled arm64 USEARCH binary. The
bundled VSEARCH binary is currently x86_64; install Rosetta 2 if macOS cannot
run it:

```bash
softwareupdate --install-rosetta --agree-to-license
```

## Setup

From this directory:

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh \
  bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
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

The setup script creates `.venv/`, prepares `bin/usearch`, both USEARCH 12
binaries, and `bin/vsearch`, removes macOS quarantine attributes when possible,
writes macOS Web UI defaults to `.xamplicon_webui/settings.json`, and writes
diagnostics to:

```text
run_logs/macos_setup_diagnostics.json
```

To verify the release files without installing Python packages:

```bash
./setup_macos.sh --diagnostics-only
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

Common startup options:

```bash
./start_webui.sh --no-browser
./start_webui.sh --port 8770
./start_webui.sh --repair-deps
./start_webui.sh --build-frontend
```

If macOS blocks a binary because it came from the internet, run:

```bash
xattr -dr com.apple.quarantine \
  bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
chmod +x bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
```

## CLI Pipeline Test

Place or upload test data as:

```text
X-Amplicon_macos/
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
- `bin/usearch` is a wrapper. On Apple Silicon it runs
  `bin/usearch_osx_m_12.0-beta`; on Intel macOS it runs
  `bin/usearch_osx_x86_12.0-beta`. Keep `pipeline_params.macos.yaml` pointed at
  `bin/usearch`.
- USEARCH 12 does not behave like older releases for every legacy command. The
  representative FASTA subset in `otutab-filter` and the OTU table statistics in
  `otutab-rare` are generated internally by Python for USEARCH 12 compatibility.
- USEARCH 12 may print its version only when run without `--version`; use
  `./setup_macos.sh --diagnostics-only` for a reliable tool check.
- `pipeline_params.macos.yaml` uses `bin/usearch` and `bin/vsearch`.
- The bundled Web UI frontend build is used when `webui/frontend/dist/index.html`
  exists. If it is missing, `start_webui.sh` builds it automatically unless
  `--no-build` is used. You can also install Node.js 20+ and run:

```bash
./start_webui.sh --build-frontend
```

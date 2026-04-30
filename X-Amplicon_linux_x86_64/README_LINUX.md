# X-Amplicon Linux x86_64 Preview

This directory is the Ubuntu 22.04 x86_64 release workspace for X-Amplicon.
It contains the X-Amplicon Python/Web UI code and the small RDP 16S reference
database. Place the redistributable Linux USEARCH and VSEARCH binaries at
`bin/usearch` and `bin/vsearch` before running setup.

The package has been tested on an x86_64 Linux server with Python 3.12,
USEARCH `v10.0.240_i86linux32`, and VSEARCH `v2.15.2_linux_x86_64`. The CLI
pipeline, visualization suite, report generation, and Web UI startup completed
successfully with the bundled small RDP 16S database and paired FASTQ test data.

## Included Layout

```text
X-Amplicon_linux_x86_64/
  bin/
    usearch
    vsearch
  database/
    rdp_16s_v18.fa
  src/
  webui/
  process.py
  agent_cli.py
  setup_linux.sh
  start_webui.sh
  run_process.sh
  run_agent.sh
  pipeline_params.linux.yaml
```

User FASTQ files, metadata, analysis outputs, API keys, and large SILVA
databases are not included by default.

## System Requirements

- Ubuntu 22.04 x86_64.
- Python 3.10 or newer.
- `python3-venv` and `python3-pip`.
- Optional: Node.js 20+ if you need to rebuild the Web UI frontend.

On a clean Ubuntu server:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## Setup

From this directory:

```bash
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
./setup_linux.sh
```

If PyPI access is slow in China:

```bash
./setup_linux.sh --china-mirror
```

If you need optional RAG, tracing, and evaluation dependencies:

```bash
./setup_linux.sh --with-skills
```

The setup script creates `.venv/`, prepares `bin/usearch` and `bin/vsearch`,
writes Linux Web UI defaults to `.xamplicon_webui/settings.json`, and writes
diagnostics to:

```text
run_logs/linux_setup_diagnostics.json
```

## Web UI

Start the Web UI:

```bash
./start_webui.sh --no-browser
```

Default URL:

```text
http://127.0.0.1:8765
```

On a remote server, SSH port forwarding is usually safer than binding to all
interfaces. Start the server side first:

```bash
./start_webui.sh --no-browser
```

Then run this on your local machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

Then open:

```text
http://127.0.0.1:8765
```

If your deployment requires direct access from another host, bind explicitly:

```bash
./start_webui.sh --host 0.0.0.0 --no-browser
```

In JupyterLab, do not click `start_webui.sh` in the file browser. That opens
the file editor. Open a Terminal and run the shell commands there. If you see
`Permission denied`, restore executable permissions:

```bash
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
bash start_webui.sh --no-browser
```

## Viewing HTML Results Remotely

`analysis_report.html` embeds plots by relative paths such as `../plots/...`.
When viewing results from your local browser, keep the whole `work/06_final`
directory structure together. The most reliable remote method is to serve the
workspace through a local-only HTTP server:

On the server:

```bash
.venv/bin/python -m http.server 8899 --bind 127.0.0.1
```

On your local machine:

```bash
ssh -N -L 8899:127.0.0.1:8899 user@server
```

Then open:

```text
http://127.0.0.1:8899/work/06_final/report/analysis_report.html
http://127.0.0.1:8899/work/06_final/plots/index.html
```

## CLI Pipeline Test

Place or upload test data as:

```text
X-Amplicon_linux_x86_64/
  metadata.txt
  seq/
    KO1_1.fq.gz
    KO1_2.fq.gz
    ...
```

Check configuration:

```bash
./run_process.sh check-pipeline-config --params pipeline_params.linux.yaml
```

Run the full workflow:

```bash
./run_process.sh run-pipeline-config --params pipeline_params.linux.yaml
```

The pipeline command writes the core final outputs:

```text
work/06_final/
  run_summary.json
  provenance.json
  provenance.md
  otutab.txt
  otutab_rare.txt
  otus.fa
  otus.sintax
  taxonomy.tsv
  alpha/
  beta/
  taxonomy_summary/
```

Generate plots and reports after the pipeline finishes:

```bash
./run_process.sh visualization-suite --final-dir work/06_final --format html
./run_process.sh generate-report --final-dir work/06_final
```

Expected additional outputs:

```text
work/06_final/
  report/
  plots/
```

Important output files:

```text
work/06_final/run_summary.json
work/06_final/provenance.json
work/06_final/report/analysis_report.html
work/06_final/plots/index.html
```

## Agent CLI

Offline mode:

```bash
./run_agent.sh --offline
```

LLM-enabled mode requires `.env` configuration or Web UI settings for API key,
API base URL, and model.

## Linux Packaging

Linux does not have a universal Windows-style `.exe` installer format. Choose
the packaging target based on how users will run X-Amplicon:

| Package style | Recommended use | Notes |
| --- | --- | --- |
| Portable `tar.gz` directory | Servers, SSH, clusters, JupyterHub | Most reliable for this project. Users unpack, run `setup_linux.sh`, then run shell launchers. |
| AppImage | Desktop-style double-click app | Closest to a single-file Linux app, but requires AppImage tooling and per-distribution testing. |
| PyInstaller/Nuitka ELF | CLI binary or Web UI launcher | Can package Python code into a Linux executable, but database files, frontend `dist/`, and external tools still need to be bundled or placed beside it. |
| `.deb` package | Managed Ubuntu deployment | Good for institutional IT installs; more packaging metadata to maintain. |

Recommended portable release command:

```bash
cd ..
tar --exclude='X-Amplicon_linux_x86_64/.venv' \
    --exclude='X-Amplicon_linux_x86_64/work' \
    --exclude='X-Amplicon_linux_x86_64/seq' \
    --exclude='X-Amplicon_linux_x86_64/.env' \
    --exclude='X-Amplicon_linux_x86_64/.xamplicon_webui' \
    -czf X-Amplicon_linux_x86_64.tar.gz X-Amplicon_linux_x86_64
```

For a more `.exe`-like artifact, create a small Python launcher that starts
`uvicorn webui.backend.app:app`, then build it with PyInstaller in `--onedir`
mode and include `webui/frontend/dist`, `database`, `bin`, `src`, `agent`, and
the launcher scripts as data. Build on the same Linux distribution family as
the target system, and confirm redistribution terms before bundling external
tools such as USEARCH.

## Notes

- `bin/usearch` and `bin/vsearch` are placed on `PATH` by the launcher scripts.
- `pipeline_params.linux.yaml` uses `bin/usearch` and `bin/vsearch`.
- `check-pipeline-config` validates paths and executable presence. For a real
  binary runtime check, run `./bin/usearch --version` and `./bin/vsearch --version`.
- A Linux package may contain a USEARCH binary that reports `i86linux32`; this
  can still run on compatible x86_64 Linux systems, but it should be tested on
  the target server.
- The bundled Web UI frontend build is used when `webui/frontend/dist/index.html`
  exists. If it is missing, install Node.js 20+ and run:

```bash
./start_webui.sh --build-frontend
```

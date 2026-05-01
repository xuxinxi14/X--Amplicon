# X-Amplicon Web UI User Guide

The Web UI is the recommended local interface for X-Amplicon on Windows. It runs on `127.0.0.1`, keeps FASTQ files and results on the local machine, and calls the same deterministic tools as the command-line workflow.

## Quick Start

Install Web UI dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

Start the Web UI:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Open the URL printed by the launcher, usually:

```text
http://127.0.0.1:8765
```

## Startup Modes

Production mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Development mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Dev
```

Useful options:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -BuildFrontend
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBuild
```

Production mode serves the built React frontend from `webui\frontend\dist`. If the build is missing and Node.js/npm are installed, the launcher can build it automatically.

## First Configuration

Open **Settings** and review:

- Python executable.
- Default output root, usually `work`.
- Metadata path, usually `metadata.txt`.
- FASTQ folder, usually `seq`.
- Sample ID column, usually `SampleID`.
- Group column, usually `Group`.
- USEARCH and VSEARCH executable paths.
- Default plot format.
- Authorized directories for file browsing.

The **Agent LLM access** panel is optional. It lets you set:

- Model name.
- OpenAI-compatible API base URL.
- API key.

The API key is saved in the local `.env` file and is not returned by browser reads. The Web UI remains usable without a key.

## Recommended Analysis Flow

1. Use **Agent** to follow the guided readiness checklist.
2. Use **New Analysis** to create a project and validate inputs.
3. Confirm sample groups and differential comparisons.
4. Write `pipeline_params.webui.yaml`.
5. Run preflight from **Run Monitor**.
6. Start the full pipeline after preflight passes.
7. Browse plots, tables, reports, provenance, and files in **Results**.
8. Check or register reference databases in **Databases**.

## Troubleshooting

Missing backend dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

Missing frontend build:

```powershell
cd webui\frontend
npm.cmd install
npm.cmd run build
cd ..\..
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Port already in use:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
```

No API key:

- Deterministic analysis still works.
- The Agent page falls back to local rule-based guidance.
- CLI Agent can be started with `python agent_cli.py --offline`.

## Files Not To Package

Do not include local runtime state or user data in source commits:

```text
.env
.xamplicon_webui/
work/
run_logs/
seq/
webui/frontend/node_modules/
webui/frontend/dist/
```

For a Windows release archive, a prebuilt `webui\frontend\dist` can be included so end users do not need Node.js.

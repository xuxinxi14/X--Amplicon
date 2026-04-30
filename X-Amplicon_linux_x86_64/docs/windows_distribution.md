# Windows Distribution Guide

This document describes the supported Windows distribution routes for
X-Amplicon. The repository is designed so the deterministic CLI works without
an LLM API key; Agent mode is an optional interaction layer over the same core
tools.

## Distribution Routes

| Route | Target user | What to provide | Typical command |
| --- | --- | --- | --- |
| Source install | Developers and users comfortable with Python | GitHub source tree plus `setup_windows.ps1` | `powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1` |
| Conda/mamba environment | Bioinformatics users who already use conda | GitHub source tree plus `environment.yml` | `mamba env create -f environment.yml` |
| Portable bundle | Users who should not install Python manually | Zip containing source tree, `.tools\python-*-amd64\`, launchers, and docs | `.\run_process.bat --help` |

Large FASTQ files, reference databases, USEARCH binaries, `.env`, `work\`, and
`run_logs\` should not be committed to GitHub or included in a public source
release. Users provide those files locally.

## Source Install

Use this route for GitHub users and development machines.

```powershell
git clone https://github.com/xuxinxi14/X--Amplicon.git
cd X--Amplicon
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

Useful options:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallStaticExport
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -CreateDesktopShortcuts
```

The script creates `run_agent.bat` and `run_process.bat` unless `-NoLauncher`
is supplied.

## Conda Or Mamba

Use this route when users prefer a normal bioinformatics package manager.

```powershell
mamba env create -f environment.yml
mamba activate seq-proc-env
python process.py --help
python process.py check-pipeline-config --params pipeline_params.yaml
```

If using `conda` instead of `mamba`, replace `mamba` with `conda`.

## Portable Bundle

Use this route for non-developer Windows users. A portable bundle should be
assembled on a clean machine or CI worker, then zipped.

Recommended bundle layout:

```text
X-Amplicon/
  .tools/
    python-3.13.13-amd64/
      python.exe
  agent/
  docs/
  src/
  tests/
  .env.example
  databases.example.yaml
  environment.yml
  pipeline_params.yaml
  process.py
  agent_cli.py
  requirements.txt
  requirements-skills.txt
  setup_windows.ps1
  run_agent.bat
  run_process.bat
```

Do not include these local or large paths in a public portable zip:

```text
.env
work/
run_logs/
seq/
databas/
bin/
```

If a private lab bundle is distributed internally, `databas\` and
`bin\windows\` may be pre-populated when licenses and local policy allow it.

## Diagnostics

Generate a setup diagnostics report without installing packages or modifying
`.env`/launchers:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly
```

The default report is:

```text
run_logs/windows_setup_diagnostics.json
```

Use a custom report path:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 `
  -DiagnosticsOnly `
  -DiagnosticReportPath run_logs\my_setup_report.json
```

The report records Python resolution, import smoke-test status, external
executable/database presence, launcher creation, and pipeline config check
status.

## Release Checklist

Before publishing a Windows source release:

- Run `python process.py --help`.
- Run `powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly`.
- Confirm `README.md`, `README_zh.md`, `.env.example`, `requirements.txt`,
  `requirements-skills.txt`, `environment.yml`, and `setup_windows.ps1` are
  included.
- Confirm `.env`, `work\`, `run_logs\`, `seq\`, `databas\`, `bin\`, `.venv\`,
  and `.tools\` are excluded from public GitHub releases unless intentionally
  creating a private portable bundle.
- Confirm the user-facing docs explain how to provide USEARCH, VSEARCH, and
  RDP/SILVA databases locally.

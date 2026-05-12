# X-Amplicon Windows Release Package

This folder is the minimal local package for running X-Amplicon Web UI on Windows.

## What Is Included

- Bundled Python runtime: `.tools\python-3.13.13-amd64\python.exe`
- X-Amplicon core programs: `process.py`, `agent_cli.py`, `src\`, `agent\`
- Local Web UI backend and launcher: `webui\backend\`, `webui\launcher\`
- Prebuilt React frontend: `webui\frontend\dist\`
- Small RDP 16S database: `database\rdp_16s_v18.fa`
- Windows USEARCH/VSEARCH executables: `bin\windows\`
- One-click startup scripts: `Start_X-Amplicon_WebUI.vbs`, `Start_X-Amplicon_WebUI.cmd`, and `Start_X-Amplicon_WebUI.ps1`

Large user data and generated outputs are not included:

- `seq\`
- `work\`
- `.xamplicon_webui\`
- `.env`
- `webui\frontend\node_modules\`
- large SILVA databases

## Start

Recommended for ordinary Windows users:

```text
Double-click Start_X-Amplicon_WebUI.vbs
```

This opens the Web UI without a terminal window. A small startup window shows progress until the backend is ready. Closing the Web UI app window also stops the local backend.

For troubleshooting, use the visible console launcher:

```text
Double-click Start_X-Amplicon_WebUI.cmd
```

PowerShell users can run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

The Web UI normally opens at:

```text
http://127.0.0.1:8765
```

If the port is occupied:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

## First Use

1. Open **Settings** in the Web UI.
2. Confirm Python, output root, metadata path, FASTQ directory, USEARCH path, VSEARCH path, and plot format.
3. Optional: configure Agent LLM access with model, API base URL, and API key.
4. Open **Agent** for step-by-step readiness guidance.
5. Use **New Analysis** to select metadata and paired FASTQ files.
6. Run preflight and the full pipeline from **Run Monitor**.
7. Browse figures, tables, reports, provenance, and output files in **Results**.

## Add Your Data

Place or select your own metadata and sequencing files. A typical layout is:

```text
X-Amplicon_main\
  metadata.txt
  seq\
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
```

The metadata table should include a sample ID column and a group column:

```text
SampleID	Group
S1	WT
S2	KO
```

## Optional Dependency Repair

The package is intended to include a working Python environment. If dependency checking fails and internet access is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

Use the China mirror when needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps -UseChinaMirror
```

[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon is a Windows-first local Agent and Web UI for 16S rRNA amplicon analysis. It turns paired-end FASTQ files and a metadata table into OTU/ASV tables, taxonomy annotation, alpha/beta diversity, publication-ready visualizations, differential abundance plots, reports, and reproducibility records.

The recommended way to use X-Amplicon is the local browser Web UI. It keeps sequencing files on your computer, guides users step by step, and calls the same deterministic Python workflow as the CLI. An LLM API key is optional.

## Highlights

- Local Windows Web UI for wet-lab users.
- One-click Windows installer with bundled Python, RDP 16S database, USEARCH/VSEARCH, and prebuilt Web UI.
- Guided Agent page for analysis readiness and step-by-step execution.
- Deterministic `process.py` workflow for reproducibility and automation.
- No-LLM mode for local checks, visualization, reports, and most guidance.
- Optional LLM configuration from the Web UI: API key, API base URL, and model selection.
- Outputs include Plotly charts, report HTML/Markdown, `run_summary.json`, and provenance files.

## Quick Start: Windows Installer

For most users, download the Windows installer from GitHub Releases:

```text
X-Amplicon-Setup-v0.1.0.exe
```

Then:

1. Double-click `X-Amplicon-Setup-v0.1.0.exe`.
2. Follow the installer wizard. The default per-user install path is:

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

3. Launch **X-Amplicon Web UI** from the Start Menu or desktop shortcut.

The installed launcher checks the bundled Python environment, verifies the small RDP database, and opens the local Web UI. The default address is:

```text
http://127.0.0.1:8765
```

If the browser does not open automatically, copy the printed address into your browser.

### What The Installer Includes

| Component | Installed path |
| --- | --- |
| Bundled Python runtime | `.tools\python-3.13.13-amd64\python.exe` |
| Small 16S database | `database\rdp_16s_v18.fa` |
| USEARCH/VSEARCH executables | `bin\windows\` |
| X-Amplicon core workflow | `process.py`, `src\`, `agent\` |
| Web UI backend | `webui\backend\` |
| Prebuilt Web UI frontend | `webui\frontend\dist\` |
| One-click launchers | `Start_X-Amplicon_WebUI.cmd`, `Start_X-Amplicon_WebUI.ps1` |

The installer does not include user FASTQ data, analysis outputs, API keys, runtime state, `node_modules`, or large SILVA databases.

## Quick Start: Source Checkout

If you use the GitHub source repository instead of the Windows installer, install dependencies first:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

For slower PyPI access:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

Start the Web UI:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Optional startup flags:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
```

## Web UI Workflow

Use the Web UI in this order:

1. **Settings**: confirm Python, output directory, metadata path, FASTQ directory, USEARCH/VSEARCH paths, plot format, and optional LLM settings.
2. **Agent**: follow the guided readiness checklist before starting analysis.
3. **New Analysis**: create a project, select metadata and paired FASTQ files, validate sample matching, choose groups, set comparisons, and write parameters.
4. **Run Monitor**: run preflight checks, start the full pipeline, inspect logs, and copy reproducible commands.
5. **Results**: browse plots, tables, differential abundance results, reports, provenance, and files.
6. **Databases**: check the bundled RDP database or register your own FASTA database.

The Web UI does not upload sequencing files. Data, logs, and results stay local.

## Input Files

Typical project layout:

```text
your_project\
  metadata.txt
  seq\
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
```

Minimal metadata:

```text
SampleID	Group
S1	WT
S2	KO
```

Requirements:

- Metadata must be tab-separated text.
- Sample IDs must match paired FASTQ names after removing the R1/R2 suffixes.
- A group column such as `Group` is needed for diversity plots and differential comparisons.

## Output Files

The default output root is:

```text
work\
```

Final results are written to:

```text
work\06_final
```

Main outputs:

| Output | Default location |
| --- | --- |
| OTU/ASV table | `work\06_final\otutab.txt` |
| Taxonomy annotation | `work\06_final\taxonomy.txt` |
| Alpha diversity | `work\06_final\alpha_diversity.txt` |
| Beta diversity | `work\06_final\beta_diversity\` |
| Visualization browser | `work\06_final\plots\index.html` |
| Differential abundance | `work\06_final\differential_abundance\` |
| Report | `work\06_final\report\analysis_report.html` |
| Reproducibility records | `work\06_final\run_summary.json`, `provenance.json`, `provenance.md` |

Plot outputs are organized in subfolders instead of being placed together in one directory.

## Optional LLM Agent

The full analysis workflow works without an API key. To enable LLM-assisted guidance:

1. Open **Settings** in the Web UI.
2. Select or enter a LiteLLM-compatible model.
3. Enter an OpenAI-compatible API base URL if needed.
4. Enter the API key.

The key is saved locally to `.env` and is not returned to the browser by the settings API.

Equivalent `.env` fields:

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

## CLI Usage

The Web UI is recommended for most users. The CLI remains available for reproducible scripts and automation.

Run the standard workflow:

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

Useful CLI tools:

| Task | Command |
| --- | --- |
| Validate configuration | `python process.py check-pipeline-config --params pipeline_params.yaml` |
| Run full pipeline | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| Generate visualizations | `python process.py visualization-suite --final-dir work\06_final --format html` |
| Run differential abundance | `python process.py differential-abundance --reference-group WT --format html` |
| Generate report | `python process.py generate-report --final-dir work\06_final` |
| Check database | `python process.py check-database rdp_16s_v18` |
| List all CLI commands | `python process.py --help` |

CLI Agent:

```powershell
python agent_cli.py
python agent_cli.py --offline
```

Useful slash commands include `/params`, `/status`, `/tools`, `/language`, `/report`, `/config`, and `/quit`.

## Dependencies

The Windows installer already includes the runtime needed for ordinary use. Source users need:

| Category | Packages or tools |
| --- | --- |
| Core Python | `numpy`, `pandas`, `scipy`, `scikit-bio`, `pyyaml`, `click`, `biopython`, `pydantic`, `plotly`, `rich`, `litellm` |
| Web UI backend | `fastapi`, `uvicorn[standard]`, `python-multipart`, `aiofiles` |
| Static plot export | `kaleido` |
| Optional Agent skills | `llama-index`, `deepeval`, `ragas`, `langchain-openai`, `opentelemetry-api`, `opentelemetry-sdk` |
| External tools | USEARCH and VSEARCH |

## Troubleshooting

If PowerShell blocks the launcher, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

If the default port is occupied:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

If an installed dependency check fails and internet access is available, open PowerShell in the installation directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

## License

See [LICENSE](LICENSE).

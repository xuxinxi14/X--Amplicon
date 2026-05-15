[English](README.md) | [中文](README_zh.md)

# 🧬 X-Amplicon
**Author:** XinXi Xu

X-Amplicon is a Windows-first local Agent and Web UI for 16S rRNA amplicon analysis, with a Linux x86_64 server package for command-line and browser-based deployment. It turns paired-end FASTQ files and a metadata table into OTU/ASV tables, taxonomy annotation, alpha/beta diversity, publication-ready visualizations, differential abundance plots, reports, and reproducibility records.

> 💡 **Recommended workflow:** Use the local browser Web UI. Your sequencing files never leave your computer, the wizard guides you step by step, and everything runs through the same deterministic Python workflow as the CLI. An LLM API key is entirely optional.

## ✨ Highlights

- Local Windows Web UI for wet-lab users.
- One-click Windows installer with bundled Python, RDP 16S database, USEARCH/VSEARCH, and prebuilt Web UI.
- Linux x86_64 package with setup, Web UI, CLI launchers, bundled small RDP database, and server test workflow.
- Guided Agent page for analysis readiness and step-by-step execution.
- Deterministic `process.py` workflow for reproducibility and automation.
- No-LLM mode for local checks, visualization, reports, and most guidance.
- Optional LLM configuration from the Web UI: API key, API base URL, and model selection.
- Outputs include Plotly charts, report HTML/Markdown, `run_summary.json`, and provenance files.

<img width="1014" height="671" alt="c1a4c08be4838b85f1ee997ea8b795b" src="https://github.com/user-attachments/assets/557330d5-e8ef-41a5-9ad1-2983c4d17f87" />


## 🚀 Quick Start: Windows Installer

The easiest way to get started is to download the Windows installer directly from GitHub Releases:

```text
X-Amplicon-Setup-v0.1.2.exe
```

Then:

1. Double-click `X-Amplicon-Setup-v0.1.2.exe` to launch the setup wizard.
2. Follow the prompts. The default per-user install path is:

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

3. Launch **X-Amplicon Web UI** from the Start Menu or desktop shortcut — and you're ready to analyze!

The normal shortcut starts X-Amplicon without showing a terminal window. A small startup window shows progress until the backend is ready, then the Web UI opens. Closing the Web UI app window also stops the local backend. The visible `Start_X-Amplicon_WebUI.cmd` launcher is still included for troubleshooting.

The launcher automatically verifies the bundled Python environment and RDP database, then opens the local Web UI. The default address is:

```text
http://127.0.0.1:8765
```

If the hidden launcher fails, run `Start_X-Amplicon_WebUI.cmd` from the installation folder to see startup messages.

### 📦 What the Installer Includes

| Component | Installed path |
| --- | --- |
| Bundled Python runtime | `.tools\python-3.13.13-amd64\python.exe` |
| Small 16S database | `database\rdp_16s_v18.fa` |
| USEARCH/VSEARCH executables | `bin\windows\` |
| X-Amplicon core workflow | `process.py`, `src\`, `agent\` |
| Web UI backend | `webui\backend\` |
| Prebuilt Web UI frontend | `webui\frontend\dist\` |
| One-click launchers | `Start_X-Amplicon_WebUI.vbs`, `Start_X-Amplicon_WebUI.cmd`, `Start_X-Amplicon_WebUI.ps1` |

The installer does not include user FASTQ data, analysis outputs, API keys, runtime state, `node_modules`, or large SILVA databases — all that stays yours.

## 🛠️ Quick Start: Source Checkout

Prefer working from source? Install the dependencies first:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

If PyPI is slow in your region, use the China mirror:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

Start the Web UI:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Handy startup flags (change port or suppress auto-open):

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
```

## Quick Start: Linux x86_64 Server

The Linux release workspace is intended for Ubuntu 22.04 x86_64 or compatible x86_64 Linux servers:

```bash
cd /path/to/X-Amplicon_linux_x86_64
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
./setup_linux.sh --china-mirror
```

Check external tools and pipeline configuration:

```bash
./bin/usearch --version
./bin/vsearch --version
./run_process.sh check-pipeline-config --params pipeline_params.linux.yaml
```

Run the full CLI workflow:

```bash
./run_process.sh run-pipeline-config --params pipeline_params.linux.yaml
./run_process.sh visualization-suite --final-dir work/06_final --format html
./run_process.sh generate-report --final-dir work/06_final
```

Start the Linux Web UI from a terminal, not by clicking the `.sh` file in Jupyter:

```bash
./start_webui.sh --no-browser
```

On an SSH server, forward the Web UI to your local browser:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

Then open `http://127.0.0.1:8765`.

For offline report browsing over SSH, serve the result directory through a local-only HTTP server:

```bash
.venv/bin/python -m http.server 8899 --bind 127.0.0.1
ssh -N -L 8899:127.0.0.1:8899 user@server
```

Then open `http://127.0.0.1:8899/work/06_final/report/analysis_report.html`.

## Web UI Workflow

Follow these steps in order for a smooth analysis experience:

1. **Settings**: confirm your Python path, output directory, metadata path, FASTQ directory, USEARCH/VSEARCH paths, plot format, and any optional LLM settings.
2. **Agent**: work through the guided readiness checklist to make sure everything is in order before kicking off the analysis.
3. **New Analysis**: create a project, select your metadata and paired FASTQ files, validate sample matching, choose groups, define comparisons, and set parameters.
4. **Run Monitor**: run preflight checks, launch the full pipeline, watch the live logs, and grab the reproducible commands for your records.
5. **Results**: explore plots, tables, differential abundance results, reports, provenance files, and all outputs at a glance.
6. **Databases**: inspect the bundled RDP database or register your own custom FASTA database.

The Web UI never uploads your sequencing files. All data, logs, and results stay on your machine.

## 📂 Input Files
<img width="1583" height="674" alt="image" src="https://github.com/user-attachments/assets/d2a3cbf2-8e9b-4090-8392-332cd9a11116" />

A typical project layout looks like this:

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

Format requirements:

- Metadata must be a tab-separated text file (TSV).
- Sample IDs must match paired FASTQ filenames after stripping the R1/R2 suffixes.
- A group column such as `Group` is required for diversity plots and differential comparisons.

## 📊 Output Files
<img width="1584" height="1179" alt="image" src="https://github.com/user-attachments/assets/a17feaf7-ac65-470c-bf5a-99824f5dd7d0" />

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
| Taxonomy annotation | `work\06_final\otus.sintax`, `work\06_final\taxonomy.tsv` |
| Alpha diversity | `work\06_final\alpha\alpha_diversity.tsv` |
| Beta diversity | `work\06_final\beta\` |
| Visualization browser | `work\06_final\plots\index.html` |
| Differential abundance | `work\06_final\differential_abundance\` |
| Report | `work\06_final\report\analysis_report.html` |
| Reproducibility records | `work\06_final\run_summary.json`, `provenance.json`, `provenance.md` |

The CLI `run-pipeline-config` command writes the core analysis outputs first.
Generate `plots/` and `report/` afterward with `visualization-suite` and
`generate-report`. Plot outputs are organized in subfolders instead of being
placed together in one directory.

## 🤖 Optional LLM Agent
<img width="1586" height="1137" alt="image" src="https://github.com/user-attachments/assets/1a27c243-d392-446b-a0f9-9f0490c43efd" />

The full analysis workflow runs perfectly without an API key. To unlock LLM-assisted guidance, follow these steps:

1. Open **Settings** in the Web UI.
2. Select or type a LiteLLM-compatible model name.
3. Enter an OpenAI-compatible API base URL if you're using a proxy or custom gateway.
4. Enter your API key and save.

Your key is saved locally to `.env` and is never sent back to the browser by the settings API — it stays safely on your machine.

Equivalent `.env` fields:

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

## ⌨️ CLI Usage

The Web UI is recommended for most users. The CLI is there when you need scripted, reproducible runs or automation.

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

Useful slash commands include `/params`, `/status`, `/tools`, `/language`, `/report`, `/config`, and `/quit`. Type `/help` at any time for the full list.

## Linux Packaging Options

Linux does not use Windows `.exe` installers in the same way. The closest options are:

| Option | When to use | Notes |
| --- | --- | --- |
| Portable `tar.gz` release | Recommended for servers and clusters | Ship the project directory, run `setup_linux.sh` on the target machine, and start with shell launchers. |
| AppImage | Closest double-click desktop experience | Produces one Linux application file, but needs extra packaging work and testing per distribution. |
| PyInstaller/Nuitka executable | CLI or launcher binary | Can produce an ELF executable, but Web UI assets, database files, and USEARCH/VSEARCH still need to be bundled or placed beside it. |
| `.deb` package | Managed Ubuntu deployment | Best for internal IT deployment, but requires Debian packaging metadata and install scripts. |

For this project, the most reliable Linux equivalent of the Windows installer is a portable directory archive:

```bash
cd ..
tar --exclude='X-Amplicon_linux_x86_64/.venv' \
    --exclude='X-Amplicon_linux_x86_64/work' \
    --exclude='X-Amplicon_linux_x86_64/seq' \
    --exclude='X-Amplicon_linux_x86_64/.env' \
    -czf X-Amplicon_linux_x86_64.tar.gz X-Amplicon_linux_x86_64
```

Users unpack it, run `./setup_linux.sh`, then launch `./start_webui.sh --no-browser` or `./run_process.sh ...`. Build PyInstaller/AppImage artifacts only on a Linux system compatible with the target servers, and check redistribution terms for external tools such as USEARCH before bundling them.

## Dependencies

The Windows installer already includes everything needed for ordinary use. If you're building from source, install the following:

| Category | Packages or tools |
| --- | --- |
| Core Python | `numpy`, `pandas`, `scipy`, `scikit-bio`, `pyyaml`, `click`, `biopython`, `pydantic`, `plotly`, `rich`, `litellm` |
| Web UI backend | `fastapi`, `uvicorn[standard]`, `python-multipart`, `aiofiles` |
| Static plot export | `kaleido` |
| Optional Agent skills | `llama-index`, `deepeval`, `ragas`, `langchain-openai`, `opentelemetry-api`, `opentelemetry-sdk` |
| External tools | USEARCH and VSEARCH |

## 🔧 Troubleshooting

**PowerShell blocking the launcher?** Run it with an explicit bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

**Default port already in use?** Pick a different one with `-Port`:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

**Dependency check failing after install (and you have internet access)?** Open PowerShell in the installation directory and run the repair command:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

## 📄 License

See [LICENSE](LICENSE).

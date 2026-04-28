[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon is a Windows-first, local 16S rRNA amplicon analysis agent with a reproducible Python workflow underneath. The recommended entry point is the browser-based Web UI: it guides users through project setup, metadata validation, FASTQ pairing checks, parameter configuration, pipeline execution, result browsing, database management, and optional LLM-assisted guidance.

The deterministic pipeline remains available through `process.py`. The Web UI and CLI call the same core tools, so analyses can be reproduced from command lines, parameter files, logs, `run_summary.json`, and provenance records. An LLM API key is optional: the pipeline, Web UI checks, visualizations, differential abundance analysis, report generation, and most help features work without one.

## Recommended Entry Point: Web UI

### 1. Install

Run all commands from the repository root:

```powershell
cd X-Amplicon
```

Install the core Python dependencies and Web UI backend dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

If PyPI access is slow, use the Tsinghua mirror:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

Common setup options:

| Option | Purpose |
| --- | --- |
| `-InstallWebUIDeps` | Install FastAPI, uvicorn, file upload support, and async file serving for the Web UI |
| `-InstallStaticExport` | Install `kaleido` for static `png`, `pdf`, and `svg` plot export |
| `-InstallSkillDeps` | Install optional local RAG, literature search, tracing, and evaluation dependencies |
| `-UseChinaMirror` | Use the Tsinghua PyPI mirror |
| `-SkipConfigCheck` | Skip the initial `pipeline_params.yaml` validation during setup |

For a full local setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps -InstallStaticExport -InstallSkillDeps
```

### 2. Start The Web UI

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

The launcher starts a local FastAPI service, opens the browser, and serves the React frontend from the same local address. The default URL is:

```text
http://127.0.0.1:8765
```

If the default port is occupied, the launcher automatically tries the next available local port.

Useful startup options:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -BuildFrontend
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBuild
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Dev
```

Production mode uses one FastAPI service. If `webui\frontend\dist` is missing and Node.js/npm are available, the launcher can build the frontend automatically. Development mode (`-Dev`) starts FastAPI plus the Vite development server.

### 3. Configure The Web UI

Open **Settings** first.

General settings:

| Setting | Typical value | Notes |
| --- | --- | --- |
| Python executable | auto-detected | Uses `.tools`, `.venv`, or system Python |
| Output root | `work` | Final results are written under `work\06_final` |
| Metadata path | `metadata.txt` | Tab-separated sample metadata |
| FASTQ directory | `seq` | Raw paired-end FASTQ files |
| Sample ID column | `SampleID` | Column used to match metadata and FASTQ files |
| Group column | `Group` | Column used for diversity plots and differential comparisons |
| USEARCH path | `bin\windows\usearch.exe` | Required for USEARCH-based feature and table steps |
| VSEARCH path | `bin\windows\vsearch.exe` | Required for VSEARCH clustering, chimera checking, and SINTAX annotation |
| Default plot format | `html` | Use `all` only when static export dependencies are installed |

Agent LLM access:

- Choose a model from the list or enter a LiteLLM-compatible model string.
- Set an OpenAI-compatible API base URL when using a proxy or custom gateway.
- Enter an API key only on your own machine.
- The key is saved locally to `.env` and is never returned to the browser by `GET /api/settings/llm`.
- Clear the stored key from the same Settings panel when needed.

Equivalent `.env` fields:

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

No API key is required for deterministic analysis. Without a key, the Agent page still provides rule-based guidance and the CLI Agent can run in no-LLM mode.

### 4. Run A Guided Analysis

Use the Web UI in this order:

1. **Agent**: follow the guided analysis checklist and confirm what is missing before starting.
2. **New Analysis**: create a project, select metadata and FASTQ files, validate sample matching, confirm groups, choose comparisons, and write `pipeline_params.webui.yaml`.
3. **Run Monitor**: run preflight checks, start the full pipeline, inspect logs, copy commands, and stop jobs when necessary.
4. **Results**: browse Plotly figures, tables, reports, provenance, `run_summary.json`, and output files.
5. **Databases**: check registered databases, compute hashes on demand, or register a local FASTA database.
6. **Settings**: adjust default paths, plotting format, authorized directories, and optional LLM configuration.

The Web UI does not upload sequencing files. FASTQ files, databases, configuration, logs, and results stay on the local machine.

### 5. Required Local Inputs

Minimal project layout:

```text
X-Amplicon/
  pipeline_params.yaml
  metadata.txt
  seq/
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
  database/
    rdp_16s_v18.fa
  bin/
    windows/
      usearch.exe
      vsearch.exe
```

Minimal metadata:

```text
SampleID	Group
S1	WT
S2	KO
```

The sample IDs in metadata must match FASTQ file names after removing `read1_suffix` and `read2_suffix`.

### 6. Outputs

The standard final directory is:

```text
work\06_final
```

Important outputs:

| Output | Location |
| --- | --- |
| Feature table | `work\06_final\otutab.txt` |
| Taxonomic annotation | `work\06_final\taxonomy.txt` and SINTAX-derived summaries |
| Alpha diversity | `work\06_final\alpha_diversity.txt` |
| Beta diversity | `work\06_final\beta_diversity\` |
| Visualization index | `work\06_final\plots\index.html` |
| Differential abundance | `work\06_final\differential_abundance\` |
| Report | `work\06_final\report\analysis_report.html` and `.md` |
| Reproducibility | `work\06_final\run_summary.json`, `provenance.json`, `provenance.md` |

Visualization subdirectories are kept separate, for example alpha diversity, beta diversity, taxonomy, and differential abundance charts.

## Deterministic CLI

The CLI is useful for automation, debugging, and exact reproducibility.

### Standard End-To-End Commands

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

Replace `WT` with the actual control group in your metadata. To write only a comparison plan first:

```powershell
python process.py differential-abundance --final-dir work\06_final
```

### CLI Tool Reference

Use `python process.py <command> --help` for all options.

| Tool | Typical command |
| --- | --- |
| Print no-LLM workflow | `python process.py cli-only-workflow` |
| Validate pipeline config | `python process.py check-pipeline-config --params pipeline_params.yaml` |
| Run full config workflow | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| Run full workflow with explicit flags | `python process.py run-pipeline --help` |
| USEARCH ASV denoising | `python process.py usearch-asv --help` |
| USEARCH OTU clustering | `python process.py usearch-otu --help` |
| VSEARCH OTU clustering | `python process.py vsearch-otu --help` |
| VSEARCH reference chimera check | `python process.py vsearch-uchime-ref --help` |
| VSEARCH SINTAX annotation | `python process.py vsearch-sintax --help` |
| Build feature table | `python process.py otutab --help` |
| Taxonomy-based table filtering | `python process.py otutab-filter --help` |
| Rarefy OTU table | `python process.py otutab-rare --help` |
| Alpha diversity | `python process.py alpha-diversity --help` |
| Beta diversity | `python process.py beta-diversity --help` |
| Phylogenetic tree | `python process.py phylogenetic-tree --help` |
| Taxonomy summary | `python process.py taxonomy-summary --help` |
| Visualization suite | `python process.py visualization-suite --final-dir work\06_final --format html` |
| Differential abundance | `python process.py differential-abundance --reference-group WT --format html` |
| Report generation | `python process.py generate-report --final-dir work\06_final` |
| Provenance refresh | `python process.py write-provenance --summary-path work\06_final\run_summary.json` |
| List databases | `python process.py list-databases` |
| Check database | `python process.py check-database rdp_16s_v18` |
| Register database | `python process.py register-database --help` |
| Agent evaluation log | `python process.py agent-evaluation-log` |

Some aliases are retained for compatibility, including `report`, `taxonomy-stats`, and `agent-eval-log`.

### CLI Agent

```powershell
python agent_cli.py
```

No-LLM mode:

```powershell
python agent_cli.py --offline
```

Useful startup options:

```powershell
python agent_cli.py --model gpt-4o-mini
python agent_cli.py --api-base https://proxy.example.com/v1
python agent_cli.py --resume
python agent_cli.py --reset
python agent_cli.py --params pipeline_params.yaml
python agent_cli.py --require-llm
```

Interactive slash commands:

| Command | Purpose |
| --- | --- |
| `/status` | Show session state, artifacts, and recent tool runs |
| `/params` | Review or update pipeline parameters |
| `/tools` | List available analysis tools |
| `/language` | Switch CLI language between `Chinese` and `English` |
| `/report` | Generate or preview the analysis report |
| `/config` | Show model and API configuration |
| `/history` | Show conversation history |
| `/quit` | Exit |

## Dependencies

Python core packages:

```text
numpy
pandas
scipy
scikit-bio
pyyaml
click
biopython
pydantic>=2.0
plotly>=5.15
rich
litellm
```

Optional static figure export:

```text
kaleido
```

Web UI backend packages:

```text
fastapi
uvicorn[standard]
python-multipart
aiofiles
```

Optional Agent skill packages:

```text
llama-index
deepeval
ragas
langchain-openai==1.1.0
opentelemetry-api
opentelemetry-sdk
```

Frontend development packages are managed by `webui\frontend\package.json` and `package-lock.json`. Node.js 20+ and npm are recommended when building from source.

External command-line tools:

- USEARCH: required for USEARCH ASV/OTU and USEARCH table generation routes.
- VSEARCH: required for VSEARCH OTU clustering, reference chimera checking, and SINTAX annotation.

## Development And Validation

Backend tests:

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_webui_backend tests.test_webui_api_smoke
```

Frontend tests and build:

```powershell
cd webui\frontend
npm.cmd run test
npm.cmd run build
cd ..\..
```

Python syntax check:

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m compileall webui\backend
```

Manual Web UI checks are listed in [docs/web_ui_manual_e2e_checklist.md](docs/web_ui_manual_e2e_checklist.md). The Web UI implementation plan is in [docs/web_ui_implementation_plan.md](docs/web_ui_implementation_plan.md), and a focused startup guide is in [docs/web_ui_user_guide.md](docs/web_ui_user_guide.md).

## Git And Distribution Notes

Do not commit local secrets, runtime state, large sequencing data, or generated output:

```text
.env
.xamplicon_webui/
work/
run_logs/
seq/
webui/frontend/node_modules/
webui/frontend/dist/
```

GitHub source users can build the frontend locally. A Windows release archive for non-developer users may include a prebuilt `webui\frontend\dist` directory so the Web UI can start without Node.js.

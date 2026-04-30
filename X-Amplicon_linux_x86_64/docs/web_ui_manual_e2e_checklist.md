# X-Amplicon Web UI Manual E2E Checklist

Use this checklist before publishing a Web UI build or release archive. The test can stop after preflight when USEARCH/VSEARCH or real sequencing data are unavailable.

## 1. Startup

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Expected:

- Launcher prints a local URL, usually `http://127.0.0.1:8765`.
- Browser opens or the printed URL can be opened manually.
- Dashboard shows backend connectivity.
- No local data are uploaded.

## 2. Settings

Open **Settings**.

Expected:

- General settings load and save.
- Python, output root, metadata, FASTQ, SampleID, Group, USEARCH, VSEARCH, and plot format fields are visible.
- Agent LLM access panel shows current model and whether an API key is configured.
- Saving a model/API base/API key updates local `.env`.
- Reloading `GET /api/settings/llm` never exposes the API key value.
- Clearing the API key removes stored key fields.

## 3. Agent Guided Start

Open **Agent**.

Expected:

- Page presents a step-by-step analysis guide, not only error troubleshooting.
- Readiness cards point users toward Settings, New Analysis, Run Monitor, Results, and Databases.
- Local rule-based help works without an API key.
- Optional LLM explanation works only when a key is configured and falls back cleanly when unavailable.

## 4. Create Project

Open **New Analysis** and create a project.

Suggested values:

```text
Project name: demo-16s
Output root: work
Metadata path: metadata.txt
FASTQ folder: seq
SampleID column: SampleID
Group column: Group
Read1 suffix: _1.fq.gz
Read2 suffix: _2.fq.gz
```

Expected:

- Project appears in Dashboard/New Analysis context.
- Metadata validation reports clear pass/fail details.
- FASTQ pairing preview lists matched and missing pairs.
- Group counts are visible when metadata is valid.
- Comparison setup can generate reference-group comparisons or explicit comparisons.
- `pipeline_params.webui.yaml` is written to the project directory.

## 5. Run Monitor

Run preflight first.

Expected:

- A job appears in Run Monitor.
- Status, command, log, and events are visible.
- Command can be copied for terminal reproduction.
- Missing database or executable errors are readable and actionable.
- Job cancellation endpoint is available for running jobs.

Run the full pipeline only when required input files and executables are available.

Expected after a successful full run:

- `work\06_final` exists.
- `run_summary.json` and provenance files are generated.
- Visualization and report commands can be run or are reflected in outputs.

## 6. Results

Open **Results**.

Expected:

- Empty state is clear before a run.
- Existing `work\06_final` can be indexed.
- Plotly HTML files render inline.
- Tables preview without loading very large files entirely into the browser.
- Report, provenance, differential abundance, and files tabs are accessible.
- File preview/download is restricted to project/output/authorized paths.

## 7. Databases

Open **Databases**.

Expected:

- Registered databases are listed.
- Missing files are reported clearly.
- On-demand SHA-256 check works for selected databases.
- Local FASTA registration writes a registry record.
- Large hash calculation is not triggered by ordinary list refreshes.

## 8. Regression Commands

Backend:

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_webui_backend tests.test_webui_api_smoke
```

Frontend:

```powershell
cd webui\frontend
npm.cmd run test
npm.cmd run build
cd ..\..
```

Backend syntax:

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m compileall webui\backend
```

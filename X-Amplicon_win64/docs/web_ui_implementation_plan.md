# X-Amplicon Web UI Implementation Plan

This document tracks the staged implementation of the X-Amplicon Web UI. The current Web UI is a local Windows-first interface built around an Agent-guided analysis workflow, while the deterministic `process.py` tools remain the execution backend.

## Current Status

| Phase | Status | Scope | Validation |
| --- | --- | --- | --- |
| `WEBUI-P0` | Completed | Project skeleton, Web UI dependency file, setup script option, minimal FastAPI app, launcher scaffold | Backend imports and script syntax checks |
| `WEBUI-P1` | Completed | Backend models, local JSON stores, project settings, metadata validation, FASTQ pairing, params writing, command building, job manager, result indexing, database services | Backend compile and API smoke checks |
| `WEBUI-P2` | Completed | React + Vite + TypeScript frontend skeleton, API client, layout, navigation, bilingual i18n framework, dashboard and settings shell | `npm.cmd run typecheck`, `npm.cmd run build` |
| `WEBUI-P3` | Completed | New Analysis wizard for project creation, metadata validation, FASTQ pairing, group checks, comparison setup, params writing, preflight and full-run entry points | Frontend build and backend API smoke checks |
| `WEBUI-P4` | Completed | Run Monitor page, job list/status APIs, log viewer, command copying, cancellation endpoint | Job API smoke checks |
| `WEBUI-P5` | Completed | Results page, Plotly HTML embedding, table previews, report/provenance/file browsing, current workspace result index | Result API smoke checks |
| `WEBUI-P6` | Completed | Databases page, registry listing, on-demand SHA-256 checks, local FASTA registration, registry path setting | Database API smoke checks |
| `WEBUI-P7` | Completed | Agent and Help page, no-LLM rule-based explanations, optional LLM explanation endpoint, command suggestions, common error cards | Agent API smoke checks |
| `WEBUI-P8` | Completed | Windows distribution path, root-level `start_webui.ps1`, production single-service mode, automatic frontend build, `-Dev`, `-NoBrowser`, port fallback, static React serving | Launcher smoke checks and frontend build |
| `WEBUI-P9` | Completed | Backend unit tests, API smoke tests, frontend i18n smoke test, TypeScript build validation, manual E2E checklist | `python -m unittest ...`, `npm.cmd run test`, `npm.cmd run build` |

## Post-P9 Refinements Already Implemented

- The Agent page is now organized around step-by-step analysis guidance instead of error-first troubleshooting.
- The Settings page includes Agent LLM access management: model selection, custom model string, API base URL, API key storage, and API key clearing.
- LLM secrets are saved only to the local `.env`; API key values are not returned to browser reads.
- Chinese and English i18n coverage has been expanded for the Web UI.
- The Web UI layout, spacing, panels, and guided states have been refined for wet-lab users who are starting an analysis.
- `job_manager` explicitly closes captured subprocess stdout to avoid test-time resource warnings.
- README files now place Web UI installation, startup, configuration, and guided analysis before CLI details.

## Recommended User Flow

1. Run `setup_windows.ps1 -InstallWebUIDeps`.
2. Start `start_webui.ps1`.
3. Open `http://127.0.0.1:8765` or the port reported by the launcher.
4. Configure paths and optional Agent LLM access in Settings.
5. Use Agent as the first screen for guided readiness checks.
6. Use New Analysis to create a project and write `pipeline_params.webui.yaml`.
7. Run preflight and the full pipeline from Run Monitor.
8. Review plots, tables, reports, provenance, and files in Results.
9. Manage or register local reference databases in Databases.

## Architecture

```text
webui/
  backend/
    app.py
    api/
    models/
    services/
  frontend/
    src/
      api/
      components/
      i18n/
      pages/
      styles/
  launcher/
    start_webui.ps1
```

Backend:

- FastAPI service bound to `127.0.0.1` by default.
- Local JSON state under `.xamplicon_webui`.
- Reuses deterministic `process.py` commands through a subprocess job manager.
- Serves built frontend files from `webui\frontend\dist` when available.
- Keeps `/api/*` routes separate from frontend routing.

Frontend:

- React + Vite + TypeScript.
- Bilingual i18n dictionaries in `webui\frontend\src\i18n`.
- Pages: Dashboard, Agent, New Analysis, Run Monitor, Results, Databases, Settings.
- Plotly HTML outputs are embedded from local result files rather than regenerated in the browser.

Runtime state:

```text
.xamplicon_webui/
  settings.json
  projects.json
  jobs/
    <job_id>.json
    <job_id>.log
    <job_id>.events.jsonl
```

## Implemented Backend API Surface

| Area | Endpoint examples |
| --- | --- |
| Health | `GET /api/health` |
| Settings | `GET /api/settings`, `PUT /api/settings` |
| LLM settings | `GET /api/settings/llm`, `PUT /api/settings/llm` |
| Projects | `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{id}` |
| Metadata and FASTQ checks | project validation and pairing endpoints under project APIs |
| Jobs | `GET /api/jobs`, `GET /api/jobs/{id}`, job log/event/cancel endpoints |
| Results | current result index, file previews, report data, Plotly HTML previews |
| Databases | `GET /api/databases`, `POST /api/databases`, `POST /api/databases/{name}/check` |
| Agent help | `GET /api/agent/status`, `POST /api/agent/explain` |

## Validation Commands

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

Manual E2E validation:

```text
docs/web_ui_manual_e2e_checklist.md
```

## Remaining Backlog

These items are intentionally left for later iterations:

- True browser file picker integration through a signed local bridge or explicit directory authorization flow.
- Multi-project comparison dashboard.
- SQLite migration for large job histories.
- Optional packaged Windows release with prebuilt `webui\frontend\dist`.
- Richer report editing and export templates in the Web UI.
- More granular job stage parsing from pipeline logs.
- Optional automated benchmark runner from curated public datasets.

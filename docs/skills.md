# X-Amplicon Agent Skills

X-Amplicon loads optional agent skills from:

```text
agent/skills/<skill_name>/tools.py
```

Each `tools.py` file should export a `TOOL_DEFINITIONS` list using the same
schema style as `agent/tools.py`. The agent discovers these definitions at
startup and exposes them through `/tools`.

## Installed Skills

| Skill | Purpose | Network |
| --- | --- | --- |
| `local_project_rag` | Read-only project search, file reading, run summary inspection, artifact listing, optional LlamaIndex document preview | No |
| `agent_tracing` | JSONL tool-call tracing summaries and exports | No |
| `agent_evaluation` | Static registry/prompt checks plus task/tool evaluation log summaries and exports | No |
| `literature_evidence` | PubMed search and abstract retrieval through Biopython Entrez | Yes |

## Optional Dependencies

Install optional dependencies with:

```powershell
python -m pip install -r requirements-skills.txt
```

The optional dependency set includes Biopython, LlamaIndex, DeepEval, Ragas,
and OpenTelemetry packages. Current core skill tools keep these imports lazy so
the base workflow still works when optional packages are absent.

## PubMed Configuration

Set these in `.env` or in the shell environment:

```env
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=optional-ncbi-api-key
```

Do not commit real API keys.

## Trace Files

Tool-call traces are written to:

```text
run_logs/agent_tool_trace.jsonl
```

Override this path with:

```env
X_AMPLICON_AGENT_TRACE_PATH=run_logs/custom_trace.jsonl
```

Trace files are runtime logs and should not be committed.

## Evaluation Logs

Agent task/tool evaluation events are written to:

```text
run_logs/agent_evaluation_log.jsonl
```

Override this path with:

```env
X_AMPLICON_AGENT_EVAL_LOG_PATH=run_logs/custom_agent_evaluation_log.jsonl
```

Summarize or export from the terminal:

```powershell
python process.py agent-evaluation-log
python process.py agent-evaluation-log --export-json run_logs\agent_evaluation_log_export.json
```

Evaluation logs record user-task status, tool-call counts, durations, error
labels, and recovery-path labels. They are runtime logs and should not be
committed.

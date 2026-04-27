# AGENT_QUICKSTART

给快速模式使用的最小上下文，只保留直接开跑需要的信息。

## 1. 完整流程入口

直接运行：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml
```

只做 CLI 原生预检查：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
```

或：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml --check-only
```

完整流程结束后生成标准可视化：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite --final-dir work\06_final --format html
```

## 2. 默认输入

- 参数文件：`pipeline_params.yaml`
- metadata 和测序目录以 `pipeline_params.yaml` 当前内容为准
- 快速模式不要主动扩展到 `process.py` 全文；需要更多事实时再回看 `README.md`

## 3. 关键输出

- 主要结果目录：`output_root/06_final`
- 机器可读摘要：`output_root/06_final/run_summary.json`
- 核心结果：`otutab.txt`、`otus.sintax`、`taxonomy.tsv`
- 可视化结果目录：`output_root/06_final/plots`
- 标准图表子目录：`alpha_boxplot_chart`、`alpha_barplot_chart`、`alpha_rare_chart`、`beta_pcoa_chart`、`beta_cpcoa_chart`、`beta_heatmap_chart`、`taxonomy_stacked_bar_chart`、`taxonomy_heatmap_chart`

## 4. 关键限制

- 完整流程会根据最终 `otus.fa` 自动构建 `otus.tree`
- 参数确认界面不再要求用户提供树文件路径
- `feature-filter` 是独立命令，不会在完整流程里自动执行
- beta 距离对外统一使用 `manhattan`；`cityblock` 只作为兼容别名接受
- 完整流程默认生成分析表格；可视化在流程完成后由 `process.py visualization-suite` 或 Agent 工具 `run_visualization_suite` 按需生成

## 5. 报错处理原则

- 快速模式不先做人手预检查，直接执行
- 如果失败，只定位当前阻塞错误，不顺手做无关改动
- 汇报时优先引用 `run_summary.json`
- 需要完整背景时，再切回 `README.md`

---

## 6. AI Agent 使用指南

### 6.1 安装依赖

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -m pip install litellm rich plotly
```

核心流程和可视化依赖包括 `pandas`、`numpy`、`scikit-bio`、`scipy`、`plotly` 等；Agent CLI 额外需要 `litellm` 和 `rich`。默认可视化输出为 Plotly HTML，不需要额外浏览器服务；如果要导出 `png`、`pdf` 或 `all` 静态图，再安装 `kaleido`。

### 6.2 配置 API Key 和模型

The recommended approach is a `.env` file in the project root. Copy the example and edit it:

```powershell
copy .env.example .env
# then open .env and fill in your key and model
```

The agent reads variables in this priority order:

1. CLI flags (`--api-key`, `--api-base`, `--model`)
2. Environment variables already set in the shell
3. `.env` file in the project root
4. Built-in defaults (`claude-sonnet-4-6`)

**Key variables:**

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | API key sent to the provider (generic, highest priority) |
| `LLM_API_BASE` | Custom base URL for any OpenAI-compatible proxy |
| `DEFAULT_MODEL` | Default model string (LiteLLM format) |
| `OPENAI_API_KEY` | Fallback if `LLM_API_KEY` is not set |
| `ANTHROPIC_API_KEY` | Fallback if neither of the above is set |

**Quick shell setup (no .env file):**

```powershell
# Windows PowerShell
$env:LLM_API_KEY = "sk-..."
$env:DEFAULT_MODEL = "claude-sonnet-4-6"
```

```bash
# Linux / macOS
export LLM_API_KEY="sk-..."
export DEFAULT_MODEL="claude-sonnet-4-6"
```

### 6.3 使用自定义代理 / 中转端点

Any OpenAI-compatible relay works. Set `LLM_API_BASE` to the proxy URL and
prefix the model name with `openai/` so LiteLLM routes through the OpenAI
adapter instead of a native provider SDK.

**Examples:**

```env
# Alibaba Qwen via DashScope
LLM_API_KEY=sk-your-dashscope-key
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DEFAULT_MODEL=openai/qwen-max
```

```env
# DeepSeek
LLM_API_KEY=sk-your-deepseek-key
LLM_API_BASE=https://api.deepseek.com/v1
DEFAULT_MODEL=openai/deepseek-chat
```

```env
# Any generic relay (e.g. one-api, new-api, litellm proxy)
LLM_API_KEY=sk-relay-key
LLM_API_BASE=https://your-relay.example.com/v1
DEFAULT_MODEL=openai/gpt-4o
```

Or pass everything on the command line without a `.env` file:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py `
    --model openai/qwen-max `
    --api-key sk-... `
    --api-base https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 6.4 启动 Agent CLI

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py
```

List all known model strings:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py --list-models
```

All flags:

| Flag | Description |
| --- | --- |
| `--model MODEL` | Override the LLM model string |
| `--api-key KEY` | Override the API key |
| `--api-base URL` | Override the base URL (proxy endpoint) |
| `--env-file PATH` | Use a custom .env file instead of the default |
| `--list-models` | Print common model strings and exit |
| `--state PATH` | Use a custom state JSON file |
| `--reset` | Clear saved conversation history before starting |
| `--quiet` | Suppress tool call details |

### 6.5 交互命令

Once the agent is running, type any natural-language request. Special commands:

| Command | Action |
| --- | --- |
| `/tools` | List all available analysis tools |
| `/params` | Review or update pipeline defaults |
| `/status` | Show session status and recent artifacts |
| `/history` | Show conversation history |
| `/config` | Show current model / API configuration |
| `/language` | Switch CLI language; enter `Chinese` or `English` |
| `/reset` | Clear history and start fresh |
| `/quit` | Exit |

### 6.6 示例对话

```text
You: Calculate alpha diversity for my OTU table at otutab.txt
You: Run beta diversity with Bray-Curtis on the rarefied table
You: Summarize taxonomy at the Phylum level
You: Run the full pipeline with metadata.txt and seq/ directory
You: Generate all standard visualization charts for the completed run
You: Plot alpha boxplots and beta PCoA from work/06_final
You: Search the project files for run_summary and summarize the latest output
You: Summarize recent agent tool traces
You: Run the built-in agent evaluation cases
You: Search PubMed for 16S microbiome benchmark papers
```

### 6.7 Optional Agent skills

Optional skills are loaded from `agent/skills/*/tools.py` and appear in `/tools`.
The current skills are:

| Skill | Purpose |
| --- | --- |
| `local_project_rag` | Search/read project files, inspect `run_summary.json`, list output artifacts, optionally preview LlamaIndex documents |
| `agent_tracing` | Summarize and export tool-call traces from `run_logs/agent_tool_trace.jsonl` |
| `agent_evaluation` | Run static registry/prompt checks and optional dependency checks |
| `literature_evidence` | Search PubMed and fetch abstracts through Biopython Entrez |

Install optional dependencies:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -m pip install -r requirements-skills.txt
```

For PubMed search, set `NCBI_EMAIL` in `.env`. `NCBI_API_KEY` is optional.

### 6.8 文件结构

```text
agent/
├── __init__.py   # package marker
├── config.py     # env / .env loader, AgentConfig, KNOWN_MODELS
├── tools.py      # tool registry + JSON schema + safe executor
├── skills/       # optional read-only RAG, tracing, evaluation, literature tools
├── state.py      # JSON-backed conversation + result persistence
└── agent.py      # Perception → Reasoning → Action → Observation loop
agent_cli.py      # interactive CLI entry point
.env.example      # template — copy to .env and fill in your key
```

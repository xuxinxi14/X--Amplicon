# X-Amplicon 已完成优化记录

记录日期：2026-04-27

本文档整理 X-Amplicon 当前已经完成的主要功能增强，供后续更新 GitHub、撰写 release notes 和补充论文方法/结果部分时参考。内容按功能模块组织，重点记录实际改了什么、如何使用、输出到哪里、涉及哪些文件以及当前验证状态。

## 总览

X-Amplicon 已从基础 16S 扩增子数据处理流程扩展为更完整的分析型 Agent。当前已完成的增强包括：

- 两组差异丰度分析，支持比较计划、火山图和热图。
- 运行 provenance 与 reproducibility 记录，覆盖参数、环境、软件、数据库和输出文件 hash。
- publication-ready 可视化输出，支持 HTML、PNG、PDF、SVG 和图表索引。
- 自动报告生成器，输出 Markdown、HTML 和机器可读 JSON。
- 数据库 registry 管理模块，统一记录数据库名称、版本、taxonomy format、路径和 SHA-256。
- 可选 Agent skills，包括本地项目 RAG、tool-call tracing、Agent evaluation 和 PubMed 文献检索。
- Agent CLI 语言切换功能，支持中英文界面切换。
- 无 LLM 模式强化，明确 CLI-only workflow，并在缺少 API key 时提供本地可用的 Agent shell。
- Agent 评估支持代码，记录 user-task、tool-call、错误类型和 recovery path。
- README、Windows 初始化脚本、依赖说明和 CLI 文档更新。

## 差异丰度分析

### 完成内容

新增 taxonomy/feature 层面的两组差异丰度分析能力。模块读取完整流程产生的 `work/06_final/otutab.txt`、`work/00_input/metadata.txt` 和可选 `work/06_final/taxonomy.tsv`，根据用户指定的比较组执行统计检验，输出差异结果表、火山图和热图。

已支持：

- Wilcoxon rank-sum / Mann-Whitney U 检验。
- Welch t-test 可选方法。
- Benjamini-Hochberg FDR correction。
- metadata 分组变量读取与校验。
- 显式比较组、reference group 自动比较和用户确认式 comparison plan。
- 差异结果表、显著结果表、相对丰度矩阵、火山图、热图。

当前 Python 分发版没有内置 edgeR。原因是 edgeR 依赖 R/Bioconductor 运行环境，不适合作为 Windows Python-only 分发的默认依赖。CLI 中已明确提示 edgeR 尚未打包，避免用户误认为已实现。

### 比较组设置

显式比较组模式：

```powershell
python process.py differential-abundance `
  --compare KO:WT `
  --compare OE:WT `
  --format html
```

`CASE:CONTROL` 表示 case versus control，`log2FC > 0` 表示 case 组平均相对丰度更高。

Reference group 模式：

```powershell
python process.py differential-abundance `
  --reference-group WT `
  --group-col Group `
  --format html
```

程序会自动生成所有非 reference 组与 reference 组的比较。

Plan-confirmation 模式：

```powershell
python process.py differential-abundance

python process.py differential-abundance `
  --comparison-plan work\06_final\statistics\differential\comparison_plan.tsv `
  --run-confirmed-plan
```

当没有提供 `--compare` 或 `--reference-group` 时，程序只生成 `comparison_plan.tsv`。用户确认后将需要执行的行设置为 `Include=yes`，再运行 `--run-confirmed-plan`。

### 统计输出字段

每个 feature 的主要输出字段包括：

- `ID`：OTU/ASV feature ID。
- `log2FC`：`log2(mean(case) / mean(control))`，加入 pseudo-count 避免除零。
- `log2CPM`：平均 count-per-million 的 log2 转换。
- `PValue`：原始统计检验 P 值。
- `FDR`：Benjamini-Hochberg 校正后的 FDR。
- `level`：`Enriched`、`Depleted` 或 `NotSignificant`。
- `MeanCase` / `MeanControl`：case/control 组平均相对丰度。
- `CaseGroup` / `ControlGroup`：比较方向。
- taxonomy columns：提供 `taxonomy.tsv` 时附加 `Kingdom` 到 `Species` 注释。
- sample columns：每个样本的相对丰度百分比，用于热图和结果追溯。

显著性判定同时考虑：

- `PValue <= pvalue`
- `FDR <= fdr`
- `abs(log2FC) >= log2fc_threshold`

### 输出结构

默认输出目录为 `work/06_final/statistics/differential`：

```text
work/
  06_final/
    statistics/
      differential/
        comparison_plan.tsv
        comparison_result/
          KO_vs_WT/
            differential_results.tsv
            differential_results_significant.tsv
            relative_abundance_percent.tsv
        volcano_chart/
          KO_vs_WT/
            volcano.html
        heatmap_chart/
          KO_vs_WT/
            heatmap.html
            heatmap_matrix_zscore.tsv
```

### CLI 与 Agent 接入

新增 CLI 命令：

```powershell
python process.py differential-abundance --help
python process.py taxonomy-stats --help
```

新增 Agent tools：

- `build_differential_comparison_plan`
- `run_taxonomy_differential_abundance`
- `plot_differential_volcano`
- `plot_differential_heatmap`

`agent/tools.py` 已支持自动发现 `src.core.stat_*` 模块中的 `TOOL_DEFINITIONS`。

### 涉及文件

新增：

- `src/core/stat_taxonomy.py`
- `tests/test_stat_taxonomy.py`

修改：

- `process.py`
- `agent/tools.py`
- `README.md`
- `README_zh.md`

## Provenance 与可重复性记录

### 完成内容

完整 pipeline 运行后会自动生成机器可读 provenance record，记录分析环境、参数、软件版本、数据库信息、步骤状态和关键输出文件 hash。

默认输出：

```text
work/06_final/run_summary.json
work/06_final/provenance.json
work/06_final/provenance.md
```

`provenance.json` 是机器可读记录，`provenance.md` 是简明可读摘要。

### 记录内容

Provenance 记录覆盖：

- 工作流状态、开始时间、结束时间、失败步骤和错误信息。
- Git commit、branch、dirty state 和项目路径。
- Python 版本、Python 可执行文件、操作系统和关键 Python package 版本。
- USEARCH/VSEARCH 路径和 best-effort version。
- reference database 与 annotation database 的路径、大小和 SHA-256。
- 有效参数快照，包括 `pipeline_params.yaml` 来源。
- 每个 pipeline step 的状态、耗时、输入/输出路径和错误信息。
- 关键最终输出文件的 SHA-256。

被记录的关键 Python packages 包括：

- `biopython`
- `click`
- `deepeval`
- `llama-index`
- `litellm`
- `numpy`
- `opentelemetry-api`
- `opentelemetry-sdk`
- `pandas`
- `plotly`
- `pydantic`
- `pyyaml`
- `ragas`
- `rich`
- `scikit-bio`
- `scipy`

### 成功与失败运行记录

成功运行会记录完整输出和 provenance。失败运行也会写入当前已知状态，包括：

- 已完成步骤。
- 失败步骤。
- 错误信息。
- 已生成文件。
- 有效参数。
- 运行环境。

这使得失败分析也可以被审计和复现。

### CLI 接口

从已有 `run_summary.json` 重新生成 provenance：

```powershell
python process.py write-provenance `
  --summary work\06_final\run_summary.json
```

自定义输出路径：

```powershell
python process.py write-provenance `
  --summary work\06_final\run_summary.json `
  --output-json work\06_final\provenance.json `
  --output-md work\06_final\provenance.md
```

### CLI 预检查增强

`check-pipeline-config` 和 `run-pipeline-config --check-only` 已增强，运行前会检查：

- 参数文件结构。
- metadata 是否存在并可读取。
- FASTQ 目录和样本配对。
- feature method、chimera mode、OTU table method、filter route。
- reference database 和 annotation database。
- USEARCH/VSEARCH 可执行文件。
- Python import 依赖。
- 计划输出路径，包括 `run_summary.json`、`provenance.json`、`provenance.md`。

### 涉及文件

新增：

- `src/utils/provenance.py`

修改：

- `src/core/raw_amplicon_pipeline.py`
- `process.py`
- `tests/test_process_cli.py`
- `tests/test_raw_amplicon_pipeline_analysis.py`
- `README.md`
- `README_zh.md`

## Publication-Ready 可视化

### 完成内容

可视化模块已统一为 publication-oriented 输出。所有主要图表共用 Plotly 主题、颜色处理、字体、坐标轴、legend、输出格式和 HTML index 生成逻辑。

已支持的图表类型：

- Alpha diversity boxplot。
- Alpha diversity grouped barplot。
- Alpha rarefaction curve。
- Beta diversity PCoA。
- Beta diversity constrained PCoA。
- Beta distance heatmap。
- Taxonomy stacked bar chart。
- Taxonomy heatmap。
- Differential abundance volcano plot。
- Differential abundance heatmap。

### 输出格式

支持：

- `html`
- `png`
- `pdf`
- `svg`
- `all`

`html` 不需要额外依赖。`png`、`pdf`、`svg` 和 `all` 需要安装 `kaleido`。

### 输出结构

默认输出到 `work/06_final/plots`，每类图单独存放：

```text
work/06_final/plots/
  index.html
  alpha_boxplot_chart/
    index.html
  alpha_barplot_chart/
    index.html
  alpha_rare_chart/
    index.html
  beta_pcoa_chart/
    index.html
  beta_cpcoa_chart/
    index.html
  beta_heatmap_chart/
    index.html
  taxonomy_stacked_bar_chart/
    index.html
  taxonomy_heatmap_chart/
    index.html
```

### CLI 与 Agent 接入

批量生成标准图表：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

自定义分组颜色：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format svg `
  --color-palette "WT:#4E79A7,KO:#E15759,OE:#59A14F"
```

可视化 Agent tools 已同步支持：

- `svg` 输出。
- `all` 输出。
- `color_palette` 参数。
- 批量 visualization suite。

### 涉及文件

修改：

- `src/core/viz_common.py`
- `src/core/viz_alpha_diversity.py`
- `src/core/viz_beta_diversity.py`
- `src/core/viz_taxonomy.py`
- `src/core/viz_pipeline.py`
- `process.py`
- `agent/tools.py`
- `tests/test_visualization_tools.py`
- `README.md`
- `README_zh.md`

## 自动报告生成器

### 完成内容

新增标准分析报告生成器。报告生成器以完成运行后的 `work/06_final` 为输入，自动读取 `run_summary.json`、`provenance.json`、alpha/beta/taxonomy 结果表、差异分析结果和可视化图表，输出 Markdown、HTML 和机器可读 JSON。

默认输出：

```text
work/06_final/report/
  analysis_report.md
  analysis_report.html
  analysis_report_data.json
```

### 报告内容

报告包括：

- Executive summary：运行状态、样本数、分组数、feature method、OTU table method、注释数据库、过滤路线、最终 feature 数、rarefaction depth 和运行时间。
- Workflow and inputs：pipeline step、状态、耗时、描述和关键输入/输出文件。
- Outputs and files：最终核心结果表、alpha/beta/taxonomy 输出、图表、统计结果和 report 文件。
- Diversity summary：alpha diversity 指标、beta distance matrix 和 UniFrac 输出状态。
- Taxonomy summary：各 taxonomy rank 的 top taxa。
- Differential abundance summary：比较组、显著 feature 数、结果表和图表链接。
- Visualization summary：已生成图表及其路径。
- Provenance and reproducibility：Git、Python、package、USEARCH/VSEARCH、database 和 output hash。
- Notes and limitations：自动分析结果与生物学解释的边界。

HTML 报告会在关键 Plotly HTML 图存在时自动用 iframe 嵌入交互式图表。Markdown 报告提供相对路径链接，便于 GitHub 或本地浏览。

### CLI 与 Agent 接入

CLI：

```powershell
python process.py generate-report --final-dir work\06_final
python process.py report --final-dir work\06_final
```

常用参数：

- `--summary`：指定 `run_summary.json`。
- `--provenance`：指定 `provenance.json`。
- `--output-dir`：指定报告输出目录。
- `--no-html`：只输出 Markdown 和 JSON。
- `--no-figures`：不链接或嵌入图表。
- `--top-taxa`：控制 taxonomy 报告中每个层级展示的 top taxa 数量。

Agent tool：

- `generate_analysis_report`

Agent CLI 的 `/report` 已升级，优先调用同一个核心报告生成器。如果找不到已完成运行结果，则回退到会话摘要式 Markdown。

### 涉及文件

新增：

- `src/core/report_generator.py`
- `tests/test_report_generator.py`

修改：

- `process.py`
- `agent/tools.py`
- `agent_cli.py`
- `src/core/__init__.py`
- `README.md`
- `README_zh.md`

## 数据库管理模块

### 完成内容

新增数据库 registry，用于统一管理 reference database 和 taxonomy annotation database。该模块记录数据库名称、版本、taxonomy format、FASTA 路径和 SHA-256，减少跨机器配置混乱，并使 `run_summary.json` 和 `provenance.json` 能记录实际使用的数据库。

已支持：

- 内置兼容记录：`rdp_16s_v18`、`silva_16s_v123`。
- 内置别名：`rdp`、`silva`、`rdp_16s_v18.fa`、`silva_16s_v123.fa`。
- 本地 `databases.yaml` registry。
- 可上传模板 `databases.example.yaml`。
- 直接 FASTA 路径兼容。
- 文件存在性、大小、修改时间和可选 SHA-256 检查。
- 注册时尽量保存相对路径，方便跨机器迁移。

真实 `databases.yaml` 已加入 `.gitignore`，避免本机路径和大数据库元信息误提交。

### CLI 接口

列出数据库：

```powershell
python process.py list-databases
```

检查数据库：

```powershell
python process.py check-database rdp_16s_v18
python process.py check-database databas\rdp_16s_v18.fa --no-hash
```

注册自定义数据库：

```powershell
python process.py register-database `
  --name custom_16s `
  --path databas\custom_16s.fa `
  --version 2026-04 `
  --taxonomy-format sintax `
  --alias custom16s
```

### Pipeline 与 provenance 接入

已接入：

- `vsearch-sintax --database` 支持已注册数据库名、内置别名或直接 FASTA 路径。
- `vsearch-uchime-ref --reference-db` 支持 registry 解析并兼容直接路径。
- `check-pipeline-config` 会显示 annotation database 的实际 FASTA 路径和 registry metadata。
- `run_summary.json` 的 `effective_params` 会记录实际解析后的 `reference_db` 和 `annotation_database_path`。
- `provenance.json` 的 `databases` 字段会记录数据库名称、版本、taxonomy format、路径、文件大小、SHA-256 和 hash match 状态。

### Agent tools

新增：

- `list_registered_databases`
- `check_registered_database`
- `register_database`

`agent/tools.py` 已支持自动发现 `src.core.database_*` 模块中的 `TOOL_DEFINITIONS`。

### 涉及文件

新增：

- `src/core/database_registry.py`
- `databases.example.yaml`
- `tests/test_database_registry.py`

修改：

- `.gitignore`
- `process.py`
- `agent/tools.py`
- `src/core/__init__.py`
- `src/core/raw_amplicon_pipeline.py`
- `src/core/vsearch_sintax.py`
- `src/core/vsearch_uchime_ref.py`
- `src/utils/provenance.py`
- `README.md`
- `README_zh.md`
- `tests/test_process_cli.py`

## Agent Skills 与联网文献检索

### 完成内容

Agent 已加入可选 skills 扩展机制。Agent 启动时会自动发现 `agent/skills/*/tools.py` 中定义的 `TOOL_DEFINITIONS`，将核心 16S 分析工具和可选科研辅助工具解耦。

该部分已经同步 README 并上传 GitHub。相关提交：

```text
c73d376 Update README files and agent skills
```

### 已加入 skills

`local_project_rag`：

- 检索 README、论文草稿、参数文件、roadmap 和输出摘要。
- 读取和总结 `run_summary.json`。
- 查找当前分析输出 artifacts。
- 可选使用 LlamaIndex 预览 documents。

`agent_tracing`：

- 记录 Agent tool-call trace。
- 汇总 tool 调用次数、状态、耗时和错误类型。
- 导出 trace JSONL。
- 可选接入 OpenTelemetry。

`agent_evaluation`：

- 检查关键 Agent tools 是否已注册。
- 检查可选依赖是否安装。
- 运行轻量级静态 evaluation cases。

`literature_evidence`：

- 支持在用户明确需要文献证据时进行联网 PubMed 检索。
- 通过 Biopython Entrez 获取 PMID、标题、期刊、年份和摘要 metadata。
- 将外部文献证据与本地 benchmark 结果区分开，避免混淆。

### 可选依赖

新增或更新：

- `requirements-skills.txt`
- `.env.example`
- `README.md`
- `README_zh.md`

可选包包括：

- `biopython`
- `llama-index`
- `deepeval`
- `ragas`
- `opentelemetry-api`
- `opentelemetry-sdk`

安装示例：

```powershell
python -m pip install -r requirements-skills.txt
```

## Agent CLI 语言切换

### 完成内容

Agent CLI 已加入 `/language` 命令，支持在交互式 CLI 中切换中文和英文。用户输入 `/language` 后，再输入 `Chinese` 或 `English` 即可切换当前会话语言。

切换后，CLI 中不影响专业理解的界面文本会根据当前语言设置显示。一些翻译后可能出现歧义或不够专业的术语仍保留英文，例如 command、tool、pipeline、metadata、provenance、taxonomy 等。

### 用户入口

```text
/language
Chinese
```

或：

```text
/language
English
```

### 涉及文件

修改：

- `agent_cli.py`
- `README.md`
- `README_zh.md`

## 无 LLM 模式强化

### 完成内容

X-Amplicon 已明确将 LLM 定位为可选交互层，而不是分析流程的必需依赖。完整分析、统计、可视化、数据库检查、provenance 和报告生成都可以通过 `process.py` 完成，不需要 LLM API key。

新增 CLI-only 工作流入口：

```powershell
python process.py cli-only-workflow
```

该命令会打印推荐的确定性命令序列，包括：

- `list-databases`
- `check-database`
- `check-pipeline-config`
- `run-pipeline-config`
- `write-provenance`
- `visualization-suite`
- `differential-abundance`
- `generate-report`

### Agent 无 LLM 行为

`agent_cli.py` 在没有 LLM API key 时不再直接退出。默认行为改为进入 no-LLM / CLI-only shell：

- `/params`、`/status`、`/tools`、`/report`、`/config`、`/language`、`/quit` 等本地 slash commands 仍可用。
- 自然语言 tool orchestration 会被禁用，并提示用户使用 `process.py cli-only-workflow` 或配置 API key。
- 用户可通过 `python agent_cli.py --offline` 显式启动无 LLM shell。
- 用户可通过 `python agent_cli.py --require-llm` 保持严格行为：缺少 API key 时直接失败。

### 文档更新

已在 README 中强调：

- `process.py run-pipeline-config` 是推荐的确定性入口。
- Agent 模式是可选交互层。
- 没有 API key 时仍可完成完整分析。
- `cli-only-workflow` 是无 LLM 用户的推荐入口。
- `.env.example` 已说明 LLM key 只对自然语言 Agent 编排必需。

### 涉及文件

新增：

- `src/core/cli_only_workflow.py`

修改：

- `process.py`
- `agent_cli.py`
- `.env.example`
- `README.md`
- `README_zh.md`
- `tests/test_process_cli.py`
- `tests/test_agent_cli_params.py`
- `X-Amplicon_improvement_roadmap.md`

## Agent 评估支持代码

### 完成内容

新增 Agent evaluation logging 层，用于为后续 Agent 能力评估、错误恢复任务和 usability comparison 提供可统计的运行记录。该功能与现有 `agent_tracing` 不冲突：tracing 偏向底层 tool-call 调试，evaluation log 同时记录 tool-call event 和 user-task event。

默认输出：

```text
run_logs/
  agent_tool_trace.jsonl
  agent_evaluation_log.jsonl
```

### 记录内容

`agent_evaluation_log.jsonl` 记录：

- 每次 tool call 的 tool 名称、参数摘要、解析后的参数、结果摘要、状态和耗时。
- 每个用户任务的 task id、用户输入摘要、模型、轮数、tool-call 数量、tool error 数量、最终状态和耗时。
- 失败原因、错误类型和 recovery path。
- 无 LLM 模式下的自然语言输入，记录为 `no_llm` 状态，便于统计 CLI-only fallback 使用情况。

已支持的错误类型包括：

- `missing_metadata`
- `missing_seq_dir`
- `missing_executable`
- `missing_reference_database`
- `bad_tree_path`
- `missing_fastq_pairs`
- `database_config_error`
- `llm_unavailable`
- `max_tool_rounds`
- `tool_error`

对应 recovery path 包括 `confirm_metadata_path`、`configure_external_executable`、`remove_or_fix_beta_tree_path`、`fix_database_registry`、`configure_llm_or_use_cli` 等。

### CLI 与 Agent 接入

终端汇总：

```powershell
python process.py agent-evaluation-log
```

导出 JSON：

```powershell
python process.py agent-evaluation-log `
  --export-json run_logs\agent_evaluation_log_export.json
```

Agent tools：

- `summarize_agent_evaluation_log`
- `export_agent_evaluation_log`
- `list_agent_eval_cases`
- `run_agent_eval_cases`
- `inspect_optional_skill_dependencies`

环境变量：

```env
X_AMPLICON_AGENT_EVAL_LOG_PATH=run_logs/agent_evaluation_log.jsonl
```

### 涉及文件

新增：

- `agent/evaluation_logger.py`
- `tests/test_agent_evaluation_logging.py`

修改：

- `agent/agent.py`
- `agent/tools.py`
- `agent/state.py`
- `agent_cli.py`
- `agent/skills/agent_evaluation/tools.py`
- `agent/skills/agent_evaluation/test_cases.yaml`
- `process.py`
- `.env.example`
- `README.md`
- `README_zh.md`
- `X-Amplicon_improvement_roadmap.md`

## README、分发与项目文档

### 完成内容

项目文档已围绕 GitHub 发布和 Windows 用户分发重新整理。README 的模块叙述风格已统一，并补充每个 tool 的终端使用方式、依赖列表、CLI workflow、Agent workflow 和常见问题。

主要更新：

- `README.md` 作为英文 GitHub README。
- `README_zh.md` 作为中文 README。
- README 中删除或替换本机绝对路径，改为通用目录示例。
- 增加 Windows 初始化说明。
- 增加 `setup_windows.ps1` 分发脚本说明。
- 增加 CLI-only workflow，明确不依赖 LLM 也能运行完整分析。
- 增加 Agent 配置、可选 skills、依赖包和外部工具说明。
- 增加 visualization、differential abundance、provenance、report 和 database registry 的 CLI 文档。
- 增加 README 功能速览和 workflow 选择表，帮助新用户判断应该使用 `process.py`、`agent_cli.py`、`--offline` 还是完整报告输出流程。
- 增加运行真实数据前的本地资源准备清单，明确 metadata、FASTQ、USEARCH、VSEARCH、RDP/SILVA 数据库各自用途。
- 增加最小端到端命令序列，从配置检查到完整流程、可视化、差异丰度和报告生成。
- 增加最小输入目录结构和 metadata 示例，说明 `SampleID`、R1/R2 后缀和 `pipeline_params.yaml` 的对应关系。
- 增加“不随 GitHub 仓库内置的内容”说明，明确 FASTQ、大型数据库、USEARCH/VSEARCH binary、`.env`、`work/` 和 `run_logs/` 的处理方式。
- 增加常见故障快速定位表，将常见症状映射到优先运行命令和修复方向。

### 主要用户入口

初始化：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

检查配置：

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
```

运行完整流程：

```powershell
python process.py run-pipeline-config --params pipeline_params.yaml
```

生成图表：

```powershell
python process.py visualization-suite --final-dir work\06_final --format html
```

生成报告：

```powershell
python process.py generate-report --final-dir work\06_final
```

启动 Agent：

```powershell
python agent_cli.py
```

## Windows 分发方案增强

### 完成内容

围绕 Windows 用户分发和 GitHub release 场景，增强 `setup_windows.ps1` 并新增分发说明文档。当前项目支持三种分发路线：

- Source install：适合 GitHub 用户和开发者，使用 `setup_windows.ps1` 从源码安装。
- Conda/mamba environment：适合已有 conda/mamba 环境的生信用户，使用 `environment.yml` 创建环境。
- Portable bundle：适合不希望手动安装 Python 的 Windows 用户，使用 `.tools` bundled Python 与 `run_agent.bat`、`run_process.bat` 启动。

### setup_windows.ps1 增强

新增能力：

- `-DiagnosticsOnly`：只执行诊断，不安装依赖、不复制 `.env`、不创建 launcher 或桌面快捷方式。
- `-DiagnosticReportPath`：自定义诊断 JSON 输出路径，默认 `run_logs/windows_setup_diagnostics.json`。
- `-CreateDesktopShortcuts`：在 Windows 桌面创建 Agent 和 CLI help 快捷方式。
- 诊断报告记录 PowerShell、Python、依赖 import smoke test、外部 executables、数据库文件、pipeline config check 和 launcher 状态。
- Diagnostics-only 模式下，如果没有 `.tools` 或 `.venv`，会直接检查系统 Python，不自动创建 `.venv`。

常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -CreateDesktopShortcuts
```

### 分发文档

新增：

- `docs/windows_distribution.md`

该文档说明：

- Source install、Conda/mamba 和 Portable bundle 三种路线。
- Portable bundle 推荐目录结构。
- 公共 GitHub release 不应包含 `.env`、`work/`、`run_logs/`、`seq/`、`databas/`、`bin/`、`.venv/`、`.tools/`。
- 私有实验室 bundle 只有在许可证和本地政策允许时，才建议预置数据库和外部可执行文件。
- release 前检查清单。

### 涉及文件

新增：

- `docs/windows_distribution.md`

修改：

- `setup_windows.ps1`
- `README.md`
- `README_zh.md`
- `X-Amplicon_improvement_roadmap.md`

## 当前验证状态

最近一次全量测试：

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m unittest discover -s tests -p "test_*.py"
```

结果：

```text
Ran 100 tests
OK
```

已单独验证：

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_database_registry
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_process_cli
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_agent_evaluation_logging
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_agent_cli_params tests.test_process_cli
.\.tools\python-3.13.13-amd64\python.exe process.py agent-evaluation-log --help
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly -SkipConfigCheck -NoLauncher
.\.tools\python-3.13.13-amd64\python.exe process.py list-databases
.\.tools\python-3.13.13-amd64\python.exe process.py check-database rdp_16s_v18 --no-hash
.\.tools\python-3.13.13-amd64\python.exe process.py cli-only-workflow
python agent_cli.py --offline --skip-param-confirmation
```

对应结果：

```text
tests.test_database_registry: Ran 5 tests, OK
tests.test_process_cli: Ran 14 tests, OK
tests.test_agent_evaluation_logging: Ran 4 tests, OK
tests.test_agent_cli_params + tests.test_process_cli: Ran 45 tests, OK
agent-evaluation-log --help: success
setup_windows.ps1 -DiagnosticsOnly: success; wrote run_logs/windows_setup_diagnostics.json
list-databases: success
check-database rdp_16s_v18 --no-hash: passed
cli-only-workflow: success
agent_cli.py --offline: success
```

较早已验证：

```text
tests.test_stat_taxonomy: OK
tests.test_report_generator: OK
real work/06_final report generation: success
visualization-suite on current work/06_final: success
```

## 论文和发布说明可复用要点

方法部分可描述：

- X-Amplicon provides an end-to-end Python workflow for 16S amplicon analysis from paired-end FASTQ data to feature tables, taxonomic annotation, diversity metrics, differential abundance analysis, visualization, provenance tracking, and automated report generation.
- Differential abundance analysis uses normalized relative abundance profiles, explicit or user-confirmed group comparisons, non-parametric or Welch t-test statistics, and Benjamini-Hochberg FDR correction.
- Provenance records capture runtime environment, package versions, external executable metadata, effective parameters, reference database metadata, step-level execution state, and output file checksums.
- The visualization layer uses a shared Plotly theme with interactive HTML and optional static export, while organizing each chart family in dedicated directories with index pages.
- The report generator converts completed analysis artifacts into Markdown, HTML, and JSON summaries while separating computational outputs from biological interpretation.
- The database registry records database identity, version, taxonomy format, path, and checksum, improving reproducibility across machines.
- Optional Agent skills provide local project retrieval, trace export, static evaluation, and source-backed PubMed literature retrieval without changing the deterministic core analysis workflow.

Release notes 可写入：

- Added pairwise differential abundance analysis with comparison planning, result tables, volcano plots, and heatmaps.
- Added provenance JSON/Markdown generation with environment, parameter, tool, database, and output checksum records.
- Added publication-ready visualization suite with HTML, PNG, PDF, SVG, custom palette support, and chart indexes.
- Added automated Markdown/HTML/JSON report generation from completed `work/06_final` artifacts.
- Added database registry commands for listing, checking, and registering reference FASTA databases.
- Added optional Agent skills for local project RAG, tracing, static evaluation, and PubMed literature retrieval.
- Added Agent CLI `/language` command for Chinese/English switching.
- Expanded README and CLI documentation for Windows users and CLI-only workflows.

## 后续可继续推进

尚可继续增强的方向：

- Alpha diversity 组间统计检验。
- Beta diversity PERMANOVA / pairwise PERMANOVA。
- ANCOM-BC、LEfSe 或 DESeq2/edgeR 风格的可选高级差异分析接口。
- 更完整的 manuscript-ready HTML report。
- 可编辑报告模板和用户自定义章节。
- 将 Agent tracing 与 provenance/report 联动。
- 将 `agent_evaluation` 扩展为真实任务集 benchmark。
- 增加公共数据集 benchmark、GitHub Actions 和可重复示例数据。

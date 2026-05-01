# X-Amplicon 改进路线图

本文档根据当前论文初稿和项目现状，将可改进内容按实现方式分类，便于后续开发、测试、benchmark 和论文完善。总体目标是让 X-Amplicon 不仅“能够运行”，而且具备可验证的分析可靠性、可复现性、可分发性和论文说服力。

## 总体优先级

| 优先级 | 模块 | 核心目标 | 对论文影响 |
| --- | --- | --- | --- |
| P0 | Benchmark 与可复现实例 | 证明结果可信、流程可复现 | 最高 |
| P0 | Provenance 与运行记录 | 记录软件、参数、数据库和输出来源 | 很高 |
| P0 | 统计分析模块 | 从描述性分析扩展到标准微生物组统计分析 | 很高 |
| P1 | 可视化与报告增强 | 形成 publication-ready outputs | 高 |
| P1 | 自动化测试与 CI | 提高 GitHub 项目可信度 | 高 |
| P1 | Agent 能力评估 | 证明 LLM Agent 不是装饰层 | 高 |
| P2 | 分发与数据库管理 | 降低 Windows 用户安装和配置成本 | 中高 |
| P2 | 跨平台与容器化 | 扩展用户群体 | 中 |

## 1. 通过代码修改实现

### 1.1 统计分析模块

**目标**
在现有 alpha、beta、taxonomy 和 visualization 基础上，加入标准微生物组统计检验，使 X-Amplicon 支持从描述性分析到初步统计推断。

**建议功能**

- Alpha diversity 组间检验：
  - Wilcoxon rank-sum test
  - Kruskal-Wallis test
  - ANOVA，可作为可选方法
- Beta diversity 组间检验：
  - PERMANOVA
  - 可选 pairwise PERMANOVA
- Taxonomy 差异丰度：
  - 基础版本：Kruskal-Wallis/Wilcoxon + FDR correction
  - 进阶版本：ANCOM-BC、LEfSe 或 DESeq2 风格接口作为可选扩展
- Metadata 分组变量读取、校验和自动提示。
- 统计结果表输出到 `work/06_final/statistics`。

**可能新增文件**

- `src/core/stat_alpha.py`
- `src/core/stat_beta.py`
- `src/core/stat_taxonomy.py`
- `src/core/stat_common.py`

**CLI/Agent 接口**

- `process.py alpha-stats`
- `process.py beta-stats`
- `process.py taxonomy-stats`
- Agent tools:
  - `run_alpha_statistics`
  - `run_beta_statistics`
  - `run_taxonomy_differential_abundance`

**论文价值**

可以将结果部分从“生成多样性和分类图表”提升到“完成标准微生物组统计分析”。

### 1.2 Provenance 与 reproducibility 增强

**目标**
让每次分析都产生机器可读的 provenance record，明确记录分析环境、参数、软件版本、数据库版本和输出文件来源。

**建议记录内容**

- X-Amplicon git commit hash。
- Python version。
- 关键 Python package versions。
- USEARCH/VSEARCH 路径和 version。
- 参考数据库名称、路径、文件大小和 hash。
- `pipeline_params.yaml` 的有效参数快照。
- 每一步输入和输出文件路径。
- 关键最终结果文件 hash。
- 每一步开始时间、结束时间、耗时和状态。

**可能修改文件**

- `src/core/raw_amplicon_pipeline.py`
- `src/utils/path_utils.py`
- 新增 `src/utils/provenance.py`

**输出位置**

- `work/06_final/run_summary.json`
- `work/06_final/provenance.json`
- 可选：`work/06_final/provenance.md`

**论文价值**

可以在方法和讨论中强调 X-Amplicon 的可重复性不是口头声明，而是由运行时记录直接支撑。

### 1.3 可视化升级为 publication-ready 输出

**目标**
让当前 Plotly 可视化更适合论文、报告和用户交付。

**建议功能**

- 统一图表主题、字体、坐标轴风格和颜色方案。
- 支持 metadata group 自动排序。
- Taxonomy 图支持 top N taxa + Others 合并。
- 支持用户自定义 color palette。
- 支持稳定输出 HTML、PNG、PDF、SVG。
- 每类图表生成一个 `index.html`。
- 所有图表继续按子目录组织，避免全部堆在 `work/06_final` 下。

**建议输出结构**

```text
work/06_final/plots/
  alpha_boxplot_chart/
  alpha_barplot_chart/
  alpha_rare_chart/
  beta_pcoa_chart/
  beta_cpcoa_chart/
  beta_heatmap_chart/
  taxonomy_stacked_bar_chart/
  taxonomy_heatmap_chart/
  index.html
```

**可能修改文件**

- `src/core/viz_common.py`
- `src/core/viz_alpha.py`
- `src/core/viz_beta.py`
- `src/core/viz_taxonomy.py`

**论文价值**

可在结果部分展示图表面板，增强论文的完整性和可读性。

### 1.4 自动报告生成器增强

**目标**
将当前 `/report` 从会话摘要升级为标准分析报告生成器。

**建议功能**

- 输出 Markdown 和 HTML。
- 自动嵌入关键图表。
- 汇总样本数量、reads 数、过滤比例、最终特征数量。
- 汇总 alpha、beta、taxonomy、statistics 结果。
- 自动列出参数、软件版本和数据库信息。
- 明确区分“计算结果”和“需要研究者判断的生物学解释”。

**可能修改文件**

- `agent_cli.py`
- `agent/state.py`
- 新增 `src/core/report_generator.py`

**输出位置**

```text
work/06_final/report/
  analysis_report.md
  analysis_report.html
```

**论文价值**

可以展示 X-Amplicon 从数据处理到报告生成的完整闭环。

### 1.5 Database 管理模块

**目标**
减少参考数据库配置混乱，提高跨机器复现能力。

**建议功能**

- 数据库 registry：
  - database name
  - version
  - taxonomy format
  - sequence path
  - hash
- 数据库检查命令：
  - `process.py list-databases`
  - `process.py check-database`
  - `process.py register-database`
- 在 `run_summary.json` 或 `provenance.json` 中记录实际使用数据库。

**可能新增文件**

- `src/core/database_registry.py`
- `databases.example.yaml`

**论文价值**

增强可重复性，避免审稿人质疑数据库版本和 taxonomy 注释来源。

### 1.6 无 LLM 模式强化

**目标**
强调 LLM 是交互层，而不是分析流程的必需依赖。即使没有 API key，用户仍可通过 CLI 完成完整分析。

**建议功能**

- README 中明确 CLI-only workflow。
- `process.py` 覆盖完整分析、统计、可视化和报告。
- `agent_cli.py` 在缺少 LLM 配置时给出清晰提示，而不影响 CLI 使用。

**论文价值**

降低 LLM 不稳定性带来的审稿风险，突出确定性工作流的可靠性。

### 1.7 Agent 评估支持代码

**目标**
为后续 Agent 能力评估提供可记录、可统计的执行日志。

**建议功能**

- 记录每次 tool call 的参数、结果、耗时和错误类型。
- 记录每个用户任务的轮数、成功状态和失败原因。
- 标记错误恢复路径，例如 missing metadata、missing executable、bad tree path。
- 可导出 `agent_evaluation_log.jsonl`。

**可能修改文件**

- `agent/agent.py`
- `agent/tools.py`
- `agent/state.py`

**论文价值**

可以量化 Agent 对错误恢复、工具调用和用户交互效率的贡献。

## 2. 通过测试实现

### 2.1 单元测试

**目标**
确保核心计算模块稳定可靠。

**建议覆盖**

- Alpha diversity 指标计算。
- Rarefaction 深度解析和低深度样本剔除。
- Beta distance matrix 生成。
- UniFrac tree 路径检查。
- SINTAX taxonomy 解析。
- Taxonomy filtering。
- Visualization 输出路径和文件存在性。
- Statistics 模块结果格式。

**建议目录**

```text
tests/
  test_alpha_diversity.py
  test_beta_diversity.py
  test_taxonomy_summary.py
  test_visualization.py
  test_statistics.py
```

### 2.2 CLI smoke tests

**目标**
确保终端命令不会因新功能加入而破坏。

**建议覆盖命令**

- `python process.py --help`
- `python process.py check-pipeline-config --params pipeline_params.yaml`
- `python process.py visualization-suite --help`
- `python process.py alpha-stats --help`
- `python process.py beta-stats --help`
- `python process.py taxonomy-stats --help`
- `python agent_cli.py` 的非交互配置检查或 dry-run 模式。

### 2.3 Agent 与语言切换测试

**目标**
验证中英文 CLI 文案切换不会影响功能理解和命令执行。

**建议覆盖**

- `/language` 输入 Chinese 后切换为中文。
- `/language` 输入 English 后切换为英文。
- `/params` 在两种语言下仍能显示关键参数。
- `/status` 在两种语言下仍能显示 session 信息。
- Agent 工具名称保持英文，不被错误翻译。

### 2.4 Pipeline summary 与 provenance 测试

**目标**
验证成功和失败运行都能产生可诊断记录。

**建议覆盖**

- 成功运行写入 `run_summary.json`。
- 中途失败写入 failed step。
- 缺失输入时错误信息包含相关参数名。
- `provenance.json` 包含 Python version、package versions 和数据库 hash。

### 2.5 GitHub Actions CI

**目标**
让 GitHub 项目具备持续验证能力。

**建议 workflow**

```text
.github/workflows/tests.yml
```

**建议执行**

- 安装 Python 依赖。
- 运行 unit tests。
- 运行 CLI help smoke tests。
- 验证 visualization tool registration。
- 在 Windows runner 上至少跑一次核心测试。

## 3. 通过 benchmark 实现

### 3.1 公共数据集 benchmark

**目标**
证明 X-Amplicon 结果与成熟流程具有可比性。

**建议数据集类型**

- Mock community 数据集：用于验证 taxonomy accuracy。
- 人体或宿主相关 16S 数据集：用于真实 metadata 分组分析。
- 环境微生物组数据集：用于复杂群落和高多样性场景。
- 低质量或测序深度不均数据集：用于鲁棒性测试。

**比较对象**

- QIIME 2。
- nf-core/ampliseq。
- EasyAmplicon。
- USEARCH/VSEARCH scripted baseline。

**指标**

- Retained reads。
- Feature 数量。
- 样本测序深度分布。
- Alpha diversity correlation。
- Beta distance matrix correlation 或 Mantel test。
- Taxonomy rank-level abundance similarity。
- Runtime 和 peak memory。
- 失败步骤数量和 rerun 次数。

### 3.2 可复现实例数据集

**目标**
让审稿人和 GitHub 用户能够快速运行一个完整 demo。

**建议内容**

```text
examples/
  metadata.tsv
  pipeline_params.example.yaml
  README.md
  expected_outputs.md
  download_demo_data.ps1
```

**注意事项**

- 不建议直接提交大型 FASTQ。
- 可使用小型 toy FASTQ 或下载脚本。
- 输出结果不应提交到仓库，只提供 expected output structure。

## 4. 通过 Agent 任务评估实现

### 4.1 错误恢复任务

**目标**
证明 Agent 层能够帮助用户定位和修正常见流程错误。

**建议任务**

- Metadata 文件缺失。
- R1/R2 后缀配置错误。
- VSEARCH 路径缺失。
- USEARCH 路径缺失。
- UniFrac tree 路径无效。
- 用户要求生成所有图表。
- 用户要求切换语言后继续运行。

**评价指标**

- Task success rate。
- Average turns to completion。
- Incorrect tool call rate。
- Recovery success rate。
- 用户需要手动输入的命令数量。

### 4.2 与 CLI-only 使用比较

**目标**
定量说明 Agent 交互是否降低使用成本。

**建议比较**

- 完成同一分析任务所需命令数。
- 参数查找和修改次数。
- 错误恢复时间。
- 初学者任务完成率。
- 用户主观信心评分。

## 5. 通过文档和分发实现

### 5.1 README 增强

**目标**
让新用户无需阅读源码即可完成安装、配置和运行。

**建议内容**

- 项目简介。
- 快速开始。
- Windows 安装方式。
- CLI-only 使用方式。
- Agent CLI 使用方式。
- `/language`、`/params`、`/status`、`/report` 等命令说明。
- 每个 tool 的终端调用方式。
- 依赖 Python 包列表。
- USEARCH/VSEARCH 配置说明。
- RDP/SILVA 数据库准备说明。
- 输出目录结构。
- 常见错误排查。

### 5.2 Windows 分发方案

**建议提供三档**

- Source install：适合开发者。
- Conda/mamba environment：适合生物信息用户。
- Portable bundle：适合普通 Windows 用户。

**已有基础**

- `setup_windows.ps1`
- `requirements.txt`
- `environment.yml`
- `.env.example`

**后续增强**

- 自动检查 Python 版本。
- 可选安装 Kaleido。
- 检查外部 executables。
- 生成桌面或命令行启动脚本。
- 输出诊断报告。

### 5.3 GitHub 仓库整理

**目标**
避免上传敏感文件、大型数据和本地运行产物。

**建议保留**

- 源代码。
- README 和文档。
- tests。
- requirements/environment 文件。
- `.env.example`。
- setup script。
- examples 中的小型示例或下载脚本。

**应排除**

- `.env`
- `work/`
- `seq/`
- `databas/`
- `bin/`
- 大型 FASTQ。
- 本地 Python runtime。
- run logs。

## 6. 通过论文内容增强实现

### 6.1 论文主线收敛

**建议主线**

1. Deterministic and reproducible Windows-oriented 16S workflow。
2. LLM-guided function-calling interface over validated tools。
3. Integrated visualization, reporting, provenance, and error recovery。

**不建议过度强调**

- “全球首个”。
- 尚未实现的 LangGraph state machine。
- 尚未实现的长期记忆。
- 尚未实现的自我改进 reflection。

### 6.2 结果部分建议图表

**建议至少包含**

- Architecture overview。
- End-to-end workflow and output layout。
- Benchmark comparison table。
- Agent error-recovery case。
- Usability comparison。
- Example alpha/beta/taxonomy visualization panel。
- Provenance/run_summary 示例。

### 6.3 讨论部分建议强调

**重点**

- Agent 不替代确定性计算，而是编排可验证工具。
- CLI 与 Agent 共享同一核心函数，减少实现分叉。
- `run_summary.json` 和 `provenance.json` 支撑可追踪性。
- 无 LLM 模式降低部署风险。
- 当前限制包括 Windows 优先、benchmark 尚需完成、数据库许可证和外部工具依赖。

## 7. 建议开发顺序

### 阶段 1：增强可复现基础

- 完成 example dataset 或 demo 下载脚本。
- 增强 `run_summary.json`。
- 新增 `provenance.json`。
- 完成 CLI smoke tests。
- 更新 README。

### 阶段 2：补齐分析能力

- 加入 alpha/beta/taxonomy 统计分析模块。
- 将统计模块接入 `process.py`。
- 将统计模块注册为 Agent tools。
- 在报告中整合统计结果。

### 阶段 3：增强输出质量

- 优化可视化主题。
- 支持 publication-ready PDF/SVG。
- 生成图表 index 页面。
- 升级 Markdown/HTML report。

### 阶段 4：正式评估

- 运行公共数据集 benchmark。
- 与 QIIME 2、nf-core/ampliseq、EasyAmplicon 等比较。
- 完成 Agent 错误恢复评估。
- 完成 usability evaluation。

### 阶段 5：论文定稿

- 填充 Results。
- 补充 Methods 中 benchmark 参数。
- 补充 References。
- 补充 Data and code availability。
- 根据 benchmark 结果收敛 Discussion。

## 8. 可执行检查清单

- [ ] 新增可复现实例数据集或下载脚本。
- [ ] 新增 `provenance.json`。
- [x] 记录 Python/package/executable/database versions。
- [ ] 新增 alpha diversity 统计检验。
- [ ] 新增 beta diversity PERMANOVA。
- [ ] 新增 taxonomy 差异丰度分析。
- [ ] 增强 visualization 输出主题和格式。
- [ ] 生成图表 index HTML。
- [ ] 升级 `/report` 为完整分析报告。
- [x] 新增 database registry。
- [x] 增强无 LLM CLI-only workflow 文档。
- [ ] 新增 CLI smoke tests。
- [ ] 新增 Agent language switching tests。
- [ ] 新增 GitHub Actions。
- [ ] 完成公共数据集 benchmark。
- [x] 新增 Agent 评估支持日志代码。
- [x] 增强 README 安装、运行、输入、依赖和排错说明。
- [x] 增强 Windows 分发脚本、诊断报告和三档分发文档。
- [ ] 完成 Agent 错误恢复 benchmark。
- [ ] 完成 usability evaluation。
- [ ] 将 benchmark 结果写入论文 Results。
- [ ] 将最终参考文献补齐。

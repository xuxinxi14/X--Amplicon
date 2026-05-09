# X-Amplicon Web UI 设计方案

本文档用于规划一个面向湿实验研究人员的 X-Amplicon 本地网页 UI。目标不是把命令行简单搬到网页上，而是把当前确定性的 16S 扩增子分析流程包装成一个低门槛、可检查、可恢复、可复现的本地分析工作台。

## 1. 产品定位

### 1.1 核心目标

X-Amplicon Web UI 应服务于三类典型用户：

| 用户类型 | 常见困难 | UI 需要解决的问题 |
| --- | --- | --- |
| 湿实验研究人员 | 不熟悉命令行、参数含义、文件路径和报错信息 | 用向导式流程完成数据准备、参数确认、运行和结果查看 |
| 课题组内部分析人员 | 需要快速重复处理多批样本 | 用项目管理、参数模板和历史任务复用提高效率 |
| 方法开发和审稿复现人员 | 需要知道参数、数据库、软件版本和输出来源 | 将 provenance、run summary、报告和日志显式展示并可导出 |

### 1.2 设计原则

- 本地优先：所有 FASTQ、metadata、数据库和结果默认只在用户电脑上处理，不上传云端。
- 简单优先：默认只暴露必要选项；高级参数收纳到“高级设置”。
- 可解释：每个关键步骤用自然语言说明正在检查什么、为什么失败、如何修复。
- 可恢复：预检失败不直接结束任务，而是给出缺失项、修复按钮和重新检查入口。
- 可复现：网页 UI 最终仍调用 `process.py` 和现有核心模块，所有参数写入 YAML/JSON，所有结果进入标准 `work/` 结构。
- 中英双语：界面默认跟随用户语言设置，专业术语保留英文或采用“中文（English）”形式。

### 1.3 与 OpenClaw 风格的对应关系

本设计借鉴的是 OpenClaw 类本地工具的交互思路，而不是复制其功能：

- 用浏览器作为主界面，减少用户直接接触终端。
- 启动器负责检查环境、启动本地服务、打开网页。
- 首页显示项目、任务状态、最近结果和可执行动作。
- 复杂能力通过“技能/工具卡片”或“向导步骤”组织。
- 日志和命令仍然保留，但默认折叠，只在调试和复现时展开。

## 2. 总体信息架构

推荐采用一个左侧导航栏加主内容区的本地 Web App。

```text
+--------------------------------------------------------------+
| X-Amplicon                          Language  Settings  Help |
+---------------+----------------------------------------------+
| Dashboard     |                                              |
| New Analysis  |        Current page content                  |
| Projects      |                                              |
| Results       |                                              |
| Databases     |                                              |
| Reports       |                                              |
| Agent         |                                              |
| Settings      |                                              |
+---------------+----------------------------------------------+
```

左侧导航应保持稳定，湿实验用户可以反复通过同一入口完成相同流程。

| 导航项 | 主要用途 |
| --- | --- |
| Dashboard | 当前项目、最近任务、环境状态、快速开始 |
| New Analysis | 新建 16S 分析任务的向导 |
| Projects | 管理多个分析项目和历史运行 |
| Results | 浏览图表、统计结果、报告和下载包 |
| Databases | 查看、检查、注册参考数据库 |
| Reports | 生成、预览和导出分析报告 |
| Agent | 自然语言助手，可选；无 API key 时保留规则化帮助 |
| Settings | Python、USEARCH、VSEARCH、默认路径、语言和主题 |

## 3. 首页 Dashboard

首页只放最常用的信息和动作，避免用户第一次打开时被参数淹没。

### 3.1 页面布局

```text
+-------------------------------------------------------------+
| Start a 16S analysis                                       |
| [New analysis] [Open existing project] [View latest report] |
+-------------------------------------------------------------+
| Environment status                                          |
| Python OK | VSEARCH OK | USEARCH missing | RDP database OK  |
| [Fix missing tools] [Run full check]                        |
+-------------------------------------------------------------+
| Recent projects                                             |
| Project name | Last run | Status | Output | Actions         |
+-------------------------------------------------------------+
| Recent results                                              |
| Alpha | Beta | Taxonomy | Differential | Report             |
+-------------------------------------------------------------+
```

### 3.2 功能细节

- 环境状态卡片：
  - Python package 状态。
  - USEARCH/VSEARCH 路径与版本。
  - 已注册数据库状态。
  - 当前工作目录和默认输出目录。
- 快速动作：
  - 新建分析。
  - 打开最近项目。
  - 继续上次未完成任务。
  - 查看最后一次报告。
- 失败状态：
  - 不显示完整 Python traceback 作为主信息。
  - 主提示使用可操作语言，例如“未找到 VSEARCH，可在 Settings 中指定 vsearch.exe 路径”。
  - 提供“查看技术日志”折叠区域。

## 4. 新建分析向导

New Analysis 是整个 Web UI 的核心。建议采用 5 步向导，但每一步尽量只解决一个问题。

```text
Step 1  Project
Step 2  Input files
Step 3  Sample groups
Step 4  Analysis settings
Step 5  Check and run
```

### 4.1 Step 1: Project

目标：让用户先创建一个清晰的分析项目。

字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| Project name | 当前日期 + analysis | 用于项目列表和输出目录显示 |
| Project location | 当前仓库或用户选择目录 | 项目配置保存位置 |
| Output root | `work` | 映射到 `pipeline_params.yaml` 的 `output_root` |
| Analysis type | `16S rRNA` | 预留 ITS 或 none |

交互：

- 提供“使用示例数据”按钮，方便新用户练习。
- 提供“从已有 `pipeline_params.yaml` 导入”按钮，服务熟练用户。

### 4.2 Step 2: Input Files

目标：让用户完成 metadata、FASTQ 文件夹和文件名匹配检查。

页面分区：

```text
Metadata table
[Choose metadata.txt]  Status: 18 samples detected

FASTQ folder
[Choose seq folder]    Status: 36 paired FASTQ files detected

Pairing rule
Read1 suffix: [_1.fq.gz]
Read2 suffix: [_2.fq.gz]
[Preview sample matching]
```

必须功能：

- metadata 表头检查：
  - `SampleID` 是否存在。
  - 分组列是否存在，默认 `Group`。
  - 样本 ID 是否重复。
  - 是否存在空值。
- FASTQ 匹配检查：
  - 根据 `SampleID + read1_suffix/read2_suffix` 预览匹配结果。
  - 表格显示 `SampleID`、Read1、Read2、状态。
  - 未匹配样本用红色标记。
  - 多余 FASTQ 文件用黄色提示。
- 文件名规则帮助：
  - 显示示例：`KO1_1.fq.gz` 与 `KO1_2.fq.gz`。
  - 支持用户从下拉框选择常见后缀：
    - `_1.fq.gz` / `_2.fq.gz`
    - `_R1.fastq.gz` / `_R2.fastq.gz`
    - `_R1.fq.gz` / `_R2.fq.gz`

### 4.3 Step 3: Sample Groups

目标：用可视化方式确认 metadata 分组，后续用于可视化和差异比较。

页面组件：

- 分组列选择器：默认 `Group`。
- 样本分组摘要：

| Group | Samples | Count |
| --- | --- | --- |
| WT | WT1, WT2, WT3... | 6 |
| KO | KO1, KO2, KO3... | 6 |
| OE | OE1, OE2, OE3... | 6 |

- 分组颜色设置：
  - 默认调色板。
  - 允许用户点击色块修改。
  - 写入 visualization-suite 的 `--color-palette`。
- 差异比较预设：
  - 不运行差异比较。
  - 以某一组为 reference，例如 `WT`。
  - 手动添加比较，例如 `KO:WT`、`KO:OE`。

关键交互：

- 如果某组样本数少于 2，差异比较按钮应提示“样本数不足，不建议运行组间统计”。
- 比较方向要明确显示：`KO:WT` 表示 KO 相对 WT。
- 后续结果页面中也要保留 case/control 定义，避免用户误读 log2FC。

### 4.4 Step 4: Analysis Settings

目标：以“预设 + 高级参数”的方式降低参数理解成本。

#### 基础模式

基础模式只显示推荐选择：

| 设置项 | UI 控件 | 默认值 |
| --- | --- | --- |
| Feature method | 单选卡片 | `usearch-asv` |
| Taxonomy database | 下拉框 | `rdp_16s_v18` |
| Chimera mode | 下拉框 | `ref` |
| Filter route | 下拉框 | `16s` |
| Rarefaction depth | 自动/手动切换 | 自动或当前 YAML 值 |
| Threads | 数字输入 | 自动检测 CPU 后给出建议 |

#### 高级模式

高级模式折叠显示，包含当前 `pipeline_params.yaml` 中的完整可调参数：

- `fastq_stripleft`
- `fastq_stripright`
- `fastq_maxee_rate`
- `feature_minsize`
- `feature_identity`
- `otutab_method`
- `otutab_identity`
- `sintax_cutoff`
- `rarefaction_seed`
- `usearch_path`
- `vsearch_path`
- `reference_db`

每个高级参数应提供：

- 当前值。
- 简短解释。
- 默认值恢复按钮。
- 参数是否影响复现性的提示。

### 4.5 Step 5: Check and Run

目标：运行前集中展示所有关键设置，并调用预检命令。

页面结构：

```text
Analysis summary
Project: root_microbiome_2026_04
Samples: 18
Groups: KO=6, OE=6, WT=6
Feature method: usearch-asv
Database: rdp_16s_v18
Output: work

[Run preflight check]
```

预检通过后：

```text
All required checks passed.
[Start analysis]
```

预检失败时：

```text
3 items need attention
1. VSEARCH executable not found
   [Select vsearch.exe] [Open setup guide]
2. Metadata contains sample IDs without paired FASTQ
   [Show unmatched samples]
3. Database file is missing
   [Select database] [Use bundled small RDP database]
```

底层命令映射：

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
```

## 5. 运行监控页面

运行页面要让用户知道“现在在做什么”，同时不要求用户理解全部日志。

### 5.1 状态模型

建议任务状态统一为：

| 状态 | 含义 |
| --- | --- |
| queued | 已创建任务，等待运行 |
| checking | 正在检查输入、依赖和数据库 |
| running | 正在执行分析 |
| paused | 等待用户修复问题 |
| completed | 完成 |
| failed | 失败 |
| cancelled | 用户取消 |

### 5.2 步骤进度条

```text
Input copy      completed
Merge reads     running
Quality filter  pending
Dereplication   pending
Feature table   pending
Taxonomy        pending
Rarefaction     pending
Diversity       pending
Visualization   pending
Report          pending
```

这些步骤可以根据 `run_summary.json`、日志关键字或后续新增的 job event JSONL 更新。

### 5.3 日志视图

日志分两层：

- 用户日志：
  - 当前步骤。
  - 已处理样本数。
  - 输出文件位置。
  - 可修复错误提示。
- 技术日志：
  - 原始 CLI 输出。
  - Python exception。
  - USEARCH/VSEARCH 输出。
  - 可复制命令。

### 5.4 中断和恢复

MVP 阶段至少支持：

- 取消当前任务。
- 重新运行预检。
- 失败后打开 Settings 修复路径。
- 从上次配置重新开始完整运行。

后续可支持：

- 单步骤重跑。
- 从已有 `work/` 目录继续生成 visualization/report。
- 缓存中间文件并跳过已完成步骤。

## 6. 结果浏览器

Results 页面应该是湿实验用户最常用的交付界面。建议以项目为单位显示结果，并按分析主题分 tab。

```text
Results / Project name

Summary | QC | Alpha | Beta | Taxonomy | Differential | Report | Provenance | Files
```

### 6.1 Summary

展示一页式分析摘要：

- 样本数量。
- 分组数量。
- 输入 reads 数。
- 过滤后 reads 数。
- 最终 OTU/ASV 数。
- 注释数据库。
- 主要输出链接。
- 关键警告。

如果存在 `work/06_final/report/analysis_report.html`，提供“打开完整报告”按钮。

### 6.2 QC

展示运行质量控制信息：

- reads 合并统计。
- 过滤统计。
- 样本保留/丢弃情况。
- rarefaction depth。
- discard samples。
- feature table stats。

MVP 可先从现有输出表和 `run_summary.json` 中读取；后续可增加专门 QC 图。

### 6.3 Alpha

显示：

- Alpha boxplot。
- Alpha barplot。
- Alpha rarefaction。
- 指标选择器：
  - richness
  - chao1
  - ACE
  - shannon
  - simpson
  - invsimpson
- 显示对应数据表下载链接。

需要保留：

- 图表目录来源：`work/06_final/plots/alpha_*`
- 数据来源：`work/06_final/alpha_diversity.txt`

### 6.4 Beta

显示：

- PCoA。
- CPCoA。
- Beta heatmap。
- Beta group test summary。
- 距离指标选择器：
  - braycurtis
  - jaccard
  - euclidean
  - unifrac 或后续支持项。

交互：

- 图表内嵌 HTML。
- 可切换 metric。
- 可下载图表和距离矩阵。

### 6.5 Taxonomy

显示：

- Stacked bar。
- Taxonomy heatmap。
- level 选择器：
  - phylum
  - class
  - order
  - family
  - genus
  - species
- top N 控件。
- Others 合并说明。

用户需要能下载：

- taxonomy summary 表。
- 当前图表 HTML/PNG/SVG。

### 6.6 Differential

显示差异比较结果：

```text
Comparison: [KO_vs_WT v]
Method: wilcox
Case: KO
Control: WT
Features tested: 1308
Significant: 0

[Volcano] [Heatmap] [Result table] [Significant only]
```

功能：

- 比较切换下拉框。
- 显示 case/control 定义。
- 显示 p-value、FDR、log2FC 阈值。
- 显著特征表可搜索、排序、筛选。
- 当显著特征为 0 时，不显示“失败”，而显示“当前阈值下无显著差异”。

底层输出：

```text
work/06_final/statistics/differential/
  comparison_plan.tsv
  comparison_result/
  volcano_chart/
  heatmap_chart/
```

### 6.7 Report

提供：

- 生成报告。
- 预览 Markdown。
- 预览 HTML。
- 下载报告文件夹。
- 重新生成报告。

底层命令：

```powershell
python process.py generate-report --final-dir work\06_final
```

### 6.8 Provenance

展示：

- X-Amplicon 版本或 git commit。
- Python 版本。
- Python package versions。
- USEARCH/VSEARCH 路径和版本。
- 数据库名称、路径、hash。
- 参数快照。
- 关键输出文件 hash。

提供：

- 查看 `provenance.md`。
- 下载 `provenance.json`。
- 下载 `run_summary.json`。
- 复制复现命令。

### 6.9 Files

文件浏览器只显示项目输出目录内的安全路径，避免误操作系统文件。

建议根目录：

```text
work/
  00_input/
  01_merge/
  02_filter/
  03_derep/
  04_feature/
  05_taxonomy/
  06_final/
```

功能：

- 下载单个文件。
- 下载图表目录。
- 打开系统文件夹。
- 文件搜索。

## 7. 数据库管理页面

Databases 页面用于把数据库问题从命令行参数中拿出来单独处理。

### 7.1 页面信息

| 字段 | 说明 |
| --- | --- |
| Name | 数据库名称，例如 `rdp_16s_v18` |
| Version | 数据库版本 |
| Type | 16S/ITS/other |
| Format | SINTAX-compatible FASTA 等 |
| Path | 本地 FASTA 路径 |
| Size | 文件大小 |
| SHA-256 | hash |
| Status | found/missing/hash mismatch |

### 7.2 操作

- 列出数据库：

```powershell
python process.py list-databases
```

- 检查数据库：

```powershell
python process.py check-database rdp_16s_v18
```

- 注册数据库：

```powershell
python process.py register-database --name my_silva --path database\my_silva.fa
```

### 7.3 UI 细节

- 默认突出“内置小型 RDP 数据库”，方便新用户起步。
- 大数据库如 SILVA 不建议放入 GitHub，可提示用户本地注册。
- 注册新数据库时自动计算 hash，但允许用户选择“稍后计算”以节省时间。

## 8. Agent 页面

Agent 页面应保持可选，不应成为完成分析的唯一入口。

### 8.1 有 LLM API key 时

功能：

- 自然语言问答。
- 解释预检错误。
- 帮用户选择参数。
- 根据 metadata 推荐差异比较方案。
- 引导生成报告。
- 联网文献检索入口，用于解释背景和结果，但不直接改变确定性分析结果。

### 8.2 无 LLM API key 时

显示“规则化助手”：

- 常见问题搜索。
- 当前项目状态解释。
- 根据错误码显示修复建议。
- 一键复制 CLI 命令。
- 链接到 README 和教程。

### 8.3 安全边界

- Agent 不能静默修改已完成结果。
- Agent 推荐的操作必须显示命令和参数。
- 涉及删除、覆盖、重新运行分析时必须二次确认。
- 文献检索结果与实际分析结果明确分区。

## 9. Settings 页面

Settings 页面用于集中管理环境和默认值。

### 9.1 Environment

- Python executable。
- Python package check。
- USEARCH path。
- VSEARCH path。
- 默认输出目录。
- 默认 metadata sample ID column。
- 默认 group column。

### 9.2 Language

- English。
- Chinese。
- 专业术语策略：
  - `OTU/ASV` 保留英文。
  - `metadata` 可显示为 `metadata 元数据表`。
  - `provenance` 可显示为 `provenance 可追溯记录`。
  - `differential abundance` 可显示为 `差异丰度分析`。

### 9.3 Visualization Defaults

- 默认格式：HTML。
- 静态图格式：PNG/PDF/SVG/all。
- 默认调色板。
- taxonomy 默认 level。
- beta 默认 metric。

### 9.4 Advanced

- 清理缓存。
- 导出设置。
- 导入设置。
- 查看 Web UI 后端日志。
- 重建项目索引。

## 10. 后端服务设计

推荐 Web UI 作为本地服务运行。

### 10.1 技术路线

推荐正式版本：

| 层 | 推荐技术 | 原因 |
| --- | --- | --- |
| 后端 | FastAPI | 适合本地 API、WebSocket 日志、异步任务 |
| 前端 | React + Vite + TypeScript | 适合复杂表格、图表嵌入、状态管理 |
| UI 组件 | Ant Design 或 Mantine | 表单、步骤条、表格和通知组件成熟 |
| 任务运行 | subprocess + job manager | 直接复用 `process.py` |
| 数据存储 | SQLite + JSON/YAML 文件 | 管理项目和任务历史 |
| 图表展示 | 直接嵌入现有 Plotly HTML | 最大化复用当前可视化输出 |

MVP 可选路线：

| 方案 | 优点 | 限制 |
| --- | --- | --- |
| Streamlit | 开发最快，适合原型 | 多任务、文件浏览和长期运行任务控制较弱 |
| NiceGUI | Python-only，适合本地工具 | 生态和复杂前端组件不如 React |
| FastAPI + Jinja2 | 简单、依赖少 | 前端交互能力有限 |

建议：先用 FastAPI + React 设计架构；如果希望 1-2 周内做 MVP，可先用 NiceGUI 或 Streamlit 验证流程。

### 10.2 推荐目录结构

```text
webui/
  backend/
    app.py
    api/
      projects.py
      jobs.py
      files.py
      databases.py
      settings.py
    services/
      pipeline_runner.py
      metadata_validator.py
      result_indexer.py
      database_service.py
      report_service.py
    models/
      project.py
      job.py
      settings.py
  frontend/
    src/
      pages/
        Dashboard.tsx
        NewAnalysis.tsx
        ProjectList.tsx
        Results.tsx
        Databases.tsx
        Reports.tsx
        Agent.tsx
        Settings.tsx
      components/
        FilePicker.tsx
        SamplePairingTable.tsx
        ParameterForm.tsx
        JobProgress.tsx
        PlotFrame.tsx
        ResultTable.tsx
      i18n/
        en.json
        zh.json
  launcher/
    start_webui.ps1
```

### 10.3 API 草案

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/health` | GET | 检查 Web UI 后端状态 |
| `/api/settings` | GET/PUT | 读取和更新全局设置 |
| `/api/projects` | GET/POST | 列出和创建项目 |
| `/api/projects/{id}` | GET/PUT | 读取和更新项目配置 |
| `/api/projects/{id}/validate-metadata` | POST | 检查 metadata |
| `/api/projects/{id}/preview-pairs` | POST | 预览 FASTQ 配对 |
| `/api/projects/{id}/write-params` | POST | 写出 `pipeline_params.yaml` |
| `/api/projects/{id}/preflight` | POST | 调用 `check-pipeline-config` |
| `/api/projects/{id}/run` | POST | 调用 `run-pipeline-config` |
| `/api/jobs/{job_id}` | GET | 查看任务状态 |
| `/api/jobs/{job_id}/logs` | GET | 查看任务日志 |
| `/api/jobs/{job_id}/stream` | WebSocket | 实时推送任务状态和日志 |
| `/api/jobs/{job_id}/cancel` | POST | 取消任务 |
| `/api/results/{project_id}` | GET | 索引可用结果 |
| `/api/results/{project_id}/figure` | GET | 返回指定图表 HTML |
| `/api/reports/{project_id}/generate` | POST | 生成报告 |
| `/api/databases` | GET/POST | 列出或注册数据库 |
| `/api/databases/{name}/check` | POST | 检查数据库 |

### 10.4 Job Event JSONL

建议新增一个轻量任务事件文件，便于 UI 稳定读取进度：

```json
{"time":"2026-04-28T10:00:01","job_id":"run_001","stage":"preflight","status":"running","message":"Checking metadata"}
{"time":"2026-04-28T10:00:05","job_id":"run_001","stage":"preflight","status":"completed","message":"All checks passed"}
{"time":"2026-04-28T10:00:06","job_id":"run_001","stage":"merge","status":"running","message":"Merging paired-end reads"}
```

现有 `agent_evaluation_log.jsonl` 和 provenance 机制可作为参考，但 Web UI 任务事件应更贴近任务进度展示。

## 11. CLI 映射

Web UI 不应绕过现有 CLI，而应生成并执行等价命令。

| UI 操作 | 底层命令 |
| --- | --- |
| 环境检查 | `python process.py check-pipeline-config --params pipeline_params.yaml` |
| 运行完整流程 | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| 生成可视化 | `python process.py visualization-suite --final-dir work\06_final --format html` |
| 运行差异比较 | `python process.py differential-abundance --compare KO:WT --format html` |
| 按 reference 运行差异比较 | `python process.py differential-abundance --reference-group WT --format html` |
| 生成报告 | `python process.py generate-report --final-dir work\06_final` |
| 列出数据库 | `python process.py list-databases` |
| 检查数据库 | `python process.py check-database rdp_16s_v18` |
| 写 provenance | `python process.py write-provenance --summary work\06_final\run_summary.json` |

UI 中应提供“复制命令”按钮，帮助用户在需要时回到终端复现同一操作。

## 12. 关键交互细节

### 12.1 文件选择

浏览器出于安全限制不能随意读取本地路径。Windows 本地 Web UI 可采用以下策略：

- 前端文件选择只用于选择文件名和上传小文件。
- 对 FASTQ 大文件不建议上传复制，优先由后端提供本地路径选择接口。
- `start_webui.ps1` 启动本地服务后，后端可以通过安全白名单访问用户选择的目录。
- 所有路径必须限制在项目目录或用户显式授权的目录内。

### 12.2 大文件策略

- 不把 FASTQ 复制到浏览器缓存。
- 不在网页中打开 FASTQ 内容。
- 只读取文件名、大小、修改时间和 gzip 状态。
- 输入目录只显示匹配摘要，不默认列出上万文件。

### 12.3 错误提示

错误信息采用三层结构：

```text
发生了什么：
未找到样本 KO1 的 R2 文件。

为什么重要：
双端测序分析需要每个样本同时具有 Read1 和 Read2。

如何修复：
检查 FASTQ 文件名是否为 KO1_2.fq.gz，或在上一步修改 Read2 suffix。
```

技术日志保持可展开：

```text
Show technical details
```

### 12.4 参数保护

- 基础模式中不允许用户输入明显无效值。
- 高级参数修改后显示“已偏离默认值”标记。
- 运行前生成参数差异摘要。
- 允许导出和导入参数模板。

### 12.5 图表体验

- 结果页面直接内嵌 Plotly HTML。
- 图表外提供：
  - 打开新窗口。
  - 下载 HTML。
  - 下载静态图。
  - 打开所在文件夹。
- 如果静态图导出失败，应提示安装 `kaleido`，但不阻断 HTML 图查看。

## 13. 推荐 MVP 范围

为了尽快降低使用门槛，第一版不需要实现所有理想功能。建议 MVP 聚焦 6 个能力。

### 13.1 MVP 必做

- 本地启动脚本 `start_webui.ps1`。
- Dashboard 环境状态。
- New Analysis 五步向导。
- metadata 和 FASTQ 配对预检。
- 调用 `run-pipeline-config` 并实时显示日志。
- Results 页面浏览 HTML 图表和报告。

### 13.2 MVP 可暂缓

- 多用户权限。
- 云端任务队列。
- 单步骤断点恢复。
- 图表在线编辑器。
- 数据库自动下载。
- 复杂 Agent 自动操作。

### 13.3 MVP 完成标准

用户可以在不手写命令的情况下完成：

1. 选择 metadata。
2. 选择 FASTQ 目录。
3. 确认样本分组。
4. 使用默认参数运行预检。
5. 启动完整分析。
6. 查看 alpha/beta/taxonomy/differential 图表。
7. 生成 HTML 报告。
8. 下载 provenance 和复现命令。

## 14. 分阶段开发路线

### Phase 1: 本地任务壳和配置向导

目标：把 CLI 可靠地包装进网页。

- 建立 `webui/backend`。
- 建立项目配置模型。
- 实现 metadata 校验。
- 实现 FASTQ 配对预览。
- 实现写出 `pipeline_params.yaml`。
- 实现 preflight 调用。
- 实现 run 调用和日志流。

### Phase 2: 结果索引和图表浏览

目标：让用户在网页中消费结果。

- 扫描 `work/06_final`。
- 读取 `run_summary.json`。
- 读取 `provenance.json`。
- 内嵌 `plots/index.html` 或具体图表。
- 内嵌 differential volcano/heatmap。
- 生成和预览 report。

### Phase 3: 数据库和环境管理

目标：解决新用户最常见安装和路径问题。

- 数据库列表、检查和注册。
- USEARCH/VSEARCH 路径设置。
- Python package 检查。
- `setup_windows.ps1` 状态展示。
- 一键复制修复命令。

### Phase 4: Agent 和帮助系统

目标：让自然语言帮助成为增强层。

- 接入现有 `agent_cli.py` 能力或抽象 Agent service。
- 无 LLM 模式提供规则化帮助。
- 有 LLM 模式提供错误解释和参数建议。
- 文献检索结果嵌入报告草稿，但不自动改变分析结果。

### Phase 5: 打包分发

目标：让 Windows 用户可以双击启动。

- `start_webui.ps1` 启动本地后端和前端。
- 可选打包为 portable zip。
- 可选打包为 Windows installer。
- 首次启动显示 setup checklist。
- 自动打开 `http://127.0.0.1:<port>`。

## 15. 视觉风格建议

界面应采用实验室工具风格，而不是营销首页风格。

### 15.1 总体风格

- 背景：浅灰或白色。
- 主色：克制蓝绿或蓝色，用于主要按钮和状态。
- 辅色：用于分组颜色，不要全站使用大面积渐变。
- 字体：系统默认字体，保证 Windows 显示稳定。
- 卡片圆角：6-8 px。
- 图表区域：宽屏、留白清晰。

### 15.2 信息密度

- 表格和参数页应适当紧凑。
- 首页和向导页应更宽松。
- 避免大段说明文字，使用提示框、tooltip 和“更多说明”折叠。

### 15.3 状态颜色

| 状态 | 颜色建议 |
| --- | --- |
| OK/completed | 绿色 |
| running | 蓝色 |
| warning | 橙色 |
| failed/missing | 红色 |
| skipped | 灰色 |

## 16. 后续需要补充的代码能力

为了让 Web UI 更稳定，建议在核心程序中逐步补充以下能力：

- 参数 schema：为 `pipeline_params.yaml` 提供机器可读字段定义、默认值、类型和说明。
- JSON 输出模式：为关键 CLI 命令增加 `--json`，减少 UI 解析文本日志。
- 任务事件：每一步写入统一 job event JSONL。
- 结果索引器：扫描 `work/06_final` 并输出 `result_index.json`。
- 错误码体系：把常见错误映射为稳定错误码和修复建议。
- 安全文件 API：限制 UI 只能访问项目目录和用户授权目录。
- Web UI 配置文件：保存语言、默认路径、工具路径和主题。

## 17. 建议的首批页面验收清单

| 页面 | 验收标准 |
| --- | --- |
| Dashboard | 能看到 Python、USEARCH、VSEARCH、数据库和最近项目状态 |
| New Analysis | 能完成 metadata、FASTQ、分组、参数、预检和启动分析 |
| Run Monitor | 能看到任务阶段、实时日志、失败原因和输出目录 |
| Results | 能打开 alpha、beta、taxonomy、differential 图表和 report |
| Databases | 能列出、检查和注册数据库 |
| Settings | 能设置语言、工具路径、默认输出目录和可视化格式 |

## 18. 最小用户路径示例

这是第一版 UI 应保证最顺畅的路径：

1. 用户双击 `start_webui.ps1`。
2. 浏览器自动打开 X-Amplicon。
3. 首页提示 VSEARCH、USEARCH、数据库是否可用。
4. 用户点击 `New analysis`。
5. 用户选择 `metadata.txt`。
6. 用户选择 `seq` 文件夹。
7. UI 自动匹配样本并显示 18 个样本、3 个分组。
8. 用户保持默认参数。
9. 用户点击 `Run preflight check`。
10. 检查通过后点击 `Start analysis`。
11. 运行完成后自动跳转到 Results。
12. 用户查看图表、差异比较和报告。
13. 用户下载报告与 provenance。

## 19. 设计结论

X-Amplicon Web UI 的关键价值是把“命令行流程”转化为“本地分析工作台”。对湿实验用户而言，最重要的不是提供更多参数，而是减少第一次运行时的不确定性：文件是否放对、分组是否识别、数据库是否可用、程序现在运行到哪里、失败后应该怎么修复、最终结果在哪里。

因此，第一版应优先实现项目向导、预检、任务监控和结果浏览。Agent、文献检索和高级报告生成可以作为增强层接入，但不应替代确定性 CLI 和 provenance 记录。这样的设计既能降低使用门槛，也能保持 X-Amplicon 当前最重要的优势：可复现、可审计、可在 Windows 本地独立运行。

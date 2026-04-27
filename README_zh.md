[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon 是一个面向 16S rRNA 扩增子双端测序数据的 Python 工作流和 AI Agent。它可以从原始 paired-end FASTQ 与 metadata 出发，完成序列合并、质量控制、去冗余、OTU/ASV 生成、去嵌合体、OTU 表构建、物种注释、过滤、等量抽样、alpha/beta 多样性、taxonomy summary、可视化和两组差异丰度分析。

推荐的确定性入口是 `process.py run-pipeline-config`，参数由 `pipeline_params.yaml` 管理。Agent 模式是可选交互层：`agent_cli.py` 会通过自然语言调用同一批核心工具，但完整分析、可视化、统计、provenance、数据库检查和报告生成都可以在没有 LLM API key 的情况下通过 CLI 完成。

## 功能速览

| 项目 | 当前状态 |
| --- | --- |
| 主要平台 | Windows 优先；Python CLI 可按需迁移到其他系统 |
| 推荐确定性入口 | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| 是否必须使用 LLM | 核心流程不需要；只有自然语言 Agent 编排需要 LLM API key |
| 输入数据 | 双端 FASTQ 文件和样本 metadata 表 |
| 主要输出 | OTU/ASV 表、taxonomy 表、alpha/beta 多样性、可视化、差异丰度、provenance、报告 |
| 外部工具 | 完整 raw FASTQ 流程需要 USEARCH 和 VSEARCH |
| Git 是否包含大文件 | 不包含；FASTQ、数据库和可执行文件由用户本地提供 |

按使用场景选择入口：

| 用户目标 | 推荐路线 |
| --- | --- |
| 从参数文件运行可复现分析 | 编辑 `pipeline_params.yaml`，再运行 `process.py run-pipeline-config` |
| 检查输入和可执行文件是否就绪 | `process.py check-pipeline-config --params pipeline_params.yaml` |
| 完全不使用 LLM key | `process.py cli-only-workflow` |
| 用自然语言描述分析步骤 | 配置 LLM API key 后运行 `agent_cli.py` |
| 只使用 Agent shell 但不启用 LLM | `agent_cli.py --offline` |
| 完整流程后生成论文级输出 | 依次运行 `visualization-suite`、`differential-abundance`、`generate-report` |

所有命令示例默认在仓库根目录运行：

```powershell
cd X-Amplicon
```

## 1. 快速开始

首次在 Windows 上使用时，先运行初始化脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

国内网络安装依赖较慢时可以使用清华 PyPI 镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror
```

如果需要导出 `png`、`pdf`、`svg` 或 `all` 静态图，加上 `-InstallStaticExport` 安装 `kaleido`：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallStaticExport
```

如果需要安装 PubMed 检索、LlamaIndex、Agent evaluation 和 tracing 等可选 Agent skill 依赖，加上 `-InstallSkillDeps`：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
```

运行真实数据前，确认以下本地资源已经准备好：

| 资源 | 常见路径 | 用途 |
| --- | --- | --- |
| Metadata 表 | `metadata.txt` 或用户自定义 TSV 路径 | 完整流程和下游统计 |
| 双端 FASTQ 目录 | `seq\` 或用户自定义目录 | 原始 FASTQ 完整流程 |
| USEARCH 可执行文件 | `bin\windows\usearch.exe` 或 `usearch_path` | ASV/OTU 步骤和部分表格工具 |
| VSEARCH 可执行文件 | `bin\windows\vsearch.exe` 或 `vsearch_path` | OTU 聚类、去嵌合体、SINTAX 注释 |
| RDP/SILVA FASTA 数据库 | `databas\rdp_16s_v18.fa`、`databas\silva_16s_v123.fa` 或已注册数据库 | 去嵌合体和 taxonomy 注释 |

最小端到端命令序列：

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

请把 `WT` 替换为 metadata 中真实的 reference/control 组；也可以先不加 `--reference-group` 运行 `differential-abundance`，只生成 comparison plan 后再确认比较组。

### 1.1 检查配置

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
```

这个命令只验证参数、输入路径、样本匹配和外部可执行文件，不启动耗时分析。

等价预检查入口：

```powershell
python process.py run-pipeline-config --params pipeline_params.yaml --check-only
```

`--dry-run` 是 `--check-only` 的同义入口。

数据库 registry 预检查：

```powershell
python process.py list-databases
python process.py check-database rdp_16s_v18
```

### 1.2 运行完整流程

```powershell
python process.py run-pipeline-config --params pipeline_params.yaml
```

### 1.3 生成标准可视化

完整流程完成后运行：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

默认图表输出到 `work\06_final\plots\`，每类图表单独放入子目录，并生成 `index.html` 方便浏览。

### 1.4 运行差异丰度分析

显式指定比较组：

```powershell
python process.py differential-abundance `
  --compare KO:WT `
  --format html
```

或者指定 reference group，自动生成所有非 reference 组与 reference 组的比较：

```powershell
python process.py differential-abundance `
  --reference-group WT `
  --format html
```

如果没有提供 `--compare` 或 `--reference-group`，X-Amplicon 只生成 `comparison_plan.tsv`，等待用户确认后再运行。

### 1.5 使用 CLI-only 模式

完整工作流不需要 LLM API key：

```powershell
python process.py cli-only-workflow
```

该命令会打印推荐的确定性命令序列，包括数据库检查、参数验证、完整 pipeline、provenance、可视化、统计和报告生成。

### 1.6 启动 Agent

```powershell
python agent_cli.py
```

如果没有配置 LLM API key，`agent_cli.py` 会进入无 LLM 模式。`/params`、`/status`、`/tools`、`/report`、`/config` 和 `/language` 等本地 slash commands 仍可使用；自然语言自动 tool 调用会禁用，直到配置 API key。若希望缺少 LLM 配置时直接启动失败，可使用 `--require-llm`。

常用交互命令：

| 命令 | 作用 |
| --- | --- |
| `/tools` | 查看 Agent 可调用工具 |
| `/params` | 查看当前 pipeline 参数 |
| `/language` | 切换 CLI 语言；输入 `Chinese` 或 `English` |
| `/status` | 查看会话状态 |
| `/report` | 在 `work\06_final\report` 下生成 Markdown 和 HTML 分析报告 |
| `/config` | 查看模型和 API 配置 |
| `/quit` | 退出 |

在终端查看 Agent evaluation 日志：

```powershell
python process.py agent-evaluation-log
python process.py agent-evaluation-log --export-json run_logs\agent_evaluation_log_export.json
```

## 2. 输入文件和参数

完整流程默认读取根目录的 `pipeline_params.yaml`。常用字段如下：

| 参数 | 说明 |
| --- | --- |
| `metadata_path` | metadata 表路径，第一列为样本 ID，或包含 `SampleID` 列 |
| `seq_dir` | 原始双端 FASTQ 文件目录 |
| `read1_suffix` / `read2_suffix` | 根据样本 ID 匹配 R1/R2 文件的后缀 |
| `output_root` | 输出根目录，默认通常是 `work` |
| `fastq_stripleft` / `fastq_stripright` | 过滤前从 reads 两端剪切的碱基数 |
| `fastq_maxee_rate` | 质量过滤最大 expected error rate |
| `feature_method` | `usearch-asv`、`usearch-otu` 或 `vsearch-otu` |
| `feature_minsize` | unique 序列或 feature 生成的最小丰度 |
| `chimera_mode` | `ref` 或 `none` |
| `reference_db` | 用于去嵌合体的已注册数据库名或 FASTA 路径 |
| `otutab_method` | `usearch` 或 `vsearch` |
| `annotation_database` | 用于 SINTAX 注释的已注册数据库名、别名或 FASTA 路径 |
| `filter_route` | `16s`、`its` 或 `none` |
| `rarefaction_depth` | 等量抽样深度，`0` 表示自动取最小样本深度 |
| `rarefaction_seed` | 等量抽样和稀释曲线随机种子 |
| `threads` | 外部命令线程数 |
| `usearch_path` / `vsearch_path` | 可选，显式指定可执行文件路径 |

输入约定：

- metadata 的样本 ID 必须能和 FASTQ 文件名按 `read1_suffix`、`read2_suffix` 匹配。
- OTU/ASV 表以 feature ID 为行、样本 ID 为列，值为 reads count。
- 完整流程会自动从最终 `otus.fa` 生成 `otus.tree`，常规运行不需要手工提供树文件。
- 单独运行 UniFrac beta diversity 时，可以通过 `--tree` 显式提供外部树。

最小输入目录示例：

```text
X-Amplicon/
  pipeline_params.yaml
  metadata.txt
  seq/
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
  bin/
    windows/
      usearch.exe
      vsearch.exe
  databas/
    rdp_16s_v18.fa
```

metadata 表示例：

```text
SampleID	Group
S1	WT
S2	KO
```

对于上面的文件名，`pipeline_params.yaml` 应设置 `read1_suffix: _1.fq.gz` 和 `read2_suffix: _2.fq.gz`。

## 3. 完整流程做什么

`run-pipeline-config` 按以下顺序执行：

1. 读取 metadata 样本 ID。
2. 匹配原始双端 FASTQ。
3. 合并 paired-end reads。
4. 剪切和质量过滤。
5. 去冗余。
6. 生成 OTU 或 ASV 代表序列。
7. 参考库去嵌合体，或按配置跳过。
8. 生成原始 `otutab.txt`。
9. 运行 VSEARCH SINTAX 物种注释。
10. 按 `filter_route` 过滤非目标分类群，生成最终核心结果。
11. 生成 `otutab_rare.txt`、alpha diversity、alpha rarefaction、beta 距离矩阵、taxonomy summary。
12. 如需要图表或两组差异丰度统计，再单独运行 `visualization-suite`、`differential-abundance`，或让 Agent 调用相同工具。

`run-pipeline-config` 默认只产出表格和分析结果；图表是完整流程后的独立步骤。

## 4. 输出结构

默认输出目录结构：

```text
work/
  00_input/
  01_merged/
  02_filtered/
  03_uniques/
  04_features/
  05_raw_results/
  06_final/
    otutab.txt
    otutab_rare.txt
    otutab.id
    otus.fa
    otus.tree
    otus.sintax
    taxonomy.tsv
    run_summary.json
    provenance.json
    provenance.md
    alpha/
      alpha_diversity.tsv
      alpha_rarefaction.tsv
    beta/
      braycurtis.tsv
      jaccard.tsv
      euclidean.tsv
      manhattan.tsv
      unweighted_unifrac.tsv
      weighted_unifrac.tsv
    taxonomy_summary/
      kingdom.tsv
      phylum.tsv
      class.tsv
      order.tsv
      family.tsv
      genus.tsv
      species.tsv
    plots/
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
    report/
      analysis_report.md
      analysis_report.html
      analysis_report_data.json
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

`run_summary.json` 是完整流程的机器可读摘要，Agent 和人工排错都应优先读取它。它记录生效参数、执行步骤、关键输出、等量抽样深度、beta 指标、树文件路径、provenance 路径和失败信息。

`provenance.json` 是每次运行的可重复性记录。它会记录 X-Amplicon git commit 和 dirty state、Python 版本、关键 Python package versions、USEARCH/VSEARCH 路径和尽力获取的软件版本、参考数据库文件信息和 SHA-256 hash、有效参数快照、每一步的时间/状态/文件引用，以及关键最终输出文件 hash。`provenance.md` 是同一记录的简要可读版本。

`beta/` 默认输出 `braycurtis`、`jaccard`、`euclidean`、`manhattan`。`cityblock` 只作为兼容别名接受，文档和输出文件名统一使用 `manhattan`。

Agent 运行时记录默认写到 `work/` 之外：

```text
run_logs/
  agent_tool_trace.jsonl
  agent_evaluation_log.jsonl
```

`agent_tool_trace.jsonl` 是底层 tool-call trace。`agent_evaluation_log.jsonl` 记录 tool-call event 和 user-task event，包括状态、耗时、错误标签和 recovery-path 标签，用于后续 Agent 能力评估。

## 5. CLI 使用总览

查看全部子命令：

```powershell
python process.py --help
```

查看某个子命令参数：

```powershell
python process.py beta-diversity --help
```

下面每个模块统一按“用途、主要输入、主要输出、终端用法”描述。

### 5.1 `check-pipeline-config`

用途：检查 `pipeline_params.yaml`、输入文件、样本匹配、数据库和 USEARCH/VSEARCH 可执行文件。

主要输入：`pipeline_params.yaml`

主要输出：终端检查报告；不写分析结果。

终端用法：

```powershell
python process.py check-pipeline-config `
  --params pipeline_params.yaml
```

### 5.2 `run-pipeline-config`

用途：按 YAML 参数运行完整 16S 分析流程。

主要输入：`pipeline_params.yaml`

主要输出：`output_root\06_final\`、`run_summary.json`、`provenance.json` 和 `provenance.md`

终端用法：

```powershell
python process.py run-pipeline-config `
  --params pipeline_params.yaml
```

只检查不运行：

```powershell
python process.py run-pipeline-config `
  --params pipeline_params.yaml `
  --check-only
```

从已有成功或失败运行的 summary 重新生成 provenance：

```powershell
python process.py write-provenance `
  --summary work\06_final\run_summary.json
```

### 5.2.1 `cli-only-workflow`

用途：打印不依赖 LLM 的确定性工作流，适合完全通过 `process.py` 使用 X-Amplicon。

主要输入：可选的 `pipeline_params.yaml` 路径和输出根目录。

主要输出：终端命令指南；不写分析结果。

终端用法：

```powershell
python process.py cli-only-workflow
```

自定义路径：

```powershell
python process.py cli-only-workflow `
  --params pipeline_params.yaml `
  --output-root work
```

### 5.3 `run-pipeline`

用途：不用 YAML，直接在命令行传参运行完整流程。适合临时覆盖参数或脚本化运行。

主要输入：metadata、FASTQ 目录、过滤参数和流程参数。

主要输出：`--output-root` 下的完整 staged output。

终端用法：

```powershell
python process.py run-pipeline `
  --metadata metadata.txt `
  --seq-dir seq `
  --output-root work `
  --fastq-stripleft 0 `
  --fastq-stripright 0 `
  --fastq-maxee-rate 0.01 `
  --feature-method usearch-asv `
  --otutab-method usearch `
  --annotation-database rdp_16s_v18 `
  --filter-route 16s `
  --rarefaction-depth 0 `
  --rarefaction-seed 1 `
  --threads 4
```

### 5.4 `usearch-asv`

用途：用 USEARCH UNOISE3 从 unique FASTA 生成 ASV/ZOTU 代表序列。

主要输入：去冗余后的 FASTA。

主要输出：ASV/ZOTU FASTA 和相关中间文件。

终端用法：

```powershell
python process.py usearch-asv `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --minsize 10 `
  --threads 4
```

### 5.5 `usearch-otu`

用途：用 USEARCH `cluster_otus` 生成 97% OTU 代表序列。

主要输入：去冗余后的 FASTA。

主要输出：OTU FASTA。

终端用法：

```powershell
python process.py usearch-otu `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --minsize 10 `
  --threads 4
```

### 5.6 `vsearch-otu`

用途：用 VSEARCH 聚类生成 OTU 代表序列。

主要输入：去冗余后的 FASTA。

主要输出：OTU FASTA。

终端用法：

```powershell
python process.py vsearch-otu `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --identity 0.97 `
  --minsize 1 `
  --threads 4
```

### 5.7 `vsearch-uchime-ref`

用途：用 VSEARCH `uchime_ref` 做参考库去嵌合体，也可用 `--chimera-mode none` 跳过。

主要输入：feature FASTA 和参考数据库。

主要输出：非嵌合体 FASTA。

终端用法：

```powershell
python process.py vsearch-uchime-ref `
  --input work\04_features\otus.fa `
  --output work\04_features `
  --reference-db databas\rdp_16s_v18.fa `
  --chimera-mode ref `
  --threads 4
```

### 5.8 `otutab`

用途：将过滤后的 reads 回贴到代表序列，生成 OTU/ASV feature table。

主要输入：过滤 reads FASTA、代表序列 FASTA。

主要输出：OTU/ASV count table。

终端用法：

```powershell
python process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method usearch `
  --threads 4
```

使用 VSEARCH 后端时：

```powershell
python process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method vsearch `
  --identity 0.97 `
  --threads 4
```

### 5.9 `vsearch-sintax`

用途：用 VSEARCH SINTAX 对代表序列做物种注释。

主要输入：OTU/ASV representative FASTA，以及已注册数据库名、别名或 FASTA 路径。

主要输出：`otus.sintax`。

终端用法：

```powershell
python process.py vsearch-sintax `
  --input work\04_features\otus.fa `
  --output work\05_raw_results `
  --database rdp_16s_v18 `
  --sintax-cutoff 0.1 `
  --threads 4
```

`--database` 支持 `rdp`、`silva` 等内置别名，也支持 `databases.yaml` 中注册的名称或直接 FASTA 路径。

### 5.10 `otutab-filter`

用途：按 taxonomy route 过滤 feature table 和代表序列。

主要输入：原始 OTU 表、SINTAX 注释、代表序列 FASTA。

主要输出：过滤后的 `otutab.txt`、`otus.fa`、`otus.sintax`、feature ID 列表和统计表。

终端用法：

```powershell
python process.py otutab-filter `
  --input work\05_raw_results\otutab.txt `
  --taxonomy work\05_raw_results\otus.sintax `
  --representatives work\04_features\otus.fa `
  --output work\06_final `
  --route 16s
```

`--route 16s` 保留 Bacteria/Archaea 并去除 Chloroplast/Mitochondria；`--route its` 保留 Fungi；`--route none` 不过滤。

### 5.11 `otutab-rare`

用途：对 OTU 表等量抽样，并生成 alpha diversity 表和 USEARCH otutab stats。

主要输入：OTU 表。

主要输出：等量抽样 OTU 表、alpha diversity 表、stats 文件。

终端用法：

```powershell
python process.py otutab-rare `
  --input work\06_final\otutab.txt `
  --depth 0 `
  --seed 1 `
  --normalize work\06_final\otutab_rare.txt `
  --output work\06_final\alpha\alpha_diversity.tsv `
  --stats-path work\06_final\otutab_stats.txt
```

### 5.12 `alpha-diversity`

用途：从 OTU 表计算 alpha diversity；可选生成稀释曲线。

主要输入：OTU 表。

主要输出：alpha diversity TSV，可选 rarefaction TSV。

终端用法：

```powershell
python process.py alpha-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\alpha\alpha_diversity.tsv
```

带稀释曲线：

```powershell
python process.py alpha-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\alpha\alpha_diversity.tsv `
  --rarefaction-output work\06_final\alpha\alpha_rarefaction.tsv `
  --depth 1000 `
  --depth 5000 `
  --depth 10000
```

### 5.13 `beta-diversity`

用途：从 OTU 表计算 beta diversity 距离矩阵。

主要输入：OTU 表；UniFrac 还需要树文件。

主要输出：一个或多个距离矩阵 TSV。

终端用法：

```powershell
python process.py beta-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\beta `
  --metric braycurtis `
  --metric jaccard `
  --metric euclidean `
  --metric manhattan
```

计算 UniFrac：

```powershell
python process.py beta-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\beta `
  --metric unweighted_unifrac `
  --metric weighted_unifrac `
  --tree work\06_final\otus.tree
```

### 5.14 `phylogenetic-tree`

用途：从代表序列 FASTA 生成 rooted Newick tree，供 UniFrac 使用。

主要输入：`otus.fa`。

主要输出：`otus.tree`。

终端用法：

```powershell
python process.py phylogenetic-tree `
  --input work\06_final\otus.fa `
  --output work\06_final\otus.tree `
  --linkage max
```

### 5.15 `taxonomy-summary`

用途：解析 SINTAX 注释，并按 taxonomy rank 汇总相对丰度。

主要输入：`otus.sintax`，可选 `otutab.txt`。

主要输出：`taxonomy.tsv` 和 `taxonomy_summary\*.tsv`。

终端用法：

```powershell
python process.py taxonomy-summary `
  --sintax work\06_final\otus.sintax `
  --otutab work\06_final\otutab.txt `
  --output work\06_final
```

只汇总部分层级：

```powershell
python process.py taxonomy-summary `
  --sintax work\06_final\otus.sintax `
  --otutab work\06_final\otutab.txt `
  --rank Phylum `
  --rank Genus `
  --output work\06_final
```

### 5.16 `feature-filter`

用途：按 metadata 分组计算 feature 平均相对丰度，并过滤低丰度 feature。

主要输入：OTU 表和 metadata。

主要输出：分组丰度表。

终端用法：

```powershell
python process.py feature-filter `
  --input work\06_final\otutab.txt `
  --metadata metadata.txt `
  --group-col Group `
  --threshold 0.001 `
  --output work\06_final\group_abundance.tsv
```

注意：`feature-filter` 是独立分析命令，不会在 `run-pipeline-config` 中自动执行。

### 5.17 `visualization-suite`

用途：基于完整流程的 `06_final` 输出批量生成 publication-ready alpha、beta 和 taxonomy 图表。

主要输入：`06_final` 目录，metadata 可自动从 `work\00_input\metadata.txt` 查找。

主要输出：`plots\` 下按图表类型分目录的 HTML/TSV/可选静态图；同时生成 `plots\index.html` 和每个图表子目录内的 `index.html`。

终端用法：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

指定输出目录和部分指标：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --metadata work\00_input\metadata.txt `
  --output-dir work\06_final\plots `
  --format html `
  --beta-metric braycurtis `
  --beta-metric manhattan `
  --taxonomy-level phylum `
  --taxonomy-level genus
```

跳过部分图表：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --skip-cpcoa `
  --skip-beta-stats
```

自定义分组颜色：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format svg `
  --color-palette "WT:#4E79A7,KO:#E15759,OE:#59A14F"
```

`--format png`、`--format pdf`、`--format svg` 或 `--format all` 需要安装 `kaleido`。默认 `html` 不需要。所有图表使用统一的 publication-style Plotly 主题、metadata group 自动排序，并在 taxonomy 图中支持 top-N taxa 与 `Others` 合并。

### 5.18 `differential-abundance`

用途：基于最终 OTU/ASV 表和 metadata 进行两组 taxonomy/feature 差异丰度分析，并生成火山图和热图。

主要输入：`work\06_final\otutab.txt`、`work\00_input\metadata.txt`，以及可选的 `work\06_final\taxonomy.tsv`。

主要输出：`work\06_final\statistics\differential\` 下的 `comparison_plan.tsv`、差异结果表、火山图和热图。

显式比较组用法：

```powershell
python process.py differential-abundance `
  --otutab work\06_final\otutab.txt `
  --metadata work\00_input\metadata.txt `
  --taxonomy work\06_final\taxonomy.tsv `
  --compare KO:WT `
  --compare OE:WT `
  --format html
```

Reference-group 模式：

```powershell
python process.py differential-abundance `
  --reference-group WT `
  --group-col Group `
  --format html
```

Plan 确认模式：

```powershell
python process.py differential-abundance
# 修改 work\06_final\statistics\differential\comparison_plan.tsv，将要运行的行设置为 Include=yes
python process.py differential-abundance `
  --comparison-plan work\06_final\statistics\differential\comparison_plan.tsv `
  --run-confirmed-plan
```

比较方向始终是 `CASE:CONTROL`；`log2FC` 为正表示 case 组平均相对丰度更高。当前 Python 分发版默认支持 `wilcox`，也可选 `t.test`。`edgeR` 需要 R/Bioconductor 运行环境，暂未作为内置实现打包。

### 5.19 `generate-report` / `report`

用途：基于已经完成的 `work\06_final` 目录生成标准 Markdown 和 HTML 分析报告。

主要输入：`run_summary.json`、可选 `provenance.json`、alpha/beta/taxonomy 输出、差异统计结果和可视化文件。

主要输出：`work\06_final\report\analysis_report.md`、`analysis_report.html` 和 `analysis_report_data.json`。

终端用法：

```powershell
python process.py generate-report `
  --final-dir work\06_final
```

别名：

```powershell
python process.py report `
  --final-dir work\06_final
```

常用选项：

```powershell
python process.py generate-report `
  --final-dir work\06_final `
  --output-dir work\06_final\report `
  --top-taxa 10
```

报告会明确区分计算结果和需要研究者判断的生物学解释。HTML 报告会在关键图表存在时嵌入 Plotly HTML 图；建议先运行 `visualization-suite` 再生成报告。

### 5.20 Database registry 命令

用途：管理参考数据库元数据，使每次运行都能记录实际数据库名称、版本、taxonomy format、路径和 SHA-256。

主要输入：`databases.yaml` 以及 `databas\` 或用户自选目录中的本地 FASTA 文件。

主要输出：终端检查报告，以及可选的 `databases.yaml` registry。`databases.yaml` 属于本地配置并已加入 `.gitignore`；可用 `databases.example.yaml` 作为可上传模板。

列出已知数据库：

```powershell
python process.py list-databases
```

按名称、别名或路径检查数据库：

```powershell
python process.py check-database rdp_16s_v18
python process.py check-database databas\rdp_16s_v18.fa --no-hash
```

注册自定义 SINTAX 数据库：

```powershell
python process.py register-database `
  --name custom_16s `
  --path databas\custom_16s.fa `
  --version 2026-04 `
  --taxonomy-format sintax `
  --alias custom16s
```

注册后的数据库名可在 `pipeline_params.yaml` 中作为 `annotation_database` 使用；直接 FASTA 路径仍然兼容。

### 5.21 `agent-evaluation-log` / `agent-eval-log`

用途：汇总或导出交互式 Agent 运行时记录的 user-task 和 tool-call evaluation event。

主要输入：`run_logs\agent_evaluation_log.jsonl`

主要输出：终端摘要；可选 JSON 导出。

终端用法：

```powershell
python process.py agent-evaluation-log
```

导出 JSON：

```powershell
python process.py agent-evaluation-log `
  --export-json run_logs\agent_evaluation_log_export.json
```

使用自定义日志路径：

```powershell
python process.py agent-evaluation-log `
  --log-path run_logs\agent_evaluation_log.jsonl `
  --limit 50
```

日志会记录用户任务轮次、tool-call 数量、耗时、状态、失败原因和常见 recovery 标签，例如 `missing_metadata`、`missing_executable`、`bad_tree_path`、`database_config_error`。

## 6. 单图可视化 Python API

`visualization-suite` 是推荐批量入口；如果只想生成某一类图，也可以在终端调用 Python API。以下命令都可以从仓库根目录直接运行。

所有可视化函数都支持 `output_format='html'`、`'png'`、`'pdf'`、`'svg'` 或 `'all'`。带分组颜色的图也支持 `color_palette='WT:#4E79A7,KO:#E15759,OE:#59A14F'`。

Alpha 箱线图：

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_boxplots; plot_alpha_boxplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha 分组柱状图：

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_barplots; plot_alpha_barplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha 稀释曲线：

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_rarefaction_curve; plot_alpha_rarefaction_curve(alpha_rarefaction_path='work/06_final/alpha/alpha_rarefaction.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta PCoA：

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_pcoa; plot_beta_pcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta C-PCoA：

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_cpcoa; plot_beta_cpcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta 距离热图和组间统计：

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_heatmaps; plot_beta_heatmaps(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy 堆叠柱状图：

```powershell
python -c "from src.core.viz_taxonomy import plot_taxonomy_stacked_bars; plot_taxonomy_stacked_bars(taxonomy_summary_dir='work/06_final/taxonomy_summary', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy 热图：

```powershell
python -c "from src.core.viz_taxonomy import plot_taxonomy_heatmaps; plot_taxonomy_heatmaps(taxonomy_summary_dir='work/06_final/taxonomy_summary', output_format='html')"
```

差异丰度分析：

```powershell
python -c "from src.core.stat_taxonomy import run_taxonomy_differential_abundance; run_taxonomy_differential_abundance(comparisons=['KO:WT'], output_format='html')"
```

分析报告：

```powershell
python -c "from src.core.report_generator import generate_analysis_report; generate_analysis_report(final_dir='work/06_final')"
```

## 7. Agent 工具和终端等价入口

Agent 工具由 `agent/tools.py` 注册。查看当前工具：

```powershell
python agent_cli.py
# 进入后输入 /tools
```

下表列出 Agent 工具和推荐终端入口：

| Agent tool | 推荐终端入口 |
| --- | --- |
| `run_raw_amplicon_pipeline` | `process.py run-pipeline` 或 `process.py run-pipeline-config` |
| `run_usearch_unoise3_denoising` | `process.py usearch-asv` |
| `run_usearch_otu_clustering` | `process.py usearch-otu` |
| `run_vsearch_otu_clustering` | `process.py vsearch-otu` |
| `run_vsearch_uchime_ref` | `process.py vsearch-uchime-ref` |
| `run_vsearch_sintax` | `process.py vsearch-sintax` |
| `run_otutab_generation` | `process.py otutab` |
| `run_otutab_filter` | `process.py otutab-filter` |
| `run_otutab_rare` | `process.py otutab-rare` |
| `calculate_alpha_diversity` | `process.py alpha-diversity` |
| `rarefy_otutab` | `process.py otutab-rare` |
| `calculate_richness_rarefaction_curve` | `process.py alpha-diversity --rarefaction-output ... --depth ...` |
| `calculate_rarefaction_curve` | `process.py alpha-diversity --rarefaction-output ... --depth ...` |
| `calculate_beta_distance` | `process.py beta-diversity` |
| `run_phylogenetic_tree_generation` | `process.py phylogenetic-tree` |
| `calculate_group_abundance` | `process.py feature-filter` |
| `parse_sintax_to_dataframe` | `process.py taxonomy-summary --sintax ... --output ...` |
| `summarize_taxa_abundance` | `process.py taxonomy-summary --sintax ... --otutab ... --output ...` |
| `run_visualization_suite` | `process.py visualization-suite` |
| `build_differential_comparison_plan` | 不带 `--compare` 或 `--reference-group` 运行 `process.py differential-abundance` |
| `run_taxonomy_differential_abundance` | `process.py differential-abundance --compare CASE:CONTROL` |
| `plot_differential_volcano` | Python API，见第 6 节 |
| `plot_differential_heatmap` | Python API，见第 6 节 |
| `generate_analysis_report` | `process.py generate-report` 或 `process.py report` |
| `list_registered_databases` | `process.py list-databases` |
| `check_registered_database` | `process.py check-database` |
| `register_database` | `process.py register-database` |
| `list_agent_eval_cases` | Agent-only 静态 evaluation helper |
| `run_agent_eval_cases` | Agent-only 静态 evaluation helper |
| `inspect_optional_skill_dependencies` | Agent-only 可选依赖检查 |
| `summarize_agent_evaluation_log` | `process.py agent-evaluation-log` |
| `export_agent_evaluation_log` | `process.py agent-evaluation-log --export-json ...` |
| `summarize_agent_traces` | Agent-only trace helper；见 `run_logs\agent_tool_trace.jsonl` |
| `export_agent_traces` | Agent-only trace helper；见 `run_logs\agent_tool_trace.jsonl` |
| `plot_alpha_boxplots` | Python API,见第 6 节 |
| `plot_alpha_barplots` | Python API,见第 6 节 |
| `plot_alpha_rarefaction_curve` | Python API,见第 6 节 |
| `plot_beta_pcoa` | Python API,见第 6 节 |
| `plot_beta_cpcoa` | Python API,见第 6 节 |
| `plot_beta_heatmaps` | Python API,见第 6 节 |
| `plot_taxonomy_stacked_bars` | Python API,见第 6 节 |
| `plot_taxonomy_heatmaps` | Python API,见第 6 节 |

Agent 使用自然语言即可调用这些工具，例如：

```text
Run the full pipeline with the current pipeline_params.yaml.
Generate all standard visualization charts for work/06_final.
Generate the final Markdown and HTML analysis report.
Plot beta PCoA and taxonomy stacked bars from the completed run.
```

## 8. 依赖

请使用当前环境中的 Python 3.10+。Windows 初始化脚本也可以创建本地 `.venv`，或在提供 bundled runtime 时自动使用它：

```powershell
python --version
```

### 8.1 Python 包

核心流程、CLI、Agent 和可视化依赖的 Python 包如下：

| 包 | 用途 |
| --- | --- |
| `pyyaml` | 读取 `pipeline_params.yaml`、`config.yaml` |
| `click` | `process.py` CLI |
| `numpy` | 数值计算、距离矩阵、抽样 |
| `pandas` | 表格读写和汇总 |
| `scipy` | 聚类、统计、距离矩阵辅助计算 |
| `scikit-bio` | alpha/beta diversity、UniFrac、PERMANOVA/ANOSIM |
| `biopython` | FASTA/FASTQ 相关处理 |
| `pydantic>=2.0` | 参数和工具 schema 支持 |
| `plotly>=5.15` | HTML 交互式图表 |
| `rich` | Agent CLI 终端 UI |
| `litellm` | Agent 调用 OpenAI-compatible LLM |
| `kaleido` | 可选，仅用于 Plotly 静态 `png`/`pdf`/`svg` 导出 |

安装 Agent 和可视化常用依赖：

```powershell
python -m pip install litellm rich plotly
```

如需导出静态图：

```powershell
python -m pip install kaleido
```

Conda 环境文件在 `environment.yml`，其中已列出主要依赖。

### 8.2 外部工具

完整流程中的特征生成、去嵌合体、OTU 表构建和注释依赖外部可执行文件：

| 工具 | 默认位置或来源 | 用途 |
| --- | --- | --- |
| USEARCH | `bin/windows/usearch.exe` 或 `--usearch-path` | UNOISE3、cluster_otus、otutab、otutab_stats、fastx_getseqs |
| VSEARCH | `bin/windows/vsearch.exe` 或 `--vsearch-path` | cluster_size、uchime_ref、sintax、usearch_global |

### 8.3 数据库

默认内置兼容记录：

| 文件 | 用途 |
| --- | --- |
| `databas/rdp_16s_v18.fa` | 去嵌合体和 SINTAX 注释 |
| `databas/silva_16s_v123.fa` | 可选 SINTAX 注释数据库 |

大型 FASTA 文件不会上传到 Git。需要固定数据库版本、taxonomy format、别名和 SHA-256 时，可复制 `databases.example.yaml` 为 `databases.yaml` 并按本机路径调整：

```powershell
copy databases.example.yaml databases.yaml
python process.py register-database --name rdp_16s_v18 --path databas\rdp_16s_v18.fa --version v18 --overwrite
python process.py check-database rdp_16s_v18
```

完成运行后，`provenance.json` 会记录数据库元数据，包括文件大小和可用时的 SHA-256。

### 8.4 仓库不内置的内容

GitHub 仓库不会包含本地运行数据或大型第三方资产：

| 内容 | 原因 | 用户需要做什么 |
| --- | --- | --- |
| 原始 FASTQ 文件 | 文件过大且与样本相关 | 放入 `seq\` 或 `pipeline_params.yaml` 指定的其他目录 |
| RDP/SILVA FASTA 数据库 | 文件较大，且版本和分发方式需要用户确认 | 本地下载或准备后，用 `process.py check-database` 检查或注册 |
| USEARCH binary | 许可证和再分发限制 | 单独下载；不在 `bin\windows\` 下时设置 `usearch_path` |
| VSEARCH binary | 平台相关可执行文件 | 安装/下载 Windows 版本；必要时设置 `vsearch_path` |
| `.env`、`work\`、`run_logs\` | 本地密钥和运行产物 | 保持本地使用；这些路径已加入 `.gitignore` |

## 9. Agent 配置

Agent 使用 `.env`、环境变量或命令行参数配置模型和 API。

复制模板：

```powershell
copy .env.example .env
```

常用变量：

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEY` | OpenAI-compatible API key |
| `LLM_API_BASE` | 中转或兼容端点 base URL |
| `DEFAULT_MODEL` | LiteLLM 模型字符串 |
| `OPENAI_API_KEY` | `LLM_API_KEY` 未设置时的备用 key |
| `ANTHROPIC_API_KEY` | 备用 Anthropic key |
| `X_AMPLICON_AGENT_TRACE_PATH` | 可选，底层 tool-call trace JSONL 路径 |
| `X_AMPLICON_AGENT_EVAL_LOG_PATH` | 可选，Agent evaluation event JSONL 路径 |

命令行覆盖模型和端点：

```powershell
python agent_cli.py `
  --model openai/qwen-max `
  --api-key sk-... `
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1
```

查看内置模型示例：

```powershell
python agent_cli.py --list-models
```

LLM 配置对于确定性工作流不是必需的。没有 API key 时可以使用：

```powershell
python process.py cli-only-workflow
```

也可以显式启动 Agent 的无 LLM shell：

```powershell
python agent_cli.py --offline
```

无 LLM 模式下，本地 slash commands 仍可使用，但自然语言 tool calling 会禁用。若希望启动时强制要求有效 LLM 配置，可使用：

```powershell
python agent_cli.py --require-llm
```

## 10. 可选 Agent skills

X-Amplicon 的 Agent 可以通过 `agent/skills/*/tools.py` 自动发现扩展工具。当前内置的可选 skills 包括：

| Skill | Agent tools | 用途 |
| --- | --- | --- |
| `local_project_rag` | `search_project_files`, `read_project_file`, `read_analysis_summary`, `find_output_artifacts`, `preview_llama_index_documents` | 检索 README、论文草稿、参数文件、`run_summary.json` 和输出 artifacts；可选使用 LlamaIndex 预览 documents |
| `agent_tracing` | `summarize_agent_traces`, `export_agent_traces` | 汇总和导出 Agent tool-call JSONL trace |
| `agent_evaluation` | `list_agent_eval_cases`, `run_agent_eval_cases`, `inspect_optional_skill_dependencies`, `summarize_agent_evaluation_log`, `export_agent_evaluation_log` | 运行静态 Agent 能力检查，检查可选依赖，汇总/导出任务与 tool-call evaluation event |
| `literature_evidence` | `search_pubmed_literature`, `fetch_pubmed_abstracts` | 通过 Biopython Entrez 检索 PubMed 文献，需要联网和 `NCBI_EMAIL` |

安装可选 skill 依赖：

```powershell
python -m pip install -r requirements-skills.txt
```

或者在首次初始化时安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
```

PubMed 文献检索需要在 `.env` 或系统环境变量中配置：

```env
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=optional-ncbi-api-key
```

查看所有已注册工具：

```powershell
python agent_cli.py
# 进入后输入 /tools
```

也可以通过自然语言调用这些 skills，例如：

```text
Search the project files for run_summary and summarize the latest output.
Summarize recent agent tool traces.
Run the built-in agent evaluation cases.
Summarize the agent evaluation log and show common recovery paths.
Search PubMed for recent 16S microbiome benchmark papers.
```

Agent 的联网文献检索只用于提供来源支持的背景资料或参考文献，不应替代当前项目尚未完成的 benchmark 或生物学验证。

## 11. 常见问题和排错

先用这张表快速定位，再看后面的详细说明：

| 现象 | 优先运行的命令 | 常见修复方式 |
| --- | --- | --- |
| Pipeline 在正式分析前失败 | `python process.py check-pipeline-config --params pipeline_params.yaml` | 修复 metadata、FASTQ 路径、可执行文件或数据库路径 |
| 样本匹配失败 | `python process.py check-pipeline-config --params pipeline_params.yaml` | 让 `SampleID`、`read1_suffix`、`read2_suffix` 与真实 FASTQ 文件名一致 |
| 找不到 USEARCH/VSEARCH | `python process.py check-pipeline-config --params pipeline_params.yaml` | 在 `pipeline_params.yaml` 中设置 `usearch_path` 和 `vsearch_path` |
| SINTAX 或去嵌合体数据库缺失 | `python process.py check-database rdp_16s_v18` | 注册数据库，或使用直接 FASTA 路径 |
| 没有生成图表 | `python process.py visualization-suite --final-dir work\06_final --format html` | 完整流程结束后再运行可视化；只有静态格式需要安装 `kaleido` |
| Agent 无法自然语言调用工具 | `python agent_cli.py --offline` | 使用 CLI-only 模式，或配置有效 LLM API key |

### 11.1 先看 `run_summary.json`

完整流程完成或失败后，优先检查：

```text
work\06_final\run_summary.json
```

它比终端滚动日志更适合作为自动报告和排错依据。

### 11.2 找不到 USEARCH 或 VSEARCH

先运行：

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
```

如果提示可执行文件不可用，在 `pipeline_params.yaml` 中设置 `usearch_path`、`vsearch_path`，或在命令中传入：

```powershell
--usearch-path bin\windows\usearch.exe --vsearch-path bin\windows\vsearch.exe
```

### 11.3 样本匹配失败

检查三项：

- metadata 第一列或 `SampleID` 列是否和 FASTQ 样本前缀一致。
- `read1_suffix`、`read2_suffix` 是否和文件名一致。
- `seq_dir` 是否指向真正的 FASTQ 目录。

### 11.4 UniFrac 没有输出

完整流程会自动从 `work\06_final\otus.fa` 生成 `otus.tree`。如果单独运行 `beta-diversity`，需要显式传：

```powershell
--tree work\06_final\otus.tree
```

### 11.5 可视化没有 PNG/PDF/SVG

默认 `html` 不需要额外依赖。静态图需要：

```powershell
python -m pip install kaleido
```

然后运行：

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format all
```

### 11.6 什么时候用 Agent，什么时候用 CLI

- 想稳定复现或写脚本：优先用 `process.py`。
- 想让系统根据自然语言选择步骤、解释结果或自动生成图表：用 `agent_cli.py`。
- 想验证能否开跑：用 `check-pipeline-config`。
- 想汇总已经完成的运行：读 `run_summary.json`，再按需运行 `visualization-suite`。

## 12. Windows 分发方案

X-Amplicon 目前支持三种面向 Windows 的分发路线。完整检查清单见
[docs/windows_distribution.md](docs/windows_distribution.md)。

| 路线 | 适合用户 | 主要命令 |
| --- | --- | --- |
| Source install | GitHub 用户和开发者 | `powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1` |
| Conda/mamba environment | 已使用 conda 的生信用户 | `mamba env create -f environment.yml` |
| Portable bundle | 不希望手动安装 Python 的 Windows 用户 | 解压准备好的 bundle 后运行 `.\run_process.bat --help` |

`setup_windows.ps1` 已支持分发相关检查和输出：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -CreateDesktopShortcuts
```

默认诊断报告输出到：

```text
run_logs/windows_setup_diagnostics.json
```

公开 GitHub release 不应包含 `.env`、`work\`、`run_logs\`、`seq\`、
`databas\`、`bin\`、`.venv\` 或 `.tools\`。如果是实验室内部私有 bundle，
只有在许可证和本地政策允许时，才建议预置数据库和可执行文件目录。


[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon 是一个面向 Windows 本地环境的 16S rRNA 扩增子分析 Agent 和可复现 Python 工作流。推荐入口是浏览器 Web UI：用户可以在网页中完成项目创建、metadata 检查、双端 FASTQ 配对预览、参数配置、流程运行、结果浏览、数据库管理和可选的 LLM 辅助引导。

底层确定性流程仍然由 `process.py` 提供。Web UI 和 CLI 调用同一套核心工具，因此分析可以通过命令、参数文件、日志、`run_summary.json` 和 provenance 记录复现。LLM API key 不是必需项：pipeline、Web UI 检查、可视化、差异丰度分析、报告生成和大部分帮助功能都可以在无 LLM 情况下运行。

## 推荐入口：Web UI

### 1. 安装

所有命令默认在仓库根目录运行：

```powershell
cd X-Amplicon
```

安装核心 Python 依赖和 Web UI 后端依赖：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

如果 PyPI 访问较慢，可以使用清华镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

常用安装选项：

| 选项 | 用途 |
| --- | --- |
| `-InstallWebUIDeps` | 安装 Web UI 所需的 FastAPI、uvicorn、文件上传和异步文件服务依赖 |
| `-InstallStaticExport` | 安装 `kaleido`，用于导出 `png`、`pdf`、`svg` 静态图 |
| `-InstallSkillDeps` | 安装可选的 local RAG、文献检索、tracing 和 evaluation 依赖 |
| `-UseChinaMirror` | 使用清华 PyPI 镜像 |
| `-SkipConfigCheck` | 安装时跳过 `pipeline_params.yaml` 初始检查 |

完整本地安装示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps -InstallStaticExport -InstallSkillDeps
```

### 2. 启动 Web UI

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

启动脚本会运行本地 FastAPI 服务、打开浏览器，并由同一个本地地址提供 React 前端。默认地址是：

```text
http://127.0.0.1:8765
```

如果默认端口被占用，启动脚本会自动尝试后续可用端口。

常用启动选项：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -BuildFrontend
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBuild
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Dev
```

生产模式只启动一个 FastAPI 服务。如果 `webui\frontend\dist` 不存在且本机有 Node.js/npm，启动脚本可以自动构建前端。开发模式 `-Dev` 会同时启动 FastAPI 和 Vite 开发服务器。

### 3. 配置 Web UI

首次进入网页后先打开 **Settings**。

基础设置：

| 设置 | 常见值 | 说明 |
| --- | --- | --- |
| Python executable | 自动识别 | 优先使用 `.tools`、`.venv` 或系统 Python |
| Output root | `work` | 最终结果写入 `work\06_final` |
| Metadata path | `metadata.txt` | 制表符分隔的样本信息表 |
| FASTQ directory | `seq` | 原始双端 FASTQ 文件目录 |
| Sample ID column | `SampleID` | 用于匹配 metadata 和 FASTQ 文件的列 |
| Group column | `Group` | 用于多样性图和差异比较的分组列 |
| USEARCH path | `bin\windows\usearch.exe` | USEARCH feature 和 table 路线需要 |
| VSEARCH path | `bin\windows\vsearch.exe` | VSEARCH 聚类、去嵌合体和 SINTAX 注释需要 |
| Default plot format | `html` | 只有安装静态导出依赖后再使用 `all` |

Agent LLM access：

- 可以从列表选择模型，也可以手动输入 LiteLLM 兼容模型名。
- 使用代理或自定义网关时填写 OpenAI-compatible API base URL。
- API key 只建议在自己的本机填写。
- API key 会保存到本地 `.env`，`GET /api/settings/llm` 不会把 key 返回给浏览器。
- 需要时可以在同一设置面板清除已保存的 key。

等价 `.env` 字段：

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

确定性分析不需要 API key。没有 key 时，Agent 页面仍然提供规则化引导，CLI Agent 也可以用 no-LLM 模式运行。

### 4. 按向导运行分析

推荐按下面顺序使用 Web UI：

1. **Agent**：先根据分析向导确认数据、metadata、数据库和可执行文件是否准备好。
2. **New Analysis**：创建项目，选择 metadata 和 FASTQ，检查样本匹配，确认分组，设置比较组，写出 `pipeline_params.webui.yaml`。
3. **Run Monitor**：运行 preflight，启动完整 pipeline，查看日志，复制命令，必要时停止任务。
4. **Results**：浏览 Plotly 图、表格、报告、provenance、`run_summary.json` 和输出文件。
5. **Databases**：检查已注册数据库，按需计算 hash，或注册本地 FASTA 数据库。
6. **Settings**：调整默认路径、图表格式、授权目录和可选 LLM 配置。

Web UI 不上传测序文件。FASTQ、数据库、配置、日志和结果都保留在本机。

### 5. 本地输入文件

最小项目目录示例：

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

最小 metadata 示例：

```text
SampleID	Group
S1	WT
S2	KO
```

metadata 中的样本 ID 必须能够在去掉 `read1_suffix` 和 `read2_suffix` 后与 FASTQ 文件名对应。

### 6. 输出结果

标准最终目录是：

```text
work\06_final
```

主要输出：

| 输出 | 位置 |
| --- | --- |
| Feature table | `work\06_final\otutab.txt` |
| 物种注释 | `work\06_final\taxonomy.txt` 和 SINTAX 衍生汇总 |
| Alpha diversity | `work\06_final\alpha_diversity.txt` |
| Beta diversity | `work\06_final\beta_diversity\` |
| 可视化索引 | `work\06_final\plots\index.html` |
| 差异丰度分析 | `work\06_final\differential_abundance\` |
| 分析报告 | `work\06_final\report\analysis_report.html` 和 `.md` |
| 可复现性记录 | `work\06_final\run_summary.json`、`provenance.json`、`provenance.md` |

可视化会按图表类型分别放入子目录，例如 alpha diversity、beta diversity、taxonomy 和 differential abundance。

## 确定性 CLI

CLI 适合自动化运行、问题排查和精确复现。

### 标准端到端命令

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

请把 `WT` 替换为 metadata 中真实的对照组。若只想先生成比较计划：

```powershell
python process.py differential-abundance --final-dir work\06_final
```

### CLI tool 参考

每个命令的完整参数可用 `python process.py <command> --help` 查看。

| Tool | 常用命令 |
| --- | --- |
| 打印 no-LLM 工作流 | `python process.py cli-only-workflow` |
| 检查 pipeline 配置 | `python process.py check-pipeline-config --params pipeline_params.yaml` |
| 按配置运行完整流程 | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| 用显式参数运行完整流程 | `python process.py run-pipeline --help` |
| USEARCH ASV denoising | `python process.py usearch-asv --help` |
| USEARCH OTU clustering | `python process.py usearch-otu --help` |
| VSEARCH OTU clustering | `python process.py vsearch-otu --help` |
| VSEARCH reference chimera check | `python process.py vsearch-uchime-ref --help` |
| VSEARCH SINTAX annotation | `python process.py vsearch-sintax --help` |
| 构建 feature table | `python process.py otutab --help` |
| 按 taxonomy 过滤表 | `python process.py otutab-filter --help` |
| OTU 表等量抽样 | `python process.py otutab-rare --help` |
| Alpha diversity | `python process.py alpha-diversity --help` |
| Beta diversity | `python process.py beta-diversity --help` |
| Phylogenetic tree | `python process.py phylogenetic-tree --help` |
| Taxonomy summary | `python process.py taxonomy-summary --help` |
| Visualization suite | `python process.py visualization-suite --final-dir work\06_final --format html` |
| Differential abundance | `python process.py differential-abundance --reference-group WT --format html` |
| Report generation | `python process.py generate-report --final-dir work\06_final` |
| 刷新 provenance | `python process.py write-provenance --summary-path work\06_final\run_summary.json` |
| 列出数据库 | `python process.py list-databases` |
| 检查数据库 | `python process.py check-database rdp_16s_v18` |
| 注册数据库 | `python process.py register-database --help` |
| Agent evaluation log | `python process.py agent-evaluation-log` |

为了兼容旧入口，程序也保留了 `report`、`taxonomy-stats` 和 `agent-eval-log` 等别名。

### CLI Agent

```powershell
python agent_cli.py
```

no-LLM 模式：

```powershell
python agent_cli.py --offline
```

常用启动参数：

```powershell
python agent_cli.py --model gpt-4o-mini
python agent_cli.py --api-base https://proxy.example.com/v1
python agent_cli.py --resume
python agent_cli.py --reset
python agent_cli.py --params pipeline_params.yaml
python agent_cli.py --require-llm
```

交互式 slash commands：

| 命令 | 用途 |
| --- | --- |
| `/status` | 查看会话状态、结果文件和最近工具运行 |
| `/params` | 查看或更新 pipeline 参数 |
| `/tools` | 查看可用分析工具 |
| `/language` | 在 `Chinese` 和 `English` 之间切换 CLI 语言 |
| `/report` | 生成或预览分析报告 |
| `/config` | 查看模型和 API 配置 |
| `/history` | 查看会话历史 |
| `/quit` | 退出 |

## 依赖

Python 核心包：

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

可选静态图导出：

```text
kaleido
```

Web UI 后端包：

```text
fastapi
uvicorn[standard]
python-multipart
aiofiles
```

可选 Agent skill 包：

```text
llama-index
deepeval
ragas
langchain-openai==1.1.0
opentelemetry-api
opentelemetry-sdk
```

前端开发依赖由 `webui\frontend\package.json` 和 `package-lock.json` 管理。从源码构建 Web UI 时建议使用 Node.js 20+ 和 npm。

外部命令行工具：

- USEARCH：USEARCH ASV/OTU 和 USEARCH table 路线需要。
- VSEARCH：VSEARCH OTU 聚类、reference chimera check 和 SINTAX annotation 需要。

## 开发与验证

后端测试：

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m unittest tests.test_webui_backend tests.test_webui_api_smoke
```

前端测试和构建：

```powershell
cd webui\frontend
npm.cmd run test
npm.cmd run build
cd ..\..
```

Python 语法检查：

```powershell
.\.tools\python-3.13.13-amd64\python.exe -m compileall webui\backend
```

手工 Web UI 验收清单见 [docs/web_ui_manual_e2e_checklist.md](docs/web_ui_manual_e2e_checklist.md)。Web UI 实现计划见 [docs/web_ui_implementation_plan.md](docs/web_ui_implementation_plan.md)，启动与排查指南见 [docs/web_ui_user_guide.md](docs/web_ui_user_guide.md)。

## Git 与分发说明

不要提交本地密钥、运行状态、大型测序数据和生成结果：

```text
.env
.xamplicon_webui/
work/
run_logs/
seq/
webui/frontend/node_modules/
webui/frontend/dist/
```

GitHub 源码用户可以在本地构建前端。面向非开发用户的 Windows release 压缩包可以附带预构建的 `webui\frontend\dist`，这样启动 Web UI 时不需要安装 Node.js。

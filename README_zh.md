[English](README.md) | [中文](README_zh.md)

# 🧬 X-Amplicon
作者：徐新玺

X-Amplicon 是一个以 Windows 本地环境为核心的 16S rRNA 扩增子分析 Agent 与 Web UI，同时提供 Linux x86_64 和 macOS 发行工作区，灵活支持命令行与浏览器两种部署方式。只需提供双端 FASTQ 文件和 metadata 表，即可一站式生成 OTU/ASV 表、物种注释、alpha/beta 多样性分析、论文级可视化图表、差异丰度分析结果、分析报告以及完整的可复现性记录。

> 💡 **推荐使用方式**：本地浏览器 Web UI。测序文件始终保留在您的电脑上，向导界面手把手引导每一步分析，底层调用与 CLI 完全一致的确定性 Python 工作流。LLM API key 为可选配置，没有也能顺畅使用。

## ✨ 项目亮点

- 🖥️ 专为湿实验用户打造的 Windows 本地 Web UI，开箱即用，无需折腾环境。
- 📦 一键 Windows 安装器，内置 Python 运行时、RDP 16S 小型数据库、USEARCH/VSEARCH 及预构建 Web UI，双击即跑。
- 🐧 Linux x86_64 发行包，含 setup 脚本、Web UI、CLI 启动器、内置小型 RDP 数据库及服务器测试流程。
- 🍎 macOS 预览包，同样提供 setup、Web UI 与 CLI 启动器，`bin/usearch` 会自动识别 Intel 或 Apple Silicon 架构并调用对应的 USEARCH 12。
- 🤖 Agent 页面：分析前自动检查数据与环境是否就绪，并提供分步骤操作引导。
- 🔁 `process.py` 确定性工作流，保障分析结果可复现、流程可自动化。
- 🚫🔑 无 LLM 模式下也可完成本地检查、可视化、报告生成及绝大部分辅助功能。
- ⚙️ 可在 Web UI 中随时配置 LLM：API key、API base URL 和模型切换，一切都在界面里完成。
- 📊 丰富的输出格式：Plotly 交互图表、HTML/Markdown 报告、`run_summary.json` 与 provenance 溯源文件，让每次分析都有迹可查。

<img width="1012" height="674" alt="938062bfa773ad3c8fb3c77fbd489a0" src="https://github.com/user-attachments/assets/6b658afc-96fb-4a2f-b07b-b74279233c53" />


## 🚀 快速开始：Windows 安装器

对于大多数用户，最省心的方式是直接从 GitHub Releases 下载 Windows 安装器：

```text
X-Amplicon-Setup-v0.1.0.exe
```

使用步骤非常简单：

1. 双击 `X-Amplicon-Setup-v0.1.0.exe` 启动安装向导。
2. 按提示完成安装，默认的当前用户安装目录为：

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

3. 从开始菜单或桌面快捷方式启动 **X-Amplicon Web UI**，分析之旅就此开始！

安装后，启动器会自动检查内置 Python 环境与小型 RDP 数据库，并打开本地 Web UI。默认访问地址为：

```text
http://127.0.0.1:8765
```

如果浏览器没有自动弹出，把启动窗口中显示的地址复制到浏览器即可轻松访问。

### 📦 安装器包含什么

| 内容 | 安装后路径 |
| --- | --- |
| 内置 Python 运行时 | `.tools\python-3.13.13-amd64\python.exe` |
| 小型 16S 数据库 | `database\rdp_16s_v18.fa` |
| USEARCH/VSEARCH 可执行文件 | `bin\windows\` |
| X-Amplicon 核心流程 | `process.py`、`src\`、`agent\` |
| Web UI 后端 | `webui\backend\` |
| 已构建 Web UI 前端 | `webui\frontend\dist\` |
| 一键启动脚本 | `Start_X-Amplicon_WebUI.cmd`、`Start_X-Amplicon_WebUI.ps1` |

安装器不包含用户 FASTQ 数据、分析输出、API key、运行时状态、`node_modules` 或大型 SILVA 数据库。

## 🛠️ 快速开始：源码仓库

如果您倾向于直接使用 GitHub 源码而非 Windows 安装器，请先安装依赖：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

国内用户若 PyPI 访问较慢，可切换清华镜像加速：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

启动 Web UI：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

常用启动选项（端口冲突或不想自动开浏览器时很有用）：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
```

## 🐧 快速开始：Linux x86_64 服务器

Linux 发行工作区适用于 Ubuntu 22.04 x86_64 或其他兼容的 x86_64 Linux 服务器：

```bash
cd /path/to/X-Amplicon_linux_x86_64
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
./setup_linux.sh --china-mirror
```

检查外部工具和 pipeline 配置：

```bash
./bin/usearch --version
./bin/vsearch --version
./run_process.sh check-pipeline-config --params pipeline_params.linux.yaml
```

运行完整 CLI 流程：

```bash
./run_process.sh run-pipeline-config --params pipeline_params.linux.yaml
./run_process.sh visualization-suite --final-dir work/06_final --format html
./run_process.sh generate-report --final-dir work/06_final
```

Linux Web UI 需要在终端里启动，不会自动弹出浏览器：

```bash
./start_webui.sh --no-browser
```

如果通过 SSH 远程访问服务器，可以在本地电脑执行端口转发，把远端 Web UI 映射到本地：

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

然后在本地浏览器打开 `http://127.0.0.1:8765`，体验和在本机操作无异。

如果想通过 SSH 浏览离线 HTML 报告，建议在服务器上启动仅监听本地的 HTTP 服务，再配合端口转发访问：

```bash
.venv/bin/python -m http.server 8899 --bind 127.0.0.1
ssh -N -L 8899:127.0.0.1:8899 user@server
```

然后在本地打开 `http://127.0.0.1:8899/work/06_final/report/analysis_report.html`，离线报告一览无余。

## 🍎 快速开始：macOS 预览版

macOS 发行工作区同时支持 Intel 和 Apple Silicon 两种架构：

```bash
cd /path/to/X-Amplicon_macos
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh \
  bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
./setup_macos.sh
```

`bin/usearch` 是一个自动识别架构的 wrapper：Apple Silicon 机型会调用
`usearch_osx_m_12.0-beta`，Intel macOS 则调用
`usearch_osx_x86_12.0-beta`。当前内置的 VSEARCH 为 x86_64 版本；
Apple Silicon 用户若遇到无法运行的情况，安装 Rosetta 2 即可解决。

检查 macOS pipeline 配置：

```bash
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
```

运行完整 CLI 流程：

```bash
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
./run_process.sh visualization-suite --final-dir work/06_final --format html
./run_process.sh generate-report --final-dir work/06_final
```

启动 macOS Web UI：

```bash
./start_webui.sh --no-browser
```

然后在浏览器打开 `http://127.0.0.1:8765`，完整说明请参阅
`X-Amplicon_macos/README_MACOS_zh.md`。

## 🖱️ Web UI 使用流程

推荐按以下顺序使用，循序渐进，不易出错：

1. **Settings**：确认 Python 路径、输出目录、metadata 路径、FASTQ 目录、USEARCH/VSEARCH 路径、图表格式以及可选的 LLM 配置。
2. **Agent**：通过分析向导检查数据、数据库和工具是否一切就绪，确保"万事俱备"再开始分析。
3. **New Analysis**：创建项目，选择 metadata 和双端 FASTQ 文件，校验样本匹配关系，确认分组，设置比较组并填写参数。
4. **Run Monitor**：运行 preflight 预检，启动完整 pipeline，实时查看日志，并可复制可复现命令以备后用。
5. **Results**：自由浏览图表、表格、差异丰度结果、分析报告、provenance 溯源信息和所有输出文件。
6. **Databases**：检查内置 RDP 数据库状态，或注册您自己的 FASTA 数据库。

Web UI 不会上传测序文件，所有数据、日志和结果始终保留在您的本机。

## 📂 输入文件
<img width="1593" height="654" alt="image" src="https://github.com/user-attachments/assets/4fa3e794-3960-4135-83a4-73913fd876a7" />

典型的项目目录结构如下：

```text
your_project\
  metadata.txt
  seq\
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
```

最小化 metadata 示例：

```text
SampleID	Group
S1	WT
S2	KO
```

格式要求：

- metadata 必须为制表符分隔的纯文本文件（TSV）。
- metadata 中的样本 ID 需要去掉 R1/R2 后缀后能与 FASTQ 文件名一一对应。
- 多样性分析和差异比较需要至少一个分组列，例如 `Group`。

## 📊 输出文件
<img width="1580" height="1187" alt="image" src="https://github.com/user-attachments/assets/301a9fa2-bf14-45f2-9822-c0799a727d20" />

默认输出根目录：

```text
work\
```

最终结果目录：

```text
work\06_final
```

主要输出：

| 输出 | 默认位置 |
| --- | --- |
| OTU/ASV 表 | `work\06_final\otutab.txt` |
| 物种注释 | `work\06_final\otus.sintax`、`work\06_final\taxonomy.tsv` |
| Alpha diversity | `work\06_final\alpha\alpha_diversity.tsv` |
| Beta diversity | `work\06_final\beta\` |
| 可视化浏览入口 | `work\06_final\plots\index.html` |
| 差异丰度分析 | `work\06_final\differential_abundance\` |
| 分析报告 | `work\06_final\report\analysis_report.html` |
| 可复现性记录 | `work\06_final\run_summary.json`、`provenance.json`、`provenance.md` |

CLI 的 `run-pipeline-config` 命令会先输出核心分析结果；`plots/` 和 `report/` 目录需要在 pipeline 完成后，继续执行 `visualization-suite` 和 `generate-report` 才会生成。图表会按类型分目录存放，整洁不杂乱。

## 🤖 可选 LLM Agent

完整分析流程不依赖 API key，即可正常运行。如果想体验 LLM 辅助引导，按以下步骤配置即可：

1. 打开 Web UI 的 **Settings** 页面。
2. 选择或手动输入 LiteLLM 兼容模型名称。
3. 如需走代理或自定义网关，填写 OpenAI-compatible API base URL。
4. 填写 API key，保存即可。
<img width="1589" height="1152" alt="image" src="https://github.com/user-attachments/assets/9a45a607-9a4d-44e8-843c-638e2009677f" />

API key 会安全保存在本地 `.env` 文件中，设置接口不会将其返回给浏览器，请放心使用。

等价 `.env` 字段：

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

## ⌨️ CLI 使用

大多数用户推荐使用 Web UI。CLI 则更适合脚本化运行与精确结果复现。
<img width="1271" height="1072" alt="image" src="https://github.com/user-attachments/assets/9be5b674-004f-419f-aa65-d6d0371fe2d5" />

标准流程：

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

常用 CLI：

| 任务 | 命令 |
| --- | --- |
| 检查配置 | `python process.py check-pipeline-config --params pipeline_params.yaml` |
| 运行完整 pipeline | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| 生成可视化 | `python process.py visualization-suite --final-dir work\06_final --format html` |
| 差异丰度分析 | `python process.py differential-abundance --reference-group WT --format html` |
| 生成报告 | `python process.py generate-report --final-dir work\06_final` |
| 检查数据库 | `python process.py check-database rdp_16s_v18` |
| 查看全部 CLI 命令 | `python process.py --help` |

CLI Agent：

```powershell
python agent_cli.py
python agent_cli.py --offline
```

常用 slash commands 包括 `/params`、`/status`、`/tools`、`/language`、`/report`、`/config` 和 `/quit`，输入 `/help` 可随时查看帮助。

## 📦 依赖

Windows 安装器已经内置普通使用所需的完整运行环境，无需额外操作。源码用户需要手动安装以下依赖：

| 类别 | 包或工具 |
| --- | --- |
| Python 核心包 | `numpy`、`pandas`、`scipy`、`scikit-bio`、`pyyaml`、`click`、`biopython`、`pydantic`、`plotly`、`rich`、`litellm` |
| Web UI 后端 | `fastapi`、`uvicorn[standard]`、`python-multipart`、`aiofiles` |
| 静态图导出 | `kaleido` |
| 可选 Agent skills | `llama-index`、`deepeval`、`ragas`、`langchain-openai`、`opentelemetry-api`、`opentelemetry-sdk` |
| 外部工具 | USEARCH 和 VSEARCH |

## 🔧 常见问题

**PowerShell 提示权限被阻止？** 加上 `-ExecutionPolicy Bypass` 参数运行即可：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

**默认端口已被占用？** 通过 `-Port` 参数指定其他端口：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

**安装后依赖检查失败，且电脑可以联网？** 在安装目录中打开 PowerShell，使用 `-RepairDeps` 参数自动修复：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

## 📄 License

见 [LICENSE](LICENSE)。

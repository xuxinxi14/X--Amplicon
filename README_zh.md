[English](README.md) | [中文](README_zh.md)

# X-Amplicon
作者：徐新玺

X-Amplicon 是一个以 Windows 本地环境为主的 16S rRNA 扩增子分析 Agent 和 Web UI，同时提供 Linux x86_64 服务器包，支持命令行和浏览器部署。它可以从双端 FASTQ 文件和 metadata 表出发，生成 OTU/ASV 表、物种注释、alpha/beta 多样性、论文级可视化、差异丰度图表、分析报告和可复现性记录。

推荐使用方式是本地浏览器 Web UI。Web UI 会把测序文件保留在用户电脑中，通过向导一步步引导分析，并调用与 CLI 相同的确定性 Python 工作流。LLM API key 是可选项。

## 项目亮点

- 面向湿实验用户的 Windows 本地 Web UI。
- 一键 Windows 安装器内置 Python、RDP 16S 小型数据库、USEARCH/VSEARCH 和已构建 Web UI。
- Linux x86_64 包提供 setup、Web UI、CLI 启动脚本、内置小型 RDP 数据库和服务器测试流程。
- Agent 页面提供分析前准备检查和分步引导。
- `process.py` 提供可复现、可自动化的确定性工作流。
- 无 LLM 模式下也可完成本地检查、可视化、报告生成和大部分帮助功能。
- 可在 Web UI 中配置 LLM：API key、API base URL 和模型切换。
- 输出包括 Plotly 图表、HTML/Markdown 报告、`run_summary.json` 和 provenance 文件。

<img width="1012" height="674" alt="938062bfa773ad3c8fb3c77fbd489a0" src="https://github.com/user-attachments/assets/6b658afc-96fb-4a2f-b07b-b74279233c53" />


## 快速开始：Windows 安装器

大多数用户推荐从 GitHub Releases 下载 Windows 安装器：

```text
X-Amplicon-Setup-v0.1.0.exe
```

使用步骤：

1. 双击 `X-Amplicon-Setup-v0.1.0.exe`。
2. 按安装向导完成安装。默认的当前用户安装目录是：

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

3. 从开始菜单或桌面快捷方式启动 **X-Amplicon Web UI**。

安装后的启动器会检查内置 Python 环境、确认小型 RDP 数据库可用，并打开本地 Web UI。默认地址是：

```text
http://127.0.0.1:8765
```

如果浏览器没有自动打开，把启动窗口中显示的地址复制到浏览器即可。

### 安装器包含什么

| 内容 | 安装后路径 |
| --- | --- |
| 内置 Python 运行时 | `.tools\python-3.13.13-amd64\python.exe` |
| 小型 16S 数据库 | `database\rdp_16s_v18.fa` |
| USEARCH/VSEARCH 可执行文件 | `bin\windows\` |
| X-Amplicon 核心流程 | `process.py`、`src\`、`agent\` |
| Web UI 后端 | `webui\backend\` |
| 已构建 Web UI 前端 | `webui\frontend\dist\` |
| 一键启动脚本 | `Start_X-Amplicon_WebUI.cmd`、`Start_X-Amplicon_WebUI.ps1` |

安装器不包含用户 FASTQ 数据、分析输出、API key、本地运行状态、`node_modules` 或大型 SILVA 数据库。

## 快速开始：源码仓库

如果使用 GitHub 源码而不是 Windows 安装器，先安装依赖：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallWebUIDeps
```

国内网络可使用清华镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallWebUIDeps
```

启动 Web UI：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

常用启动选项：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -Port 8770
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1 -NoBrowser
```

## 快速开始：Linux x86_64 服务器

Linux 发行工作区面向 Ubuntu 22.04 x86_64 或兼容的 x86_64 Linux 服务器：

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

Linux Web UI 需要在终端里启动

```bash
./start_webui.sh --no-browser
```

如果通过 SSH 访问服务器，在本地电脑执行端口转发：

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

然后打开 `http://127.0.0.1:8765`。

如果要通过 SSH 查看离线 HTML 报告，建议在服务器上启动本地 HTTP 服务：

```bash
.venv/bin/python -m http.server 8899 --bind 127.0.0.1
ssh -N -L 8899:127.0.0.1:8899 user@server
```

然后打开 `http://127.0.0.1:8899/work/06_final/report/analysis_report.html`。

## Web UI 使用流程

推荐按以下顺序使用：

1. **Settings**：确认 Python、输出目录、metadata 路径、FASTQ 目录、USEARCH/VSEARCH 路径、图表格式和可选 LLM 设置。
2. **Agent**：根据分析向导检查数据、数据库和工具是否准备好。
3. **New Analysis**：创建项目，选择 metadata 和双端 FASTQ，检查样本匹配，确认分组，设置比较组并写出参数。
4. **Run Monitor**：运行 preflight，启动完整 pipeline，查看日志并复制可复现命令。
5. **Results**：浏览图表、表格、差异丰度结果、报告、provenance 和输出文件。
6. **Databases**：检查内置 RDP 数据库，或注册自己的 FASTA 数据库。

Web UI 不上传测序文件。数据、日志和结果都保留在本机。

## 输入文件

典型项目目录：

```text
your_project\
  metadata.txt
  seq\
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
```

最小 metadata 示例：

```text
SampleID	Group
S1	WT
S2	KO
```

要求：

- metadata 应为制表符分隔文本。
- metadata 中的样本 ID 需要能在去掉 R1/R2 后缀后与 FASTQ 文件名匹配。
- 多样性图和差异比较需要一个分组列，例如 `Group`。

## 输出文件

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

CLI 的 `run-pipeline-config` 会先生成核心分析结果。`plots/` 和 `report/`
需要在 pipeline 完成后继续运行 `visualization-suite` 和 `generate-report`。
图表会按类型放入不同子目录，而不是全部混放在一个文件夹。

## 可选 LLM Agent

完整分析流程不需要 API key。如需启用 LLM 辅助：

1. 打开 Web UI 的 **Settings**。
2. 选择或输入 LiteLLM 兼容模型。
3. 如需代理或自定义网关，填写 OpenAI-compatible API base URL。
4. 填写 API key。

API key 会保存在本地 `.env` 中，设置接口不会把 key 返回给浏览器。

等价 `.env` 字段：

```text
DEFAULT_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_API_BASE=https://your-openai-compatible-endpoint/v1
```

## CLI 使用

大多数用户推荐使用 Web UI。CLI 适合脚本化运行和精确复现。

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

常用 slash commands 包括 `/params`、`/status`、`/tools`、`/language`、`/report`、`/config` 和 `/quit`。

## Linux 打包方式

Linux 没有完全等同于 Windows `.exe` 安装器的统一格式。常见选择如下：

| 方式 | 适用场景 | 说明 |
| --- | --- | --- |
| 便携 `tar.gz` 包 | 推荐用于服务器和集群 | 分发整个项目目录，在目标机器运行 `setup_linux.sh`，再用 shell 启动脚本运行。 |
| AppImage | 最接近桌面双击体验 | 可以生成单个 Linux 应用文件，但需要额外打包工作，并按发行版测试。 |
| PyInstaller/Nuitka 可执行文件 | CLI 或启动器二进制 | 可以生成 Linux ELF 可执行文件，但 Web UI 静态资源、数据库、USEARCH/VSEARCH 仍需一起打包或放在旁边。 |
| `.deb` 包 | Ubuntu 内部部署 | 适合由 IT 统一安装，但需要维护 Debian 包元数据和安装脚本。 |

对当前项目，最稳妥的 Linux “类 exe”发布方式是便携目录压缩包：

```bash
cd ..
tar --exclude='X-Amplicon_linux_x86_64/.venv' \
    --exclude='X-Amplicon_linux_x86_64/work' \
    --exclude='X-Amplicon_linux_x86_64/seq' \
    --exclude='X-Amplicon_linux_x86_64/.env' \
    -czf X-Amplicon_linux_x86_64.tar.gz X-Amplicon_linux_x86_64
```

用户解压后运行 `./setup_linux.sh`，再用 `./start_webui.sh --no-browser` 或 `./run_process.sh ...`。如果后续要做 PyInstaller/AppImage，请在与目标服务器兼容的 Linux 系统上构建，并先确认 USEARCH 等外部工具的再分发许可。

## 依赖

Windows 安装器已经包含普通使用所需运行环境。源码用户需要：

| 类别 | 包或工具 |
| --- | --- |
| Python 核心包 | `numpy`、`pandas`、`scipy`、`scikit-bio`、`pyyaml`、`click`、`biopython`、`pydantic`、`plotly`、`rich`、`litellm` |
| Web UI 后端 | `fastapi`、`uvicorn[standard]`、`python-multipart`、`aiofiles` |
| 静态图导出 | `kaleido` |
| 可选 Agent skills | `llama-index`、`deepeval`、`ragas`、`langchain-openai`、`opentelemetry-api`、`opentelemetry-sdk` |
| 外部工具 | USEARCH 和 VSEARCH |

## 常见问题

如果 PowerShell 阻止脚本运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

如果默认端口被占用：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

如果安装后的依赖检查失败，且电脑可以联网，请在安装目录中打开 PowerShell 并运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

## License

见 [LICENSE](LICENSE)。

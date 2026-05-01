# X-Amplicon Windows 发行包说明

`X-Amplicon_main` 是用于 GitHub Releases 的 Windows 本地运行包。用户下载压缩包后，解压并启动脚本即可打开 Web UI。

## 已内置内容

- Python 运行时：`.tools\python-3.13.13-amd64\python.exe`
- X-Amplicon 核心程序：`process.py`、`agent_cli.py`、`src\`、`agent\`
- Web UI 后端和启动器：`webui\backend\`、`webui\launcher\`
- 已构建前端：`webui\frontend\dist\`
- 小型 RDP 16S 数据库：`database\rdp_16s_v18.fa`
- Windows USEARCH/VSEARCH：`bin\windows\`
- 一键启动脚本：`Start_X-Amplicon_WebUI.cmd`、`Start_X-Amplicon_WebUI.ps1`

以下内容不会放入发行包：

- `seq\` 原始测序数据
- `work\` 分析输出
- `.xamplicon_webui\` 本地运行状态
- `.env` 本地 API key 配置
- `webui\frontend\node_modules\`
- 大型 SILVA 数据库

## 启动方式

普通 Windows 用户推荐双击：

```text
Start_X-Amplicon_WebUI.cmd
```

也可以在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1
```

默认浏览器地址通常是：

```text
http://127.0.0.1:8765
```

如果端口被占用：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -Port 8770
```

## 首次使用流程

1. 打开 Web UI 的 **Settings**。
2. 确认 Python、输出目录、metadata 路径、FASTQ 目录、USEARCH/VSEARCH 路径和图表格式。
3. 如需 LLM Agent，在 Settings 中配置模型、API base URL 和 API key。
4. 打开 **Agent**，按引导确认数据、数据库和工具是否准备好。
5. 在 **New Analysis** 中选择 metadata 和双端 FASTQ。
6. 在 **Run Monitor** 中运行 preflight，再启动完整分析。
7. 在 **Results** 中查看图表、表格、报告、provenance 和输出文件。

## 放入自己的数据

可以把自己的 metadata 和测序文件放在发行包目录中，例如：

```text
X-Amplicon_main\
  metadata.txt
  seq\
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
```

metadata 至少应包含样本 ID 和分组列：

```text
SampleID	Group
S1	WT
S2	KO
```

## 依赖修复

发行包默认应已包含可用 Python 环境。如果依赖检查失败，并且电脑可以联网，可运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps
```

国内网络可加清华镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\Start_X-Amplicon_WebUI.ps1 -RepairDeps -UseChinaMirror
```

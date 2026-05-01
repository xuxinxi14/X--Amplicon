# X-Amplicon macOS 预览版

这个目录是面向 macOS 的 X-Amplicon 发行工作区。其中包含 X-Amplicon
Python/Web UI 程序、小型 RDP 16S 参考数据库，以及已经验证过的 macOS 版
USEARCH/VSEARCH 可执行文件。

## 目录结构

```text
X-Amplicon_mac/
  bin/
    usearch
    vsearch
  database/
    rdp_16s_v18.fa
  src/
  webui/
  process.py
  agent_cli.py
  setup_macos.sh
  start_webui.sh
  run_process.sh
  run_agent.sh
  pipeline_params.macos.yaml
```

默认不包含用户 FASTQ 文件、metadata、分析输出、API key 或大型 SILVA 数据库。

## 系统要求

- Intel 或 Apple Silicon macOS。
- Python 3.10 或更高版本。
- 可选：如果需要重新构建 Web UI 前端，需要 Node.js 20+。

推荐使用 Homebrew 安装 Python：

```bash
brew install python
```

也可以从 Python 官网下载安装：

```text
https://www.python.org/downloads/macos/
```

Apple Silicon 机器如果运行的是 Intel-only 二进制文件，需要安装 Rosetta 2：

```bash
softwareupdate --install-rosetta --agree-to-license
```

## 初始化

进入本目录后运行：

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh bin/usearch bin/vsearch
./setup_macos.sh
```

如果 PyPI 访问较慢：

```bash
./setup_macos.sh --china-mirror
```

如果需要安装 RAG、tracing 和 evaluation 相关可选依赖：

```bash
./setup_macos.sh --with-skills
```

初始化脚本会创建 `.venv/`，设置 `bin/usearch` 和 `bin/vsearch` 的可执行权限，
尽可能移除 macOS quarantine 属性，写入 macOS 版 Web UI 默认设置，并生成诊断文件：

```text
run_logs/macos_setup_diagnostics.json
```

## 启动 Web UI

本地启动：

```bash
./start_webui.sh
```

默认地址：

```text
http://127.0.0.1:8765
```

如果 macOS 因文件来自互联网而阻止运行二进制文件，可执行：

```bash
xattr -dr com.apple.quarantine bin/usearch bin/vsearch
chmod +x bin/usearch bin/vsearch
```

## CLI 测试

把测试数据放成下面的结构：

```text
X-Amplicon_mac/
  metadata.txt
  seq/
    KO1_1.fq.gz
    KO1_2.fq.gz
    ...
```

检查配置：

```bash
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
```

运行完整流程：

```bash
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
```

预期最终输出目录：

```text
work/06_final/
  run_summary.json
  provenance.json
  report/
  plots/
```

## Agent CLI

无 LLM 模式：

```bash
./run_agent.sh --offline
```

如果要启用 LLM，需要在 `.env` 或 Web UI 设置中配置 API key、API base URL 和模型。

## 说明

- 启动脚本会把 `bin/usearch` 和 `bin/vsearch` 加入本次运行的 `PATH`。
- `pipeline_params.macos.yaml` 已经使用 macOS 路径：`bin/usearch` 和 `bin/vsearch`。
- 如果 `webui/frontend/dist/index.html` 存在，会直接使用内置前端构建产物。
- 如果前端构建产物缺失，请安装 Node.js 20+ 后运行：

```bash
./start_webui.sh --build-frontend
```

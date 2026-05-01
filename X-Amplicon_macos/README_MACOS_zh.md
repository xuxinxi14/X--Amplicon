# X-Amplicon macOS 预览版

这个目录是面向 macOS 的 X-Amplicon 发行工作区。其中包含 X-Amplicon
Python/Web UI 程序、小型 RDP 16S 参考数据库、已经验证过的 Intel 和
Apple Silicon 版 USEARCH 12，以及内置 VSEARCH。

## 目录结构

```text
X-Amplicon_macos/
  bin/
    usearch
    usearch_osx_m_12.0-beta
    usearch_osx_x86_12.0-beta
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

默认不包含用户 FASTQ 文件、metadata、分析输出、API key 或大型 SILVA 数据库；
这些本地运行文件会继续被 git 忽略。

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

Apple Silicon 机器会通过 `bin/usearch` 使用内置 arm64 USEARCH。当前内置
VSEARCH 是 x86_64 版本；如果 macOS 无法运行，需要安装 Rosetta 2：

```bash
softwareupdate --install-rosetta --agree-to-license
```

## 初始化

进入本目录后运行：

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh \
  bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
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

初始化脚本会创建 `.venv/`，设置 `bin/usearch`、两个 USEARCH 12 二进制和
`bin/vsearch` 的可执行权限，尽可能移除 macOS quarantine 属性，写入 macOS 版
Web UI 默认设置，并生成诊断文件：

```text
run_logs/macos_setup_diagnostics.json
```

如果只想检查发行文件和工具，不安装 Python 包：

```bash
./setup_macos.sh --diagnostics-only
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

常用启动选项：

```bash
./start_webui.sh --no-browser
./start_webui.sh --port 8770
./start_webui.sh --repair-deps
./start_webui.sh --build-frontend
```

如果 macOS 因文件来自互联网而阻止运行二进制文件，可执行：

```bash
xattr -dr com.apple.quarantine \
  bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
chmod +x bin/usearch bin/usearch_osx_m_12.0-beta bin/usearch_osx_x86_12.0-beta bin/vsearch
```

## CLI 测试

把测试数据放成下面的结构：

```text
X-Amplicon_macos/
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
- `bin/usearch` 是自动选择架构的 wrapper。Apple Silicon 使用
  `bin/usearch_osx_m_12.0-beta`，Intel macOS 使用
  `bin/usearch_osx_x86_12.0-beta`。`pipeline_params.macos.yaml` 应继续指向
  `bin/usearch`。
- USEARCH 12 和旧版部分命令不完全兼容。`otutab-filter` 中代表序列 FASTA
  提取、`otutab-rare` 中 OTU table stats 现在由 Python 内部生成，以兼容
  USEARCH 12。
- USEARCH 12 可能只有在不带 `--version` 参数时才打印版本；推荐用
  `./setup_macos.sh --diagnostics-only` 检查工具状态。
- `pipeline_params.macos.yaml` 已经使用 macOS 路径：`bin/usearch` 和 `bin/vsearch`。
- 如果 `webui/frontend/dist/index.html` 存在，会直接使用内置前端构建产物。
- 如果前端构建产物缺失，`start_webui.sh` 会自动构建，除非使用 `--no-build`。
  也可以安装 Node.js 20+ 后手动运行：

```bash
./start_webui.sh --build-frontend
```

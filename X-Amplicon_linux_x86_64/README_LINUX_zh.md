# X-Amplicon Linux x86_64 预览版

这个目录是面向 Ubuntu 22.04 x86_64 的 X-Amplicon Linux 发行工作区。
其中包含 X-Amplicon Python/Web UI 程序和小型 RDP 16S 参考数据库。
请在运行初始化前，把可再发行的 Linux 版 USEARCH/VSEARCH 放到
`bin/usearch` 和 `bin/vsearch`。

该包已在 x86_64 Linux 服务器上完成真实测试：Python 3.12、USEARCH
`v10.0.240_i86linux32`、VSEARCH `v2.15.2_linux_x86_64` 可运行；CLI
pipeline、可视化生成、报告生成和 Web UI 启动均已通过。

## 目录结构

```text
X-Amplicon_linux_x86_64/
  bin/
    usearch
    vsearch
  database/
    rdp_16s_v18.fa
  src/
  webui/
  process.py
  agent_cli.py
  setup_linux.sh
  start_webui.sh
  run_process.sh
  run_agent.sh
  pipeline_params.linux.yaml
```

默认不包含用户 FASTQ 文件、metadata、分析输出、API key 或大型 SILVA 数据库。

## 系统要求

- Ubuntu 22.04 x86_64。
- Python 3.10 或更高版本。
- `python3-venv` 和 `python3-pip`。
- 可选：如果需要重新构建 Web UI 前端，需要 Node.js 20+。

干净的 Ubuntu 服务器可先运行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## 初始化

进入本目录后运行：

```bash
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
./setup_linux.sh
```

如果 PyPI 访问较慢：

```bash
./setup_linux.sh --china-mirror
```

如果需要安装 RAG、tracing 和 evaluation 相关可选依赖：

```bash
./setup_linux.sh --with-skills
```

初始化脚本会创建 `.venv/`，设置 `bin/usearch` 和 `bin/vsearch` 的可执行权限，
写入 Linux 版 Web UI 默认设置，并生成诊断文件：

```text
run_logs/linux_setup_diagnostics.json
```

## 启动 Web UI

本地启动：

```bash
./start_webui.sh --no-browser
```

默认地址：

```text
http://127.0.0.1:8765
```

如果在远程服务器上运行，更推荐通过 SSH 端口转发访问。先在服务器端启动：

```bash
./start_webui.sh --no-browser
```

然后在本地电脑执行：

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

然后在本地浏览器打开：

```text
http://127.0.0.1:8765
```

如果部署环境必须让其他机器直接访问，也可以显式绑定到所有网卡：

```bash
./start_webui.sh --host 0.0.0.0 --no-browser
```

在 JupyterLab 中，不要在文件列表里点击 `start_webui.sh`，那通常只会打开编辑器。
请打开 Terminal 后执行命令。如果看到 `Permission denied`，先恢复执行权限：

```bash
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
bash start_webui.sh --no-browser
```

## 远程查看 HTML 结果

`analysis_report.html` 通过相对路径嵌入图表，例如 `../plots/...`。远程查看时，
需要保留整个 `work/06_final` 目录结构。最稳妥的方法是在服务器上启动只监听
本机的 HTTP 服务：

服务器端：

```bash
.venv/bin/python -m http.server 8899 --bind 127.0.0.1
```

本地电脑：

```bash
ssh -N -L 8899:127.0.0.1:8899 user@server
```

然后打开：

```text
http://127.0.0.1:8899/work/06_final/report/analysis_report.html
http://127.0.0.1:8899/work/06_final/plots/index.html
```

## CLI 测试

把测试数据放成下面的结构：

```text
X-Amplicon_linux_x86_64/
  metadata.txt
  seq/
    KO1_1.fq.gz
    KO1_2.fq.gz
    ...
```

检查配置：

```bash
./run_process.sh check-pipeline-config --params pipeline_params.linux.yaml
```

运行完整流程：

```bash
./run_process.sh run-pipeline-config --params pipeline_params.linux.yaml
```

pipeline 命令会生成核心分析结果：

```text
work/06_final/
  run_summary.json
  provenance.json
  provenance.md
  otutab.txt
  otutab_rare.txt
  otus.fa
  otus.sintax
  taxonomy.tsv
  alpha/
  beta/
  taxonomy_summary/
```

pipeline 完成后继续生成图表和报告：

```bash
./run_process.sh visualization-suite --final-dir work/06_final --format html
./run_process.sh generate-report --final-dir work/06_final
```

预期新增输出目录：

```text
work/06_final/
  report/
  plots/
```

重要输出文件：

```text
work/06_final/run_summary.json
work/06_final/provenance.json
work/06_final/report/analysis_report.html
work/06_final/plots/index.html
```

## Agent CLI

无 LLM 模式：

```bash
./run_agent.sh --offline
```

如果要启用 LLM，需要在 `.env` 或 Web UI 设置中配置 API key、API base URL 和模型。

## Linux 打包

Linux 没有统一等同于 Windows `.exe` 的安装器格式，应根据用户运行场景选择：

| 打包形式 | 推荐场景 | 说明 |
| --- | --- | --- |
| 便携 `tar.gz` 目录 | 服务器、SSH、集群、JupyterHub | 对当前项目最稳妥。用户解压后运行 `setup_linux.sh`，再用 shell 启动脚本。 |
| AppImage | 桌面双击应用 | 最接近单文件 Linux 应用，但需要 AppImage 工具链，并按发行版测试。 |
| PyInstaller/Nuitka ELF | CLI 二进制或 Web UI 启动器 | 可以把 Python 代码打成 Linux 可执行文件，但数据库、前端 `dist/` 和外部工具仍需一起打包或放在旁边。 |
| `.deb` 包 | Ubuntu 统一部署 | 适合机构 IT 安装，但需要维护 Debian 包元数据和安装脚本。 |

推荐的便携发布包命令：

```bash
cd ..
tar --exclude='X-Amplicon_linux_x86_64/.venv' \
    --exclude='X-Amplicon_linux_x86_64/work' \
    --exclude='X-Amplicon_linux_x86_64/seq' \
    --exclude='X-Amplicon_linux_x86_64/.env' \
    --exclude='X-Amplicon_linux_x86_64/.xamplicon_webui' \
    -czf X-Amplicon_linux_x86_64.tar.gz X-Amplicon_linux_x86_64
```

如果希望更接近 `.exe`，可以写一个很小的 Python 启动器来启动
`uvicorn webui.backend.app:app`，再用 PyInstaller 的 `--onedir` 模式构建，
并把 `webui/frontend/dist`、`database`、`bin`、`src`、`agent` 和启动脚本作为数据文件加入。
构建环境应与目标服务器属于同一类 Linux 发行版，并且打包 USEARCH 等外部工具前需要确认再分发许可。

## 说明

- 启动脚本会把 `bin/usearch` 和 `bin/vsearch` 加入本次运行的 `PATH`。
- `pipeline_params.linux.yaml` 已经使用 Linux 路径：`bin/usearch` 和 `bin/vsearch`。
- `check-pipeline-config` 会检查路径和可执行文件是否存在；真实二进制运行检查请执行
  `./bin/usearch --version` 和 `./bin/vsearch --version`。
- Linux 包中的 USEARCH 可能显示为 `i86linux32`，在兼容的 x86_64 Linux 上仍可运行，
  但应在目标服务器上实际测试。
- 如果 `webui/frontend/dist/index.html` 存在，会直接使用内置前端构建产物。
- 如果前端构建产物缺失，请安装 Node.js 20+ 后运行：

```bash
./start_webui.sh --build-frontend
```

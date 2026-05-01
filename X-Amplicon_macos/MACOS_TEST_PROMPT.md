# macOS 测试提示词

在 macOS 中打开本文件后，把下面代码块里的内容复制给 Codex，即可继续进行
X-Amplicon macOS 版真实运行测试。

```text
我现在在 macOS 环境中测试 X-Amplicon macOS 发行目录。请你作为代码与运行测试助手，帮我完成真实 macOS 兼容性测试。

项目目录是：

<请填写绝对路径，例如 /Users/me/X-Amplicon_macos>

当前目录结构应该包含：

bin/usearch
bin/vsearch
database/rdp_16s_v18.fa
setup_macos.sh
start_webui.sh
run_process.sh
run_agent.sh
pipeline_params.macos.yaml
process.py
webui/
src/

测试数据已经放在项目目录下，结构为：

metadata.txt
seq/
  KO1_1.fq.gz
  KO1_2.fq.gz
  KO2_1.fq.gz
  KO2_2.fq.gz
  ...

请按下面顺序测试，并在每一步明确告诉我结果、失败原因和需要修改的最小文件范围。

1. 环境与文件检查
   - 确认当前系统是 macOS。
   - 检查 CPU 架构：Intel x86_64 还是 Apple Silicon arm64。
   - 检查 Python 版本是否为 3.10 或更高。
   - 确认 bin/usearch、bin/vsearch、database/rdp_16s_v18.fa、webui/frontend/dist/index.html 是否存在。
   - 检查脚本是否为 LF 换行，是否有执行权限。

2. macOS 二进制可执行性检查
   - 对 setup_macos.sh、start_webui.sh、run_process.sh、run_agent.sh、bin/usearch、bin/vsearch 执行 chmod +x。
   - 如果 macOS quarantine 或 Gatekeeper 阻止运行，使用 xattr -dr com.apple.quarantine 修复。
   - 运行 bin/usearch --version 和 bin/vsearch --version。
   - 如果 Apple Silicon 上出现 Bad CPU type in executable，请判断是否需要 Rosetta 2，并给出命令。

3. 初始化测试
   - 运行 ./setup_macos.sh。
   - 如果网络或 PyPI 下载较慢，可改用 ./setup_macos.sh --china-mirror。
   - 检查 .venv 是否创建成功。
   - 检查 run_logs/macos_setup_diagnostics.json。
   - 确认 .xamplicon_webui/settings.json 中 usearch_path 和 vsearch_path 是 bin/usearch 与 bin/vsearch。

4. CLI 预检查
   - 运行：
     ./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
   - 如果失败，请定位是路径、数据库、metadata、FASTQ 配对、Python 依赖还是二进制工具问题。

5. 完整流程测试
   - 运行：
     ./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
   - 观察是否完整生成：
     work/06_final/run_summary.json
     work/06_final/provenance.json
     work/06_final/report/
     work/06_final/plots/
   - 检查是否包含可视化图表、报告、alpha/beta 多样性结果、物种注释结果。

6. Web UI 启动测试
   - 运行：
     ./start_webui.sh
   - 确认 Web UI 是否能在浏览器打开：
     http://127.0.0.1:8765
   - 如果端口 8765 被占用，改用：
     ./start_webui.sh --port 8770
   - 检查 Web UI 设置页中的 Python、USEARCH、VSEARCH 路径是否为 macOS 路径。
   - 检查新建分析、运行监控、结果查看、报告图表显示是否正常。

7. Agent CLI 测试
   - 运行：
     ./run_agent.sh --offline
   - 检查无 LLM 模式是否能正常进入。
   - 如果我提供了 API key，再测试 LLM 对话与 16S 分析引导功能。

8. 输出测试总结
   请最后按下面格式总结：
   - 测试环境：macOS 版本、CPU 架构、Python 版本。
   - 通过的项目。
   - 失败的项目。
   - 每个失败项的原因。
   - 建议修改的文件。
   - 是否可以打包为 macOS release。

测试过程中不要删除我的原始数据，不要清空 work 目录，除非我明确要求。不要推送 GitHub。若必须修改代码，请先说明原因，然后只做最小必要修改。
```

## 可手动执行的参考命令

```bash
cd /path/to/X-Amplicon_macos
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh bin/usearch bin/vsearch
xattr -dr com.apple.quarantine . 2>/dev/null || true
./bin/usearch --version
./bin/vsearch --version
./setup_macos.sh
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
./start_webui.sh
```

Apple Silicon 如果遇到 Intel 二进制无法运行，可先安装 Rosetta 2：

```bash
softwareupdate --install-rosetta --agree-to-license
```

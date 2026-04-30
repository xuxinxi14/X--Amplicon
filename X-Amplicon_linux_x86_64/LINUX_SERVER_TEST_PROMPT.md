# Linux Server Test Prompt

把 `X-Amplicon_linux_x86_64` 上传到 Ubuntu 22.04 x86_64 服务器并放入测试数据后，
可以把下面这段提示词发给 Codex 继续测试。

```text
我已经把 X-Amplicon_linux_x86_64 上传到 Ubuntu 22.04 x86_64 服务器，目录路径是：

<填写服务器上的绝对路径，例如 /home/user/X-Amplicon_linux_x86_64>

测试数据已经放在该目录下：

metadata.txt
seq/
  KO1_1.fq.gz
  KO1_2.fq.gz
  ...

请帮我在 Linux 服务器上完成 X-Amplicon 的真实运行测试，重点检查：

1. setup_linux.sh 是否能创建 .venv 并安装依赖。
2. bin/usearch 和 bin/vsearch 是否能正常运行并输出版本信息。
3. pipeline_params.linux.yaml 是否能通过 check-pipeline-config。
4. run-pipeline-config 是否能完整跑通 16S 流程。
5. work/06_final 是否包含 run_summary.json、provenance.json、report 和 plots。
6. start_webui.sh --no-browser 是否能启动 Web UI。
7. 如果服务器通过 SSH 端口转发访问 Web UI，请给出本地访问命令。

测试时请尽量不要改动源代码；如果发现 Linux 兼容性问题，先定位原因并给出需要修改的文件和最小改动方案。
```

## Suggested Commands

```bash
cd /path/to/X-Amplicon_linux_x86_64
chmod +x setup_linux.sh start_webui.sh run_process.sh run_agent.sh
./setup_linux.sh --china-mirror
./bin/usearch --version
./bin/vsearch --version
./run_process.sh check-pipeline-config --params pipeline_params.linux.yaml
./run_process.sh run-pipeline-config --params pipeline_params.linux.yaml
./start_webui.sh --no-browser
```

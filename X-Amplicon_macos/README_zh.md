# X-Amplicon macOS 版

这是 X-Amplicon 的 macOS 发行工作区。优先从这里开始：

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh bin/usearch bin/vsearch
./setup_macos.sh
./start_webui.sh
```

默认 Web UI 地址：

```text
http://127.0.0.1:8765
```

完整说明见：

- `README_MACOS.md`
- `README_MACOS_zh.md`

命令行测试：

```bash
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
```

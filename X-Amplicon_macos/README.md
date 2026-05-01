# X-Amplicon for macOS

This is the macOS release workspace for X-Amplicon. Start here:

```bash
chmod +x setup_macos.sh start_webui.sh run_process.sh run_agent.sh bin/usearch bin/vsearch
./setup_macos.sh
./start_webui.sh
```

Default Web UI address:

```text
http://127.0.0.1:8765
```

For full instructions, see:

- `README_MACOS.md`
- `README_MACOS_zh.md`

For command-line testing:

```bash
./run_process.sh check-pipeline-config --params pipeline_params.macos.yaml
./run_process.sh run-pipeline-config --params pipeline_params.macos.yaml
```

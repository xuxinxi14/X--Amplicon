# X-Amplicon Web UI Launcher

For the macOS release workspace, use the shell launcher at the project root:

```bash
./start_webui.sh
```

Common macOS options:

```bash
./start_webui.sh --no-browser
./start_webui.sh --port 8770
./start_webui.sh --repair-deps
./start_webui.sh --build-frontend
```

The PowerShell launcher in this directory is retained for source-tree
compatibility with the Windows package and is not used by `setup_macos.sh`.

## Windows Launcher Reference

This directory also contains Windows launcher scripts for the local browser
interface.

Recommended root command:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_webui.ps1
```

Direct launcher command:

```powershell
powershell -ExecutionPolicy Bypass -File .\webui\launcher\start_webui.ps1
```

Production mode starts one FastAPI service and serves `webui\frontend\dist` when the frontend has been built. Development mode starts FastAPI plus Vite:

```powershell
powershell -ExecutionPolicy Bypass -File .\webui\launcher\start_webui.ps1 -Dev
```

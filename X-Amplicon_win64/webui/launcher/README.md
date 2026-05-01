# X-Amplicon Web UI Launcher

This directory contains Windows launcher scripts for the local browser interface.

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

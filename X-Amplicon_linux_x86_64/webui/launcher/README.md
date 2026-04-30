# X-Amplicon Web UI Launcher

This directory contains launcher scripts for the local browser interface. The
Windows PowerShell launcher lives here; the Linux release uses the root-level
`start_webui.sh` wrapper.

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

Linux root command:

```bash
cd /path/to/X-Amplicon_linux_x86_64
chmod +x start_webui.sh
./start_webui.sh --no-browser
```

On SSH servers, forward the backend port from your local machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@server
```

Then open `http://127.0.0.1:8765`.

In JupyterLab, clicking `start_webui.sh` opens the editor instead of executing
the script. Open a Terminal and run the Linux command there.

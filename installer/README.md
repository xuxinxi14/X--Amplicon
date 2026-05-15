# X-Amplicon Inno Setup Installer

This folder contains the Inno Setup script for packaging the Windows release zip as a Windows installer. The installer stores the already-built zip payload and expands it during installation. This avoids path-length issues caused by sending the bundled Python environment to Inno Setup file by file.

## Build

Install Inno Setup 6, then run from the repository root:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\installer\X-Amplicon.iss
```

The installer is written to:

```text
dist\installer\X-Amplicon-Setup-v0.1.2.exe
```

The installer uses a per-user writable install path:

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

The destination page is shown during setup, so users can choose another writable directory. The default path avoids write-permission problems for `.env`, `.xamplicon_webui`, `work`, and other local runtime files.

## Payload

Create or refresh the payload before compiling:

```powershell
.\.tools\python-3.13.13-amd64\python.exe .\installer\build_payload_zip.py
```

The setup script expects the generated payload:

```text
X-Amplicon_win64.zip
```

Do not use plain `Compress-Archive` unless you manually exclude local backup
folders such as `.tools.local_backup`.

During installation, `install_payload.ps1` uses Windows `tar.exe` when
available and falls back to `Expand-Archive` only when needed. This avoids the
very slow PowerShell extraction path for large Python runtimes with many small
files.

The setup icon and installed shortcuts use:

```text
installer\X-Amplicon.ico
```

Installed user-facing shortcuts point to `Start_X-Amplicon_WebUI.vbs`, which
starts the Web UI without showing a terminal window and displays a small startup
window until the backend is ready. The visible `Start_X-Amplicon_WebUI.cmd`
launcher remains in the install directory for troubleshooting startup problems.

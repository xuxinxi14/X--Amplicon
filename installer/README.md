# X-Amplicon Inno Setup Installer

This folder contains the Inno Setup script for packaging `X-Amplicon_main.zip` as a Windows installer. The installer stores the already-built zip payload and expands it during installation. This avoids path-length issues caused by sending the bundled Python environment to Inno Setup file by file.

## Build

Install Inno Setup 6, then run from the repository root:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\installer\X-Amplicon.iss
```

The installer is written to:

```text
dist\installer\X-Amplicon-Setup-v0.1.0.exe
```

The installer uses a per-user writable install path:

```text
%LOCALAPPDATA%\Programs\X-Amplicon
```

This avoids write-permission problems for `.env`, `.xamplicon_webui`, `work`, and other local runtime files.

## Payload

Create or refresh the payload before compiling:

```powershell
Compress-Archive -Path .\X-Amplicon_main -DestinationPath .\X-Amplicon_main.zip -Force
```

The setup script expects:

```text
X-Amplicon_main.zip
```

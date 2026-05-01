@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start_X-Amplicon_WebUI.ps1"
if errorlevel 1 (
  echo.
  echo X-Amplicon Web UI exited with an error.
  pause
)

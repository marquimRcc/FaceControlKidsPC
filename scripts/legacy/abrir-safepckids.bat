@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m safepckids.admin_dashboard
) else (
    py -3.11 -m safepckids.admin_dashboard
)

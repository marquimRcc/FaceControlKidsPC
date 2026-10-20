@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m facekids.gui
) else (
    py -3.11 -m facekids.gui
)

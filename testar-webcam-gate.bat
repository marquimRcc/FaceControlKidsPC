@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m facekids.gate_webcam_preview
) else (
    py -3.11 -m facekids.gate_webcam_preview
)
if errorlevel 1 (
    echo.
    echo Leia docs\DEMO-FACE-GATE.md
    pause
)

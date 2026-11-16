@echo off
setlocal
title SafePCKids - Servidor de Controle Remoto
cd /d "%~dp0.."
echo ============================================================
echo   SafePCKids // Servidor de Controle Remoto (Focus Boss)
echo ============================================================
echo.
if exist "%ProgramFiles%\SafePCKids\.venv\Scripts\python.exe" (
    "%ProgramFiles%\SafePCKids\.venv\Scripts\python.exe" -m safepckids.app_server --port 8765
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m safepckids.app_server --port 8765
    exit /b 0
)
python.exe -m safepckids.app_server --port 8765
pause

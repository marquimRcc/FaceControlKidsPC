@echo off
setlocal
title SafePCKids - Painel Administrativo

:: Guarda contra re-execucao em loop caso ja tenha sido elevado
if /i "%~1"=="--elevated" goto :launch

:: Auto-elevacao administrativa (UAC) em tentativa unica para controle de servicos, DNS e Firewall
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -Verb RunAs"
    exit /b 0
)

:launch
cd /d "%~dp0.."
if exist "runtime\pythonw.exe" (
    start "" "runtime\pythonw.exe" -m safepckids.launcher --dashboard
    exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m safepckids.launcher --dashboard
    exit /b 0
)
if exist "%ProgramFiles%\SafePCKids\.venv\Scripts\pythonw.exe" (
    cd /d "%ProgramFiles%\SafePCKids"
    start "" "%ProgramFiles%\SafePCKids\.venv\Scripts\pythonw.exe" -m safepckids.launcher --dashboard
    exit /b 0
)
start "" pythonw.exe -m safepckids.launcher --dashboard
exit /b 0

@echo off
setlocal
title SafePCKids - Painel Administrativo

:: Auto-elevacao administrativa (UAC) para garantir controle de servicos, DNS e Firewall
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0.."
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m safepckids.launcher --admin
) else (
    start "" pythonw -m safepckids.launcher --admin
)

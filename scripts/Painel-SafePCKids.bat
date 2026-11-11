@echo off
setlocal
title SafePCKids - Painel Administrativo

cd /d "%~dp0.."
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m safepckids.launcher --admin
) else (
    start "" pythonw -m safepckids.launcher --admin
)

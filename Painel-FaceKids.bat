@echo off
setlocal
title FaceKids - Painel Administrativo

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m facekids.app_window --mode=dashboard
) else (
    start "" pythonw -m facekids.app_window --mode=dashboard
)

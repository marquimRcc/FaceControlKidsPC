@echo off
setlocal
title FaceKids - Painel Administrativo

cd /d "%~dp0.."
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m facekids.launcher --admin
) else (
    start "" pythonw -m facekids.launcher --admin
)

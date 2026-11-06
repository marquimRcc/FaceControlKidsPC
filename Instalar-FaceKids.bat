@echo off
setlocal
title FaceKids - Instalador Inteligente

:: Verifica e solicita elevacao UAC (Administrador)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando privilegios de Administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
echo ========================================================
echo       Iniciando Instalador Moderno FaceKids...
echo ========================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m facekids.app_window --mode=wizard
) else (
    python -m facekids.app_window --mode=wizard
)

@echo off
setlocal
title SafePCKids - Instalador Inteligente

:: Verifica e solicita elevacao UAC (Administrador)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando privilegios de Administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0.."
echo Preparando Python e bibliotecas necessarias...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar-Ambiente-SafePCKids.ps1"
if %errorlevel% neq 0 (
    echo Nao foi possivel preparar os componentes do SafePCKids.
    pause
    exit /b 1
)
echo ========================================================
echo       Iniciando Instalador Moderno SafePCKids...
echo ========================================================

cd /d "%ProgramFiles%\SafePCKids"
".venv\Scripts\python.exe" -m safepckids.launcher --setup

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

cd /d "%~dp0.."
echo Preparando Python e bibliotecas necessarias...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar-Ambiente-FaceKids.ps1"
if %errorlevel% neq 0 (
    echo Nao foi possivel preparar os componentes do FaceKids.
    pause
    exit /b 1
)
echo ========================================================
echo       Iniciando Instalador Moderno FaceKids...
echo ========================================================

cd /d "%ProgramFiles%\FaceKids"
".venv\Scripts\python.exe" -m facekids.launcher --setup

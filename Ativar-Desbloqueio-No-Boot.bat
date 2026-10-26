@echo off
title FaceKids - Ativar Desbloqueio Facial no Boot
set "ROOT=%~dp0"
if not exist "%ROOT%scripts\Ativar-Desbloqueio-No-Boot.ps1" (
    set "ROOT=C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC\"
)
cd /d "%ROOT%"

:: Verificar privilegios de administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [UAC] Solicitando elevacao de Administrador...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo Privilegios de Administrador confirmados!
echo Ativando servico de reconhecimento facial no Boot (antes do logon)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\Ativar-Desbloqueio-No-Boot.ps1"
echo.
pause

@echo off
title FaceKids - Instalador de Desbloqueio Facial
cd /d "C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC"

:: Verificar privilegios de administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [UAC] Solicitando elevacao de Administrador...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo Privilegios de Administrador confirmados!
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC\scripts\Instalar-FaceKids-Nativo.ps1"
echo.
pause

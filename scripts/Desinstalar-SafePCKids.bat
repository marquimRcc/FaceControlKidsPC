@echo off
title SafePCKids - Desinstalador de Seguranca e Reset Total
cd /d "%~dp0.."

:: Verificar privilegios de administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [UAC] Solicitando elevacao de Administrador...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c ""%~f0""' -Verb RunAs"
    exit /b
)

echo Privilegios de Administrador confirmados!
echo ============================================================
echo   Executando desinstalacao completa e reset de ambiente...
echo ============================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Desinstalar-SafePCKids-Nativo.ps1" -RemoveData -RemoveWindowsUser
echo.
pause

@echo off
setlocal
title SafePCKids - Atualizacao e Ativacao do Sistema

:: Solicita elevacao de Administrador (UAC)
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo        Atualizando SafePCKids e Protecao de Rede
echo ========================================================

cd /d "%~dp0.."

echo [1/3] Parando servicos anteriores...
schtasks /end /tn SafePCKidsAuthService 2>nul

echo [2/3] Sincronizando arquivos e bibliotecas...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar-Ambiente-SafePCKids.ps1"
if %errorlevel% neq 0 (
    echo ERRO: Nao foi possivel sincronizar os arquivos.
    pause
    exit /b 1
)

echo [3/3] Aplicando reparo e ativando AdGuard Family...
cd /d "%ProgramFiles%\SafePCKids"
".venv\Scripts\python.exe" -m safepckids.repair

echo.
echo ========================================================
echo    Atualizacao concluida com sucesso!
echo ========================================================
echo O servico SafePCKids e a Protecao Global estao ativos.
timeout /t 5

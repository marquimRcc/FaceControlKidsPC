@echo off
title Cadastro Facial - Filho 1
cd /d "%~dp0"
echo ============================================================
echo      FaceControlKidsPC - CADASTRO FACIAL DO FILHO 1
echo ============================================================
echo.
echo Posicione o FILHO 1 na frente da webcam.
echo (Apenas o FILHO 1 deve estar visivel para a camera).
echo.
echo Pressione qualquer tecla para abrir a camera e comecar...
pause >nul
echo.
echo [LIGANDO A CAMERA] Olhe para a webcam e mova suavemente o rosto.
echo.
.\.venv\Scripts\python.exe -m facekids.children_pilot enroll 1
echo.
echo ============================================================
pause

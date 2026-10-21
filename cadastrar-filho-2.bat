@echo off
title Cadastro Facial - Filho 2
cd /d "C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC"
set PYTHONPATH=C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC
echo ============================================================
echo      FaceControlKidsPC - CADASTRO FACIAL DO FILHO 2
echo ============================================================
echo.
echo Posicione o FILHO 2 na frente da webcam.
echo (Apenas o FILHO 2 deve estar visivel para a camera).
echo.
echo Pressione qualquer tecla para abrir a camera e comecar...
pause >nul
echo.
echo [LIGANDO A CAMERA] Olhe para a webcam e mova suavemente o rosto.
echo.
".\.venv\Scripts\python.exe" -m facekids.children_pilot enroll 2
echo.
echo ============================================================
pause

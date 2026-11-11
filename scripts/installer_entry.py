"""SafePCKids - Ponto de Entrada do Executavel de Instalacao Unificado.

Garante a resolucao de caminhos tanto no ambiente de desenvolvimento
quanto quando extraido em sys._MEIPASS pelo PyInstaller.
"""
import os
import sys
from pathlib import Path

# Suporte ao diretorio temporario do PyInstaller (_MEIPASS)
if hasattr(sys, "_MEIPASS"):
    base_dir = Path(sys._MEIPASS)
else:
    current_dir = Path(__file__).resolve().parent
    base_dir = current_dir.parent if current_dir.name == "scripts" else current_dir

if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from safepckids.app_window import open_app_window


if __name__ == "__main__":
    sys.exit(open_app_window(mode="wizard"))

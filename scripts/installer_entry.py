"""FaceControlKidsPC - Ponto de Entrada do Executavel de Instalacao Unificado.

Quando empacotado pelo PyInstaller, este script descompacta os recursos necessarios,
garante a execucao com privilegios de Administrador e abre a interface moderna (Conceito A).
"""
import os
import sys
from pathlib import Path

# Adiciona o diretorio base ao path para importacao dos modulos facekids
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent if current_dir.name == "scripts" else current_dir
sys.path.insert(0, str(root_dir))

from facekids.app_window import open_app_window


if __name__ == "__main__":
    # Inicia diretamente no modo wizard de instalacao
    sys.exit(open_app_window(mode="wizard"))

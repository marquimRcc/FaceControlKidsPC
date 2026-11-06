"""FaceControlKidsPC - Entrada Principal do Instalador Unificado."""
import sys
from pathlib import Path

# Suporte ao empacotamento PyInstaller
if hasattr(sys, "_MEIPASS"):
    root_dir = Path(sys._MEIPASS)
else:
    root_dir = Path(__file__).resolve().parent

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Importacoes explicitas para analise estatica do PyInstaller
import facekids.app_window
import facekids.app_server
import facekids.camera_service
import facekids.installer_engine
import facekids.session_secret
import facekids.admin_auth
import facekids.storage

if __name__ == "__main__":
    sys.exit(facekids.app_window.open_app_window(mode="wizard"))

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
    mode = "auto"
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg in ("--dashboard", "-d", "--admin"):
                mode = "dashboard"
                break
            elif arg in ("--wizard", "-w"):
                mode = "wizard"
                break
            elif arg.startswith("--mode="):
                mode = arg.split("=", 1)[1]
                break
    else:
        # Se o sistema ja estiver instalado e configurado, abre diretamente no Painel Administrativo
        try:
            from facekids.installer_engine import DEFAULT_DB_FILE
            from facekids.admin_auth import AUTH_SETTING
            from facekids.storage import Storage
            if DEFAULT_DB_FILE.exists():
                store = Storage(DEFAULT_DB_FILE)
                has_pin = bool(store.get_setting(AUTH_SETTING))
                store.close()
                if has_pin:
                    mode = "dashboard"
                else:
                    mode = "wizard"
            else:
                mode = "wizard"
        except Exception:
            mode = "wizard"

    sys.exit(facekids.app_window.open_app_window(mode=mode))

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
import facekids.credential_store
import facekids.avatar_utils
import facekids.admin_auth
import facekids.storage
import facekids.auth_service
import facekids.filhos_agent

if __name__ == "__main__":
    # Despacho direto de servicos de segundo plano se acionado via Task Scheduler ou scripts
    args_lower = " ".join(sys.argv[1:]).lower()
    if "auth_service" in args_lower or "--auth-service" in args_lower:
        from facekids.auth_service import run_pipe_server
        sys.exit(run_pipe_server())
    elif "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        from facekids.filhos_agent import run_agent
        sys.exit(run_agent())

    # Como este binario e o Instalador oficial (FaceKids-Instalador.exe),
    # o comportamento padrao e sempre abrir o Assistente de Instalacao (wizard).
    # O modo painel administrativo (dashboard) e ativado apenas quando explicitamente solicitado por parametro.
    mode = "wizard"
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

    sys.exit(facekids.app_window.open_app_window(mode=mode))

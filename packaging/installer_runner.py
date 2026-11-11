"""SafePCKids - Entrada Principal do Instalador Unificado."""

import sys
from pathlib import Path

# Suporte ao empacotamento PyInstaller
if hasattr(sys, "_MEIPASS"):
    root_dir = Path(sys._MEIPASS)
else:
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent if current_dir.name in ("packaging", "scripts") else current_dir

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Importacoes explicitas para analise estatica do PyInstaller
import safepckids.app_window
import safepckids.app_server
import safepckids.camera_service
import safepckids.installer_engine
import safepckids.session_secret
import safepckids.credential_store
import safepckids.avatar_utils
import safepckids.admin_auth
import safepckids.storage
import safepckids.auth_service
import safepckids.filhos_agent

def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin_if_needed():
    """Garante privilegios de Administrador para instalacao ou painel sem elevar o agente."""
    if sys.platform != "win32":
        return
    args_lower = " ".join(sys.argv[1:]).lower()
    # O agente da sessao de Filhos DEVE rodar com privilegios limitados (sem UAC)
    if "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        return

    if not is_admin():
        import ctypes
        params = " ".join([f'"{a}"' for a in sys.argv[1:]])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        if ret > 32:
            sys.exit(0)


if __name__ == "__main__":
    # Despacho direto de servicos de segundo plano se acionado via Task Scheduler ou scripts
    args_lower = " ".join(sys.argv[1:]).lower()
    if "auth_service" in args_lower or "--auth-service" in args_lower:
        from safepckids.auth_service import run_pipe_server
        sys.exit(run_pipe_server())
    elif "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        from safepckids.filhos_agent import run_agent
        sys.exit(run_agent())

    # Se for instalador ou dashboard, garante elevacao uma unica vez para o administrador
    ensure_admin_if_needed()

    # Como este binario e o Instalador oficial (SafePCKids-Instalador.exe),
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

    sys.exit(safepckids.app_window.open_app_window(mode=mode))

"""SafePCKids - Entrada Principal do Instalador Unificado."""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

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
import safepckids.launcher


def _parse_runner_args(raw_args: List[str]) -> Tuple[Optional[str], List[str]]:
    """Extrai eventual flag '-m <modulo>' e flags de interpretador (-E, -s, -B, -u) para evitar reabertura em loop."""
    module_name: Optional[str] = None
    remaining: List[str] = []
    idx = 0
    while idx < len(raw_args):
        arg = raw_args[idx]
        if module_name is None and arg in ("-E", "-s", "-B", "-u"):
            idx += 1
            continue
        if module_name is None and arg == "-m" and idx + 1 < len(raw_args):
            module_name = raw_args[idx + 1]
            remaining.extend(raw_args[idx + 2:])
            break
        remaining.append(arg)
        idx += 1
    return module_name, [a for a in remaining if a != "--elevated"]


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin_if_needed(raw_args: Optional[List[str]] = None) -> None:
    """Garante privilegios de Administrador para instalacao ou painel sem elevar o agente."""
    if sys.platform != "win32":
        return
    argv_list = list(sys.argv[1:] if raw_args is None else raw_args)
    args_lower = " ".join(argv_list).lower()
    # O agente da sessao de Filhos DEVE rodar com privilegios limitados (sem UAC)
    if "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        return
    if "--elevated" in argv_list:
        return

    if not is_admin():
        import ctypes
        elev_args = [*argv_list, "--elevated"]
        if getattr(sys, "frozen", False):
            target_exe = sys.executable
            params = subprocess.list2cmdline(elev_args)
        else:
            exe_path = Path(sys.executable)
            if exe_path.name.lower() == "python.exe":
                pyw_candidate = exe_path.with_name("pythonw.exe")
                target_exe = str(pyw_candidate) if pyw_candidate.is_file() else sys.executable
            else:
                target_exe = sys.executable
            params = subprocess.list2cmdline([str(Path(__file__).resolve()), *elev_args])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", target_exe, params, None, 0)
        sys.exit(0 if ret > 32 else 1)


def main(argv: Optional[List[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    module_name, clean_args = _parse_runner_args(raw_args)
    args_lower = " ".join(clean_args).lower()

    # Despacho direto de servicos de segundo plano se acionado via Task Scheduler, scripts ou -m
    if module_name == "safepckids.auth_service" or "auth_service" in args_lower or "--auth-service" in args_lower:
        from safepckids.auth_service import run_pipe_server
        return run_pipe_server()
    if module_name == "safepckids.filhos_agent" or "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        from safepckids.filhos_agent import run_agent
        return run_agent()
    if module_name == "safepckids.boot_auth" or "boot_auth" in args_lower or "--boot-auth" in args_lower:
        from safepckids.boot_auth import main as boot_main
        return boot_main()

    # Se for instalador ou dashboard, garante elevacao uma unica vez para o administrador
    ensure_admin_if_needed(raw_args)

    if module_name == "safepckids.launcher":
        return safepckids.launcher.main([*clean_args, "--elevated"])

    # Como este binario e o Instalador oficial (SafePCKids-Instalador.exe),
    # o comportamento padrao e sempre abrir o Assistente de Instalacao (wizard).
    # O modo painel administrativo (dashboard) e ativado apenas quando explicitamente solicitado por parametro.
    mode = "wizard"
    for arg in clean_args:
        if arg in ("--dashboard", "-d", "--admin"):
            mode = "dashboard"
            break
        elif arg in ("--wizard", "-w", "--setup", "-s"):
            mode = "wizard"
            break
        elif arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
            break

    return safepckids.app_window.open_app_window(mode=mode)


if __name__ == "__main__":
    sys.exit(main())

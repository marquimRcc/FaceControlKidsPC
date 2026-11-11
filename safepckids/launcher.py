"""SafePCKids - Ponto de Entrada Inteligente Unificado (Smart Launcher).

Detecta o estado do sistema:
- Se já estiver instalado e configurado, abre diretamente o Painel de Controle dos Pais.
- Se for a primeira execução ou explicitamente solicitado (--setup / --wizard), abre o Assistente de Instalação.
- Suporta comandos de console (CLI):
    safepckids              -> Smart Launcher (abre Painel se já configurado, ou Assistente se novo)
    safepckids-admin        -> Abre diretamente o Painel dos Pais
    safepckids-installer    -> Abre diretamente o Assistente de Instalação
- Suporta execução de serviços de segundo plano:
    safepckids --auth-service -> Executa o serviço de autenticação facial (SYSTEM)
    safepckids --filhos-agent -> Executa o agente de monitoramento da sessão infantil
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .app_server import DEFAULT_DB_FILE
from .admin_auth import AUTH_SETTING
from .app_window import open_app_window
from .storage import Storage
from .installer_engine import INSTALL_MARKER


def is_admin() -> bool:
    """Verifica se o processo possui privilégios de Administrador no Windows."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin_if_needed() -> None:
    """Garante elevação UAC para instalador ou painel, exceto para o agente da sessão limitada."""
    if sys.platform != "win32":
        return
    args_lower = " ".join(sys.argv[1:]).lower()
    # O agente de monitoramento da sessão 'Filhos' deve rodar com privilégios limitados de usuário
    if "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        return
    if "--elevated" in sys.argv[1:]:
        return

    if not is_admin():
        import ctypes
        elev_args = [*sys.argv[1:], "--elevated"]
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
            params = subprocess.list2cmdline(["-E", "-s", "-m", "safepckids.launcher", *elev_args])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", target_exe, params, None, 0)
        sys.exit(0 if ret > 32 else 1)


def is_system_installed() -> bool:
    """Verifica se o SafePCKids já está devidamente instalado e configurado no computador."""
    try:
        if not DEFAULT_DB_FILE.exists() or not INSTALL_MARKER.exists():
            return False

        store = Storage(DEFAULT_DB_FILE)
        try:
            return bool(store.get_setting(AUTH_SETTING))
        finally:
            store.close()
    except Exception:
        return False


def main(argv: Optional[list[str]] = None) -> int:
    """Ponto de entrada inteligente do SafePCKids."""
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = [a for a in raw_args if a != "--elevated"]
    args_lower = " ".join(args).lower()

    # Roteamento de serviços de segundo plano
    if "auth_service" in args_lower or "--auth-service" in args_lower:
        from .auth_service import run_pipe_server
        return run_pipe_server()
    elif "filhos_agent" in args_lower or "--filhos-agent" in args_lower:
        from .filhos_agent import run_agent
        return run_agent()

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        username = ctypes.create_unicode_buffer(257)
        size = wintypes.DWORD(len(username))
        if ctypes.windll.advapi32.GetUserNameW(username, ctypes.byref(size)):
            if username.value.casefold() == "filhos":
                return 1
    ensure_admin_if_needed()

    mode = "auto"
    if any(a in ("--admin", "-a", "--dashboard", "-d", "admin") for a in args):
        mode = "dashboard"
    elif any(a in ("--setup", "-s", "--wizard", "-w", "--install", "install", "setup") for a in args):
        mode = "wizard"
    else:
        # Smart Launcher: se já instalado, abre o painel dos pais; caso contrário, abre o assistente
        mode = "dashboard" if is_system_installed() else "wizard"

    return open_app_window(mode=mode)


def admin_main() -> int:
    """Entrada direta para o comando 'safepckids-admin'."""
    return main(["--admin"])


def installer_main() -> int:
    """Entrada direta para o comando 'safepckids-installer'."""
    return main(["--setup"])


if __name__ == "__main__":
    sys.exit(main())

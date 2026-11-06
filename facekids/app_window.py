"""FaceControlKidsPC - Inicializador da Janela de Aplicativo Nativa.

Executa o servidor local e abre a interface moderna (Conceito A)
em uma janela dedicada e acelerada por hardware via Microsoft Edge (--app).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from .app_server import run_app_server, find_free_port


EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]


def find_edge_executable() -> str | None:
    for path in EDGE_PATHS:
        if os.path.exists(path):
            return path
    return None


def open_app_window(mode: str = "auto", port: int | None = None) -> int:
    """Inicia o servidor e exibe a janela da aplicacao."""
    server, active_port = run_app_server(port)
    url = f"http://127.0.0.1:{active_port}/"
    if mode in ("wizard", "install"):
        url += "?mode=wizard"
    elif mode in ("dashboard", "admin"):
        url += "?mode=dashboard"

    edge = find_edge_executable()
    profile_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "FaceKids" / "app_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    if edge and sys.platform == "win32":
        cmd = [
            edge,
            f"--app={url}",
            "--window-size=1220,840",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            server.shutdown()
            return 0
        except Exception:
            pass

    # Fallback para navegador padrao caso o Edge nao esteja presente
    import webbrowser
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaceKids Modern App Launcher")
    parser.add_argument("--mode", choices=("auto", "wizard", "dashboard"), default="auto")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    sys.exit(open_app_window(mode=args.mode, port=args.port))

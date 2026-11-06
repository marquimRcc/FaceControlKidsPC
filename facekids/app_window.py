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

from .app_server import run_app_server, find_free_port, FaceKidsApiHandler


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
    """Inicia o servidor e exibe a janela da aplicacao mantendo o servidor ativo."""
    server, active_port = run_app_server(port)
    url = f"http://127.0.0.1:{active_port}/"
    if mode in ("wizard", "install"):
        url += "?mode=wizard"
    elif mode in ("dashboard", "admin"):
        url += "?mode=dashboard"

    edge = find_edge_executable()
    # Usa LOCALAPPDATA para garantir permissao de escrita sem elevacao
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    profile_dir = Path(local_app_data) / "FaceKids" / "app_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    FaceKidsApiHandler.last_activity_time = time.time()

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
            subprocess.Popen(cmd)
        except Exception:
            pass
    else:
        import webbrowser
        webbrowser.open(url)

    # Mantem o servidor ativo enquanto houver comunicacao com a janela (heartbeat / requisicoes)
    # Periodo de graca inicial de 15 segundos para a janela carregar
    time.sleep(3)
    try:
        idle_count = 0
        while True:
            time.sleep(1)
            elapsed = time.time() - FaceKidsApiHandler.last_activity_time
            if elapsed > 12.0:
                idle_count += 1
                if idle_count >= 5:  # 5 segundos sem requisicao apos o timeout
                    break
            else:
                idle_count = 0
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaceKids Modern App Launcher")
    parser.add_argument("--mode", choices=("auto", "wizard", "dashboard"), default="auto")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    sys.exit(open_app_window(mode=args.mode, port=args.port))

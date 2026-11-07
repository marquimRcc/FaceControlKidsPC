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
    # Utiliza diretorio de perfil temporario exclusivo para evitar conflito de processo ou sessoes do Edge
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", os.path.expanduser("~")))
    profile_dir = Path(temp_dir) / "FaceKidsEdgeProfile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    FaceKidsApiHandler.last_activity_time = time.time()
    FaceKidsApiHandler.shutdown_requested = False
    FaceKidsApiHandler.is_installing = False
    start_time = time.time()

    proc = None
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
        except Exception:
            pass
    else:
        import webbrowser
        webbrowser.open(url)

    # Mantem o servidor ativo enquanto a janela estiver aberta
    time.sleep(2)
    try:
        while True:
            time.sleep(1)

            # 1. Enquanto uma instalacao estiver em processamento, o servidor NUNCA encerra
            if getattr(FaceKidsApiHandler, "is_installing", False):
                FaceKidsApiHandler.last_activity_time = time.time()
                continue

            # 2. Encerramento explicito recebido da janela (beforeunload / shutdown)
            if getattr(FaceKidsApiHandler, "shutdown_requested", False):
                break

            # 3. Se o processo Edge dedicado ainda estiver ativo, mantem vivo
            if proc is not None and proc.poll() is None:
                continue

            # 4. Grace period inicial de abertura: pelo menos 180 segundos
            if time.time() - start_time < 180.0:
                continue

            # 5. No modo assistente/instalacao (wizard/install), o instalador NUNCA encerra
            # por inatividade enquanto o usuario estiver configurando
            if mode in ("wizard", "install"):
                elapsed = time.time() - FaceKidsApiHandler.last_activity_time
                if elapsed > 1800.0:
                    break
                continue

            # 6. Timeout generoso de inatividade no painel (600 segundos sem nenhum heartbeat)
            elapsed = time.time() - FaceKidsApiHandler.last_activity_time
            if elapsed > 600.0:
                break
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

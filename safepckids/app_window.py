"""SafePCKids - Inicializador da Janela de Aplicativo Nativa.

Executa o servidor local quando necessário e abre a interface moderna (Conceito A)
em uma janela dedicada de aplicativo do SO (--app), mantendo uma ponte local
na sessão do usuário para abrir links externos no navegador padrão do sistema.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from .app_server import run_app_server, SafePCKidsApiHandler


def is_server_listening(port: int = 8765) -> bool:
    """Verifica se o servidor SafePCKids já está respondendo na porta indicada."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/heartbeat", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


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


def _is_allowed_remote_url(target_url: str, active_port: int) -> bool:
    """Permite abrir apenas a rota /remote do servidor local SafePCKids."""
    try:
        parsed = urllib.parse.urlparse(target_url)
    except Exception:
        return False
    if parsed.scheme != "http":
        return False
    if parsed.port not in (active_port, None):
        return False
    if parsed.port is None and active_port != 80:
        return False
    return parsed.path in ("/remote", "/remote/", "/remote.html")


def start_desktop_bridge(active_port: int) -> tuple[ThreadingHTTPServer, int]:
    """Inicia ponte HTTP local na sessão do desktop para abrir URLs no navegador padrão."""
    allowed_origins = {
        f"http://127.0.0.1:{active_port}",
        f"http://localhost:{active_port}",
    }

    class _DesktopBridgeHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _send_cors_headers(self) -> None:
            origin = self.headers.get("Origin", "")
            allow_origin = origin if origin in allowed_origins else f"http://127.0.0.1:{active_port}"
            self.send_header("Access-Control-Allow-Origin", allow_origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_POST(self) -> None:
            if urllib.parse.urlparse(self.path).path != "/open-remote":
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(min(length, 4096)) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                payload = {}

            target_url = str(payload.get("url") or f"http://127.0.0.1:{active_port}/remote").strip()
            if not _is_allowed_remote_url(target_url, active_port):
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"ok":false,"error":"URL nao permitida"}')
                return

            opened = webbrowser.open(target_url)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"ok": bool(opened)}).encode("utf-8"))

    bridge = ThreadingHTTPServer(("127.0.0.1", 0), _DesktopBridgeHandler)
    bridge_port = bridge.server_address[1]
    thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    thread.start()
    return bridge, bridge_port


def open_app_window(mode: str = "auto", port: int | None = None) -> int:
    """Inicia o servidor e exibe a janela da aplicacao mantendo o servidor ativo."""
    server = None
    target_port = port or 8765
    if port is None and is_server_listening(target_port):
        active_port = target_port
    else:
        server, active_port = run_app_server(port)
    url = f"http://127.0.0.1:{active_port}/"
    if mode in ("wizard", "install"):
        url += "?mode=wizard"
    elif mode in ("dashboard", "admin"):
        url += "?mode=dashboard"

    bridge_server = None
    try:
        bridge_server, bridge_port = start_desktop_bridge(active_port)
        sep = "&" if "?" in url else "?"
        url += f"{sep}desktop_bridge={bridge_port}"
    except Exception:
        bridge_server = None

    edge = find_edge_executable()
    # Utiliza diretorio de perfil temporario exclusivo para evitar conflito de processo ou sessoes do Edge
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", os.path.expanduser("~")))
    profile_dir = Path(temp_dir) / "SafePCKidsEdgeProfile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    SafePCKidsApiHandler.last_activity_time = time.time()
    SafePCKidsApiHandler.shutdown_requested = False
    SafePCKidsApiHandler.is_installing = False
    start_time = time.time()

    proc = None
    if edge and sys.platform == "win32":
        cmd = [
            edge,
            f"--app={url}",
            "--window-size=1220,840",
            f"--user-data-dir={profile_dir}",
            "--guest",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-signin-promo",
            "--disable-features=msImplicitSignIn",
        ]
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
            proc = subprocess.Popen(cmd, creationflags=creation_flags)
        except Exception:
            pass
    else:
        webbrowser.open(url)

    # Mantem o servidor/ponte ativos enquanto a janela estiver aberta
    time.sleep(2)
    try:
        while True:
            time.sleep(1)

            # 1. Enquanto uma instalacao estiver em processamento, o servidor NUNCA encerra
            if getattr(SafePCKidsApiHandler, "is_installing", False):
                SafePCKidsApiHandler.last_activity_time = time.time()
                continue

            # 2. Encerramento explicito recebido da janela (beforeunload / shutdown)
            if getattr(SafePCKidsApiHandler, "shutdown_requested", False):
                break

            # 3. Se o processo Edge dedicado ainda estiver ativo, mantem vivo
            if proc is not None and proc.poll() is None:
                continue

            # 3b. Se o servidor ja pertencia ao servico e a janela do app foi fechada, encerra a ponte
            if server is None and proc is not None and proc.poll() is not None and (time.time() - start_time >= 5.0):
                break

            # 4. Grace period inicial de abertura: pelo menos 180 segundos
            if time.time() - start_time < 180.0:
                continue

            # 5. No modo assistente/instalacao (wizard/install), o instalador NUNCA encerra
            # por inatividade enquanto o usuario estiver configurando
            if mode in ("wizard", "install"):
                elapsed = time.time() - SafePCKidsApiHandler.last_activity_time
                if elapsed > 1800.0:
                    break
                continue

            # 6. Timeout generoso de inatividade no painel (600 segundos sem nenhum heartbeat)
            elapsed = time.time() - SafePCKidsApiHandler.last_activity_time
            if elapsed > 600.0:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if bridge_server is not None:
            try:
                bridge_server.shutdown()
                bridge_server.server_close()
            except Exception:
                pass
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SafePCKids Modern App Launcher")
    parser.add_argument("--mode", choices=("auto", "wizard", "dashboard"), default="auto")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    sys.exit(open_app_window(mode=args.mode, port=args.port))

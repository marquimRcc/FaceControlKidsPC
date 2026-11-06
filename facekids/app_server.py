"""FaceControlKidsPC - Servidor de Aplicacao Local (Modern UI & API).

Fornece a interface visual moderna (Conceito A: One-Click Wizard + Painel Admin)
e os endpoints REST locais para comunicacao em tempo real entre o frontend e o sistema.
"""
from __future__ import annotations

import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from .admin_auth import verify_pin, hash_pin, AUTH_SETTING
from .storage import Storage
from .installer_engine import get_system_diagnostics, setup_system, PROGRAMDATA_DIR, DEFAULT_DB_FILE
from .camera_service import CameraService


logger = logging.getLogger("facekids.app_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

UI_DIR = Path(__file__).resolve().parent / "ui_assets"


class FaceKidsApiHandler(BaseHTTPRequestHandler):
    server_token: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        # Suprime logs excessivos de polling no console
        pass

    def send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FaceKids-Token")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FaceKids-Token")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self.handle_status()
        elif path == "/api/diagnostics":
            self.handle_diagnostics()
        elif path == "/api/dashboard":
            self.handle_dashboard()
        elif path == "/api/camera/stream":
            self.handle_camera_stream()
        elif path == "/api/camera/preview":
            self.handle_camera_preview()
        elif path == "/api/camera/enroll/status":
            self.handle_camera_enroll_status()
        elif path.startswith("/api/child/") and path.endswith("/avatar"):
            self.handle_child_avatar(path)
        elif path.startswith("/ui/") or path == "/" or path == "/index.html":
            self.serve_static(path)
        else:
            self.send_json({"error": "Endpoint nao encontrado"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            body = {}

        if path == "/api/install":
            self.handle_install(body)
        elif path == "/api/auth/verify":
            self.handle_auth_verify(body)
        elif path == "/api/child/bonus":
            self.handle_child_bonus(body)
        elif path == "/api/child/limit":
            self.handle_child_limit(body)
        elif path == "/api/child/add":
            self.handle_child_add(body)
        elif path == "/api/camera/enroll/start":
            self.handle_camera_enroll_start(body)
        else:
            self.send_json({"error": "Endpoint POST desconhecido"}, 404)

    def handle_status(self) -> None:
        """Indica se o sistema ja foi instalado ou se deve abrir o Wizard."""
        has_db = DEFAULT_DB_FILE.exists()
        has_pin = False
        children_count = 0

        if has_db:
            try:
                store = Storage(DEFAULT_DB_FILE)
                has_pin = bool(store.get_setting(AUTH_SETTING))
                children_count = len(store.list_people())
                store.close()
            except Exception:
                pass

        is_installed = has_db and has_pin
        self.send_json({
            "installed": is_installed,
            "has_pin": has_pin,
            "children_count": children_count,
            "default_mode": "dashboard" if is_installed else "wizard"
        })

    def handle_diagnostics(self) -> None:
        diag = get_system_diagnostics()
        self.send_json(diag)

    def handle_install(self, data: Dict[str, Any]) -> None:
        master_pin = str(data.get("pin", "")).strip()
        first_child = str(data.get("child_name", "")).strip()
        limit_hours = float(data.get("daily_limit_hours", 2.0))
        limit_minutes = int(limit_hours * 60)

        if not master_pin or len(master_pin) < 4:
            self.send_json({"ok": False, "error": "O PIN mestre precisa ter pelo menos 4 digitos."}, 400)
            return

        ok, msg = setup_system(
            master_pin=master_pin,
            first_child_name=first_child if first_child else None,
            first_child_daily_limit_minutes=limit_minutes
        )
        self.send_json({"ok": ok, "message": msg})

    def handle_auth_verify(self, data: Dict[str, Any]) -> None:
        pin = str(data.get("pin", "")).strip()
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"ok": False, "error": "Banco de dados ainda nao inicializado."}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            stored = store.get_setting(AUTH_SETTING)
            if not stored:
                self.send_json({"ok": True, "message": "Sem PIN configurado."})
                return
            valid = verify_pin(pin, stored)
            self.send_json({"ok": valid, "error": None if valid else "PIN incorreto."})
        finally:
            store.close()

    def handle_dashboard(self) -> None:
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"children": [], "summary": {}})
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            people = store.list_people()
            children = []
            total_used_today = 0
            total_limit_today = 0

            for p in people:
                cid = p["id"]
                name = p["name"]
                limit_sec = p.get("daily_limit_seconds", 7200)
                used_sec = store.get_today_usage_seconds(cid)
                bonus_sec = store.get_today_bonus_seconds(cid)
                remaining_sec = max(0, limit_sec + bonus_sec - used_sec)

                total_used_today += used_sec
                total_limit_today += limit_sec

                children.append({
                    "id": cid,
                    "name": name,
                    "status": "online" if used_sec > 0 and remaining_sec > 0 else "offline",
                    "remaining_seconds": remaining_sec,
                    "used_seconds": used_sec,
                    "limit_seconds": limit_sec,
                    "bonus_seconds": bonus_sec,
                    "remaining_formatted": f"{remaining_sec // 3600}h {(remaining_sec % 3600) // 60}m",
                    "used_formatted": f"{used_sec // 3600}h {(used_sec % 3600) // 60}m",
                    "percent_remaining": round((remaining_sec / max(1, limit_sec + bonus_sec)) * 100)
                })

            summary = {
                "active_children": len(children),
                "total_used_formatted": f"{total_used_today // 3600}h {(total_used_today % 3600) // 60}m",
                "total_limit_formatted": f"{total_limit_today // 3600}h {(total_limit_today % 3600) // 60}m"
            }
            self.send_json({"children": children, "summary": summary})
        finally:
            store.close()

    def handle_child_bonus(self, data: Dict[str, Any]) -> None:
        cid = int(data.get("child_id", 0))
        minutes = int(data.get("minutes", 15))
        if cid <= 0 or minutes <= 0:
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            store.add_daily_bonus(cid, minutes)
            self.send_json({"ok": True, "message": f"Bonus de {minutes}m concedido."})
        finally:
            store.close()

    def handle_child_limit(self, data: Dict[str, Any]) -> None:
        cid = int(data.get("child_id", 0))
        hours = float(data.get("hours", 2.0))
        minutes = int(hours * 60)
        if cid <= 0 or minutes <= 0:
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            store.set_daily_limit(cid, minutes)
            self.send_json({"ok": True, "message": f"Limite atualizado para {hours}h."})
        finally:
            store.close()

    def handle_child_add(self, data: Dict[str, Any]) -> None:
        name = str(data.get("name", "")).strip()
        hours = float(data.get("daily_limit_hours", 2.0))
        if not name:
            self.send_json({"ok": False, "error": "Nome obrigatorio"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            new_id = store.add_person(name, int(hours * 60))
            self.send_json({"ok": True, "id": new_id, "name": name})
        finally:
            store.close()

    def handle_camera_preview(self) -> None:
        """Captura um snapshot da camera em Base64 para exibicao no frontend."""
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
            if not cap.isOpened():
                self.send_json({"ok": False, "error": "Camera indisponivel"}, 503)
                return
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                self.send_json({"ok": False, "error": "Falha ao capturar quadro"}, 500)
                return

            # Converte em JPEG e depois base64
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buffer).decode("ascii")
            self.send_json({"ok": True, "image": f"data:image/jpeg;base64,{b64}"})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)


    def handle_camera_stream(self) -> None:
        """Transmite streaming MJPEG de baixa latência em tempo real."""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            cam = CameraService.get_instance()
            for chunk in cam.generate_mjpeg_stream():
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_camera_enroll_start(self, body: Dict[str, Any]) -> None:
        """Dispara a captura de 12 fotos para o cadastro biométrico da criança."""
        cid = int(body.get("child_id", 0))
        if cid <= 0:
            if DEFAULT_DB_FILE.exists():
                try:
                    store = Storage(DEFAULT_DB_FILE)
                    people = store.list_people()
                    store.close()
                    if people:
                        cid = people[0]["id"]
                except Exception:
                    pass
        if cid <= 0:
            self.send_json({"ok": False, "error": "Crie o perfil da criança antes de cadastrar a biometria."}, 400)
            return

        cam = CameraService.get_instance()
        res = cam.start_enrollment(cid, DEFAULT_DB_FILE)
        self.send_json(res)

    def handle_camera_enroll_status(self) -> None:
        """Consulta o progresso da captura facial (ex: 5 de 12 fotos)."""
        cam = CameraService.get_instance()
        self.send_json(cam.enrollment_state)

    def handle_child_avatar(self, path: str) -> None:
        """Serve o avatar PNG circular da criança diretamente."""
        try:
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "child":
                cid = int(parts[2])
                avatar_file = PROGRAMDATA_DIR / "fotos" / f"crianca_{cid}_avatar.png"
                if avatar_file.exists():
                    data = avatar_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(data)
                    return
        except Exception:
            pass
        self.send_error(404, "Avatar não encontrado")

    def serve_static(self, path: str) -> None:
        if path in ("/", "/index.html"):
            target = UI_DIR / "app.html"
        else:
            rel = path.lstrip("/ui/")
            target = UI_DIR / rel

        if not target.exists() or not target.is_file():
            # Fallback para o HTML principal do Concept A
            target = UI_DIR / "app.html"

        if not target.exists():
            self.send_error(404, "Arquivo nao encontrado")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "text/html"

        try:
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Erro ao servir arquivo")


def find_free_port(start: int = 14220) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def run_app_server(port: Optional[int] = None) -> Tuple[HTTPServer, int]:
    port = port or find_free_port()
    server = HTTPServer(("127.0.0.1", port), FaceKidsApiHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info(f"Servidor FaceKids ativo em http://127.0.0.1:{port}")
    return server, port


if __name__ == "__main__":
    server, port = run_app_server()
    print(f"Servidor FaceKids ativo em http://127.0.0.1:{port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()

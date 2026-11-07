"""FaceControlKidsPC - Servidor de Aplicacao Local (Modern UI & API).

Fornece a interface visual moderna (Conceito A: One-Click Wizard + Painel Admin)
e os endpoints REST locais para comunicacao em tempo real entre o frontend e o sistema.
"""
from __future__ import annotations

import base64
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
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
import traceback
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from .admin_auth import verify_pin, hash_pin, AUTH_SETTING
from .storage import Storage
from .installer_engine import (
    get_system_diagnostics,
    setup_system,
    uninstall_system,
    verify_runtime_health,
    ensure_filhos_windows_user,
    PROGRAMDATA_DIR,
    DEFAULT_DB_FILE,
    _run_win_cmd,
)
from .session_secret import get_session_secret
from .credential_store import (
    get_filhos_credentials,
    get_filhos_password,
    save_filhos_credentials,
)
from .avatar_utils import (
    get_child_sample_photos,
    select_child_sample_photo,
    get_child_avatar_path,
    remove_child_avatar_files,
    AVATAR_DIR,
)
from .camera_service import CameraService


logger = logging.getLogger("facekids.app_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"


def get_ui_dir() -> Path:
    """Localiza o diretorio de assets HTML/JS tanto no venv quanto no _MEIPASS."""
    if hasattr(sys, "_MEIPASS"):
        p1 = Path(sys._MEIPASS) / "facekids" / "ui_assets"
        if p1.exists():
            return p1
        p2 = Path(sys._MEIPASS) / "ui_assets"
        if p2.exists():
            return p2
    return Path(__file__).resolve().parent / "ui_assets"


UI_DIR = get_ui_dir()


class FaceKidsApiHandler(BaseHTTPRequestHandler):
    last_activity_time: float = time.time()
    shutdown_requested: bool = False
    is_installing: bool = False

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def send_json(self, data: Any, status: int = 200) -> None:
        FaceKidsApiHandler.last_activity_time = time.time()
        payload_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload_bytes)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FaceKids-Token, X-Session-Token")
            self.end_headers()
            self.wfile.write(payload_bytes)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.debug(f"Conexao fechada pelo cliente ao enviar JSON: {e}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FaceKids-Token, X-Session-Token")
        self.end_headers()

    def do_GET(self) -> None:
        FaceKidsApiHandler.last_activity_time = time.time()
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/status":
                self.handle_status()
            elif path == "/api/diagnostics":
                self.handle_diagnostics()
            elif path == "/api/service/status":
                self.handle_service_status()
            elif path == "/api/dashboard":
                self.handle_dashboard()
            elif path == "/api/heartbeat":
                self.send_json({"ok": True, "time": time.time()})
            elif path == "/api/shutdown":
                if not FaceKidsApiHandler.is_installing:
                    FaceKidsApiHandler.shutdown_requested = True
                self.send_json({"ok": True, "message": "Encerrando servidor..."})
            elif path == "/api/camera/stream":
                self.handle_camera_stream()
            elif path == "/api/camera/preview":
                self.handle_camera_preview()
            elif path == "/api/camera/enroll/status":
                self.handle_camera_enroll_status()
            elif path.startswith("/api/child/") and path.endswith("/avatar"):
                self.handle_child_avatar(path)
            elif path.startswith("/api/children/") and "/photos/" in path:
                self.handle_child_photo_sample(path)
            elif path.startswith("/api/children/") and path.endswith("/photos"):
                self.handle_child_photos_list(path)
            elif path.startswith("/assets/") or path == "/favicon.ico":
                self.serve_asset(path)
            elif path.startswith("/ui/") or path == "/" or path == "/index.html":
                self.serve_static(path)
            else:
                self.send_json({"error": "Endpoint nao encontrado"}, 404)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            logger.error(f"Erro nao tratado em do_GET: {traceback.format_exc()}")
            try:
                self.send_json({"ok": False, "error": f"Erro interno: {exc}"}, 500)
            except Exception:
                pass

    def do_POST(self) -> None:
        FaceKidsApiHandler.last_activity_time = time.time()
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                body = {}

            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/install":
                self.handle_install(body)
            elif path == "/api/auth/verify":
                self.handle_auth_verify(body)
            elif path == "/api/settings/windows-account":
                self.handle_settings_windows_account(body)
            elif path == "/api/service/restart":
                self.handle_service_restart(body)
            elif path.startswith("/api/children/") and path.endswith("/photos/select"):
                self.handle_child_photo_select(path, body)
            elif path.startswith("/api/children/") and path.endswith("/recapture"):
                self.handle_child_recapture(path, body)
            elif path == "/api/uninstall":
                self.handle_uninstall(body)
            elif path == "/api/child/bonus":
                self.handle_child_bonus(body)
            elif path == "/api/child/limit":
                self.handle_child_limit(body)
            elif path == "/api/child/add":
                self.handle_child_add(body)
            elif path == "/api/child/delete":
                self.handle_child_delete(body)
            elif path == "/api/child/rename":
                self.handle_child_rename(body)
            elif path == "/api/camera/enroll/start":
                self.handle_camera_enroll_start(body)
            elif path == "/api/settings/pin":
                self.handle_settings_pin(body)
            elif path == "/api/shutdown":
                if not FaceKidsApiHandler.is_installing:
                    FaceKidsApiHandler.shutdown_requested = True
                self.send_json({"ok": True, "message": "Encerrando servidor..."})
            else:
                self.send_json({"error": "Endpoint POST desconhecido"}, 404)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            logger.error(f"Erro nao tratado em do_POST: {traceback.format_exc()}")
            try:
                self.send_json({"ok": False, "error": f"Erro interno do servidor: {exc}"}, 500)
            except Exception:
                pass

    def handle_status(self) -> None:
        has_db = DEFAULT_DB_FILE.exists()
        has_pin = False
        children_count = 0

        if has_db:
            try:
                store = Storage(DEFAULT_DB_FILE)
                has_pin = bool(store.get_setting(AUTH_SETTING))
                children_count = len(store.people())
                store.close()
            except Exception:
                pass

        is_installed = has_db and has_pin
        u, _ = get_filhos_credentials()
        self.send_json({
            "installed": is_installed,
            "has_pin": has_pin,
            "children_count": children_count,
            "windows_user": u,
            "default_mode": "dashboard" if is_installed else "wizard"
        })

    def handle_diagnostics(self) -> None:
        diag = get_system_diagnostics()
        self.send_json(diag)

    def handle_service_status(self) -> None:
        health = verify_runtime_health()
        self.send_json({"ok": True, "health": health})

    def handle_service_restart(self, data: Optional[Dict[str, Any]] = None) -> None:
        service_name = "FaceKidsAuthService"
        if data and data.get("service"):
            cand = str(data.get("service")).strip()
            if cand in ("FaceKidsAuthService", "FaceKidsFilhosAgent"):
                service_name = cand
            else:
                self.send_json({"ok": False, "error": f"Servico '{cand}' nao autorizado."}, 400)
                return

        if sys.platform == "win32":
            _run_win_cmd(["schtasks", "/run", "/tn", service_name], timeout=5.0)
        self.send_json({"ok": True, "message": f"Servico {service_name} reiniciado com sucesso."})

    def handle_settings_windows_account(self, data: Dict[str, Any]) -> None:
        username = str(data.get("username", "Filhos")).strip() or "Filhos"
        password = str(data.get("password", "")).strip()

        if not password:
            self.send_json({"ok": False, "error": "A senha nao pode ser vazia."}, 400)
            return

        ok, msg = ensure_filhos_windows_user(password, username=username)
        self.send_json({"ok": ok, "message": msg})

    def handle_install(self, data: Dict[str, Any]) -> None:
        FaceKidsApiHandler.is_installing = True
        FaceKidsApiHandler.last_activity_time = time.time()
        try:
            master_pin = str(data.get("pin", "")).strip()
            raw_child = data.get("child_name")
            first_child = str(raw_child).strip() if raw_child is not None else ""
            if not first_child or first_child.lower() in ("none", "null"):
                first_child = "Filho" 
            limit_hours = float(data.get("daily_limit_hours", 2.0))
            limit_minutes = int(limit_hours * 60)
            filhos_pass = str(data.get("filhos_password", "")).strip()
            filhos_user = str(data.get("filhos_username", "Filhos")).strip() or "Filhos"

            if not master_pin or len(master_pin) < 4:
                self.send_json({"ok": False, "error": "O PIN mestre precisa ter pelo menos 4 digitos."}, 400)
                return

            ok, msg = setup_system(
                master_pin=master_pin,
                first_child_name=first_child if first_child else None,
                first_child_daily_limit_minutes=limit_minutes,
                filhos_password=filhos_pass if filhos_pass else None,
                filhos_username=filhos_user
            )
            current_token = get_session_secret()
            self.send_json({
                "ok": ok,
                "status": "success" if ok else "error",
                "token": current_token,
                "message": msg
            })
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            logger.error(f"Erro em handle_install: {traceback.format_exc()}")
            self.send_json({"ok": False, "error": f"Erro durante a instalacao: {exc}"}, 500)
        finally:
            FaceKidsApiHandler.is_installing = False
            FaceKidsApiHandler.last_activity_time = time.time()

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

    def handle_settings_pin(self, data: Dict[str, Any]) -> None:
        pin = str(data.get("pin", "")).strip()
        if not pin or len(pin) < 4:
            self.send_json({"ok": False, "error": "PIN precisa ter de 4 a 6 digitos."}, 400)
            return
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"ok": False, "error": "Banco de dados ainda nao inicializado."}, 400)
            return
        store = Storage(DEFAULT_DB_FILE)
        try:
            store.set_setting(AUTH_SETTING, hash_pin(pin))
            self.send_json({"ok": True, "message": "PIN atualizado com sucesso."})
        finally:
            store.close()

    def handle_dashboard(self) -> None:
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"children": [], "summary": {}})
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            people = store.people()
            children = []
            total_used_today = 0
            total_limit_today = 0

            for p in people:
                cid = p[0]
                name = p[1]
                limit_sec = p[2]
                used_sec = int(store.used(cid))
                bonus_sec = int(store.bonus(cid))
                remaining_sec = int(store.remaining(cid))

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
                "total_used_seconds": total_used_today,
                "total_limit_seconds": total_limit_today,
                "total_used_formatted": f"{total_used_today // 3600}h {(total_used_today % 3600) // 60}m",
                "total_limit_formatted": f"{total_limit_today // 3600}h {(total_limit_today % 3600) // 60}m"
            }
            self.send_json({"children": children, "summary": summary})
        finally:
            store.close()

    def handle_child_photos_list(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        try:
            cid = int(parts[2])
        except Exception:
            self.send_json({"ok": False, "error": "ID da crianca invalido."}, 400)
            return

        store = Storage(DEFAULT_DB_FILE) if DEFAULT_DB_FILE.exists() else None
        try:
            samples = get_child_sample_photos(cid, store=store)
            items = []
            for s in samples:
                idx = s["index"]
                items.append({
                    "index": idx,
                    "label": s.get("label", f"Foto {idx}"),
                    "selected": s.get("selected", False),
                    "url": f"/api/children/{cid}/photos/{idx}"
                })
            self.send_json({"ok": True, "child_id": cid, "photos": items})
        finally:
            if store:
                store.close()

    def handle_child_photo_sample(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        try:
            cid = int(parts[2])
            idx = int(parts[4])
        except Exception:
            self.send_error(400, "Parametros invalidos")
            return

        sample_p = PROGRAMDATA_DIR / "fotos" / f"amostras_{cid}" / f"amostra_{idx}.jpg"
        if sample_p.exists() and sample_p.stat().st_size > 0:
            data = sample_p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)
            return

        # Fallback para profile_photos no SQLite
        store = Storage(DEFAULT_DB_FILE) if DEFAULT_DB_FILE.exists() else None
        if store and hasattr(store, "profile_photos"):
            try:
                db_photos = store.profile_photos(cid)
                if 0 <= idx - 1 < len(db_photos):
                    data = db_photos[idx - 1][1]
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.end_headers()
                    self.wfile.write(data)
                    store.close()
                    return
            except Exception:
                pass
        if store:
            store.close()

        # Fallback para crianca_cid.jpg
        fallback_p = PROGRAMDATA_DIR / "fotos" / f"crianca_{cid}.jpg"
        if fallback_p.exists():
            data = fallback_p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "Amostra nao encontrada")

    def handle_child_photo_select(self, path: str, body: Dict[str, Any]) -> None:
        parts = [p for p in path.split("/") if p]
        try:
            cid = int(parts[2])
            idx = int(body.get("index", 1))
        except Exception:
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        sample_p = PROGRAMDATA_DIR / "fotos" / f"amostras_{cid}" / f"amostra_{idx}.jpg"
        store = Storage(DEFAULT_DB_FILE) if DEFAULT_DB_FILE.exists() else None
        try:
            if sample_p.exists() and sample_p.stat().st_size > 0:
                ok = select_child_sample_photo(cid, sample_p, store=store, sample_index=idx)
            else:
                photo_bytes = None
                if store and hasattr(store, "profile_photos"):
                    photos = store.profile_photos(cid)
                    if 0 <= idx - 1 < len(photos):
                        photo_bytes = photos[idx - 1][1]
                if photo_bytes:
                    ok = select_child_sample_photo(cid, photo_bytes, store=store, sample_index=idx)
                else:
                    self.send_json({"ok": False, "error": "Arquivo de amostra nao encontrado"}, 404)
                    return
            self.send_json({"ok": ok, "message": f"Foto {idx} selecionada como avatar oficial."})
        finally:
            if store:
                store.close()

    def handle_child_recapture(self, path: str, body: Dict[str, Any]) -> None:
        parts = [p for p in path.split("/") if p]
        try:
            cid = int(parts[2])
        except Exception:
            self.send_json({"ok": False, "error": "Parametro invalido"}, 400)
            return

        cam = CameraService.get_instance()
        res = cam.start_enrollment(cid, DEFAULT_DB_FILE)
        self.send_json(res)

    def handle_child_bonus(self, data: Dict[str, Any]) -> None:
        try:
            cid = int(data.get("child_id", 0))
            minutes = int(data.get("minutes", 15))
        except (ValueError, TypeError):
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        if cid <= 0 or abs(minutes) > 1440:
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            if minutes > 0:
                store.add_bonus(cid, minutes)
                self.send_json({"ok": True, "message": f"Bônus de +{minutes}m aplicado com sucesso."})
            elif minutes < 0:
                store.reduce_time(cid, abs(minutes))
                self.send_json({"ok": True, "message": f"Redução de {abs(minutes)}m aplicada com sucesso."})
            else:
                self.send_json({"ok": True, "message": "Nenhuma alteração de tempo aplicada."})
        except Exception as e:
            self.send_json({"ok": False, "error": f"Erro ao aplicar ajuste de tempo: {e}"}, 400)
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

    def handle_child_rename(self, body: Dict[str, Any]) -> None:
        cid = int(body.get("child_id", 0))
        new_name = str(body.get("name", "")).strip()
        if cid <= 0 or not new_name or len(new_name) > 80:
            self.send_json({"ok": False, "error": "ID e nome valido sao obrigatorios."}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            store.update_person_name(cid, new_name)
            self.send_json({"ok": True, "message": f"Perfil #{cid} renomeado para '{new_name}'."})
        finally:
            store.close()

    def handle_child_delete(self, body: Dict[str, Any]) -> None:
        cid = int(body.get("child_id", 0))
        if cid <= 0:
            self.send_json({"ok": False, "error": "ID da crianca invalido."}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            store.remove_person(cid)
            remove_child_avatar_files(cid)
            self.send_json({"ok": True, "message": "Perfil infantil removido com sucesso."})
        finally:
            store.close()

    def handle_uninstall(self, body: Dict[str, Any]) -> None:
        pin = str(body.get("pin", "")).strip()
        remove_data = bool(body.get("remove_data", False))
        remove_user = bool(body.get("remove_windows_user", False))

        if DEFAULT_DB_FILE.exists():
            store = Storage(DEFAULT_DB_FILE)
            try:
                stored = store.get_setting(AUTH_SETTING)
                if stored and not verify_pin(pin, stored):
                    self.send_json({"ok": False, "error": "PIN incorreto para confirmar a desinstalacao."}, 400)
                    return
            finally:
                store.close()

        ok, msg = uninstall_system(remove_data=remove_data, remove_windows_user=remove_user)
        self.send_json({"ok": ok, "message": msg})

    def handle_camera_preview(self) -> None:
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

            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buffer).decode("ascii")
            self.send_json({"ok": True, "image": f"data:image/jpeg;base64,{b64}"})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_camera_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            cam = CameraService.get_instance()
            for chunk in cam.generate_mjpeg_stream():
                FaceKidsApiHandler.last_activity_time = time.time()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_camera_enroll_start(self, body: Dict[str, Any]) -> None:
        cid = int(body.get("child_id", 0))
        if cid <= 0:
            if DEFAULT_DB_FILE.exists():
                try:
                    store = Storage(DEFAULT_DB_FILE)
                    people = store.people()
                    store.close()
                    if people:
                        cid = people[0][0]
                except Exception:
                    pass
        if cid <= 0:
            self.send_json({"ok": False, "error": "Crie o perfil da crianca antes de cadastrar a biometria."}, 400)
            return

        cam = CameraService.get_instance()
        res = cam.start_enrollment(cid, DEFAULT_DB_FILE)
        self.send_json(res)

    def handle_camera_enroll_status(self) -> None:
        cam = CameraService.get_instance()
        self.send_json(cam.enrollment_state)

    def handle_child_avatar(self, path: str) -> None:
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
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                # Tenta jpg
                jpg_file = PROGRAMDATA_DIR / "fotos" / f"crianca_{cid}.jpg"
                if jpg_file.exists():
                    data = jpg_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.end_headers()
                    self.wfile.write(data)
                    return
        except Exception:
            pass
        self.send_error(404, "Avatar nao encontrado")

    def serve_asset(self, path: str) -> None:
        if path == "/favicon.ico":
            target = ASSETS_DIR / "facekids.ico"
        else:
            rel = path.lstrip("/assets/")
            target = ASSETS_DIR / rel

        if not target.exists() or not target.is_file():
            self.send_error(404, "Asset nao encontrado")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        try:
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Erro ao servir asset: {e}")

    def serve_static(self, path: str) -> None:
        target_dir = get_ui_dir()
        if path in ("/", "/index.html"):
            target = target_dir / "app.html"
        else:
            rel = path.lstrip("/ui/")
            target = target_dir / rel

        if not target.exists() or not target.is_file():
            target = target_dir / "app.html"

        if not target.exists():
            self.send_error(404, f"Arquivo nao encontrado em {target_dir}")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "text/html"

        try:
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.debug(f"Erro ao servir arquivo estatico: {e}")
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


def run_app_server(port: Optional[int] = None) -> Tuple[ThreadingHTTPServer, int]:
    port = port or find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), FaceKidsApiHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info(f"Servidor FaceKids ativo em http://127.0.0.1:{port}")
    return server, port

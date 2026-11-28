"""SafePCKids - Servidor de Aplicacao Local (Modern UI & API).

Fornece a interface visual moderna (Conceito A: One-Click Wizard + Painel Admin)
e os endpoints REST locais para comunicacao em tempo real entre o frontend e o sistema.
"""
from __future__ import annotations

import base64
import hmac
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import logging
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import threading
import time
import traceback
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlsplit, unquote

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
    INSTALL_MARKER,
    _run_win_cmd,
)
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
from .mdns_responder import DEFAULT_REMOTE_HOSTNAME, MdnsResponder
from .program_policy import (
    discover_installed_programs,
    is_program_allowed_for_child,
    load_programs_config,
    normalize_program_entry,
    save_programs_config,
    set_program_allowed_for_child,
)


logger = logging.getLogger("safepckids.app_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
_DEFAULT_PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SafePCKids"
MAX_POST_BODY_BYTES = 1_048_576
API_SESSION_TOKEN = secrets.token_urlsafe(32)
PIN_MAX_FAILURES = 5
PIN_WINDOW_SECONDS = 60.0
PIN_LOCKOUT_SECONDS = 60.0


def _is_loopback_ip(host: str) -> bool:
    clean = str(host or "").strip().lower()
    if clean.startswith("::ffff:"):
        clean = clean[7:]
    return clean in ("127.0.0.1", "::1", "localhost")


def _is_loopback_origin(url_value: str) -> bool:
    try:
        parsed = urlparse(str(url_value or "").strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    return _is_loopback_ip(parsed.hostname or "")


def _is_remote_allowed_path(path: str) -> bool:
    if path in (
        "/remote",
        "/remote/",
        "/remote.html",
        "/api/remote/status",
        "/api/remote/pause",
        "/api/remote/resume",
        "/favicon.ico",
    ):
        return True
    if path.startswith("/assets/"):
        return True
    if path.startswith("/api/child/") and path.endswith("/avatar"):
        return True
    return False


def _resolve_safe_subpath(base_dir: Path, rel_path: str) -> Optional[Path]:
    """Resolve um subcaminho relativo garantindo que permaneca dentro de base_dir."""
    decoded = unquote(rel_path or "")
    if "\x00" in decoded:
        return None
    normalized = decoded.replace("\\", "/").lstrip("/")
    if not normalized or normalized.startswith("/"):
        return None
    parts = [p for p in normalized.split("/") if p]
    if any(p in (".", "..") or ":" in p for p in parts):
        return None
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / Path(*parts)).resolve()
    try:
        if not candidate.is_relative_to(base_resolved):
            return None
    except AttributeError:
        if str(candidate) != str(base_resolved) and not str(candidate).startswith(str(base_resolved) + os.sep):
            return None
    return candidate


def _fotos_dir() -> Path:
    """Resolve o diretorio de fotos preservando overrides de testes em PROGRAMDATA_DIR ou AVATAR_DIR."""
    if PROGRAMDATA_DIR != _DEFAULT_PROGRAMDATA_DIR:
        return PROGRAMDATA_DIR / "fotos"
    return AVATAR_DIR


def _programs_config_path() -> Optional[Path]:
    """Resolve o arquivo de programas preservando overrides de testes em PROGRAMDATA_DIR."""
    if PROGRAMDATA_DIR != _DEFAULT_PROGRAMDATA_DIR:
        return PROGRAMDATA_DIR / "programas_inicializar.json"
    return None


def get_ui_dir() -> Path:
    """Localiza o diretorio de assets HTML/JS tanto no venv quanto no _MEIPASS."""
    if hasattr(sys, "_MEIPASS"):
        p1 = Path(sys._MEIPASS) / "safepckids" / "ui_assets"
        if p1.exists():
            return p1
        p2 = Path(sys._MEIPASS) / "ui_assets"
        if p2.exists():
            return p2
    return Path(__file__).resolve().parent / "ui_assets"


UI_DIR = get_ui_dir()


class SafePCKidsApiHandler(BaseHTTPRequestHandler):
    session_token = secrets.token_urlsafe(32)
    MAX_REQUEST_BODY = 1024 * 1024
    last_activity_time: float = time.time()
    shutdown_requested: bool = False
    is_installing: bool = False
    install_lock = threading.Lock()
    require_api_token: bool = os.environ.get("SAFEPCKIDS_REQUIRE_API_TOKEN", "1") == "1"
    _pin_failures: Dict[str, list[float]] = {}
    _pin_lockouts: Dict[str, float] = {}
    _pin_rate_lock = threading.Lock()

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _client_ip(self) -> str:
        addr = getattr(self, "client_address", None)
        if isinstance(addr, tuple) and addr:
            return str(addr[0])
        return "127.0.0.1"

    def _is_loopback(self) -> bool:
        return _is_loopback_ip(self._client_ip())

    def _send_cors_headers(self, allow_remote: bool = False) -> None:
        origin = self.headers.get("Origin", "") if hasattr(self, "headers") else ""
        if allow_remote:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
            self.send_header("Vary", "Origin")
        elif origin and _is_loopback_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SafePCKids-Token, X-Session-Token")

    def _is_valid_api_token(self, token: str) -> bool:
        if not token:
            return False
        if hmac.compare_digest(token.encode("utf-8"), str(self.session_token).encode("utf-8")):
            return True
        if hmac.compare_digest(token.encode("utf-8"), API_SESSION_TOKEN.encode("utf-8")):
            return True
        return False

    def _check_request_security(self, path: str) -> bool:
        is_remote_route = _is_remote_allowed_path(path)
        if not self._is_loopback() and not is_remote_route:
            self.send_json({"ok": False, "error": "Acesso restrito ao computador local."}, 403)
            return False

        if not is_remote_route and hasattr(self, "headers"):
            host_hdr = (self.headers.get("Host") or "").strip()
            if host_hdr:
                try:
                    parsed_host = urlsplit("//" + host_hdr)
                    if not _is_loopback_ip(parsed_host.hostname or ""):
                        self.send_json({"ok": False, "error": "Host local nao autorizado."}, 403)
                        return False
                except ValueError:
                    self.send_json({"ok": False, "error": "Host local nao autorizado."}, 403)
                    return False

            origin = self.headers.get("Origin", "")
            referer = self.headers.get("Referer", "")
            fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if origin and not _is_loopback_origin(origin):
                self.send_json({"ok": False, "error": "Origem nao autorizada."}, 403)
                return False
            if referer and not _is_loopback_origin(referer):
                self.send_json({"ok": False, "error": "Referer nao autorizado."}, 403)
                return False
            if fetch_site in ("cross-site", "cross-origin"):
                self.send_json({"ok": False, "error": "Requisicao cross-site bloqueada."}, 403)
                return False

            provided = (
                self.headers.get("X-SafePCKids-Token")
                or self.headers.get("X-Session-Token")
                or ""
            ).strip()
            if not provided and getattr(self, "command", "GET") == "GET":
                provided = parse_qs(urlparse(getattr(self, "path", "")).query).get("session_token", [""])[0].strip()

            if provided and not self._is_valid_api_token(provided):
                self.send_json({"ok": False, "error": "Token de sessao invalido."}, 403)
                return False
            if self.require_api_token and path.startswith("/api/") and path != "/api/heartbeat":
                if not self._is_valid_api_token(provided):
                    self.send_json({"ok": False, "error": "Autenticacao de sessao obrigatoria."}, 403)
                    return False
        return True

    def _check_pin_rate_limit(self) -> bool:
        ip = self._client_ip()
        now = time.monotonic()
        with SafePCKidsApiHandler._pin_rate_lock:
            until = SafePCKidsApiHandler._pin_lockouts.get(ip, 0.0)
            if until > now:
                retry_after = max(1, int(until - now))
                self.send_json(
                    {
                        "ok": False,
                        "error": f"Muitas tentativas de PIN incorretas. Aguarde {retry_after}s.",
                    },
                    429,
                )
                return False
            if ip in SafePCKidsApiHandler._pin_lockouts:
                del SafePCKidsApiHandler._pin_lockouts[ip]
        return True

    def _record_pin_attempt(self, success: bool) -> None:
        ip = self._client_ip()
        now = time.monotonic()
        with SafePCKidsApiHandler._pin_rate_lock:
            if success:
                SafePCKidsApiHandler._pin_failures.pop(ip, None)
                SafePCKidsApiHandler._pin_lockouts.pop(ip, None)
                return
            recent = [
                t for t in SafePCKidsApiHandler._pin_failures.get(ip, [])
                if now - t <= PIN_WINDOW_SECONDS
            ]
            recent.append(now)
            if len(recent) >= PIN_MAX_FAILURES:
                SafePCKidsApiHandler._pin_lockouts[ip] = now + PIN_LOCKOUT_SECONDS
                SafePCKidsApiHandler._pin_failures.pop(ip, None)
            else:
                SafePCKidsApiHandler._pin_failures[ip] = recent

    def send_json(self, data: Any, status: int = 200) -> None:
        SafePCKidsApiHandler.last_activity_time = time.time()
        payload_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            req_path = urlparse(getattr(self, "path", "/")).path
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload_bytes)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Connection", "close")
            self._send_cors_headers(allow_remote=_is_remote_allowed_path(req_path))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(payload_bytes)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.debug(f"Conexao fechada pelo cliente ao enviar JSON: {e}")

    def do_OPTIONS(self) -> None:
        req_path = urlparse(getattr(self, "path", "/")).path
        if not _is_remote_allowed_path(req_path):
            self.send_json({"ok": False, "error": "CORS nao esta habilitado."}, 403)
            return
        self.send_response(204)
        self._send_cors_headers(allow_remote=True)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        SafePCKidsApiHandler.last_activity_time = time.time()
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._check_request_security(path):
                return

            if path in ("/remote", "/remote/", "/remote.html"):
                self.serve_static(path)
            elif path == "/api/remote/status":
                self.handle_remote_status()
            elif path == "/api/status":
                self.handle_status()
            elif path == "/api/diagnostics":
                self.handle_diagnostics()
            elif path == "/api/service/status":
                self.handle_service_status()
            elif path == "/api/network/protection":
                self.handle_network_protection_get()
            elif path == "/api/dashboard":
                self.handle_dashboard()
            elif path == "/api/heartbeat":
                self.send_json({"ok": True, "time": time.time()})
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
            elif path.startswith("/api/children/") and path.endswith("/programs"):
                self.handle_child_programs_get(path)
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
        SafePCKidsApiHandler.last_activity_time = time.time()
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._check_request_security(path):
                return

            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except (ValueError, TypeError):
                self.send_json({"ok": False, "error": "Content-Length invalido."}, 400)
                return

            if length < 0:
                self.send_json({"ok": False, "error": "Content-Length negativo."}, 400)
                return
            if length > MAX_POST_BODY_BYTES:
                self.send_json({"ok": False, "error": "Corpo da requisicao excede o limite permitido."}, 413)
                return

            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                self.send_json({"ok": False, "error": "JSON invalido no corpo da requisicao."}, 400)
                return
            if not isinstance(body, dict):
                self.send_json({"ok": False, "error": "O corpo JSON deve ser um objeto."}, 400)
                return

            if path == "/api/install":
                self.handle_install(body)
            elif path == "/api/install/complete":
                self.handle_install_complete()
            elif path == "/api/auth/verify":
                self.handle_auth_verify(body)
            elif path == "/api/settings/windows-account":
                self.handle_settings_windows_account(body)
            elif path == "/api/network/protection":
                self.handle_network_protection_post(body)
            elif path == "/api/service/restart":
                self.handle_service_restart(body)
            elif path.startswith("/api/children/") and path.endswith("/photos/select"):
                self.handle_child_photo_select(path, body)
            elif path.startswith("/api/children/") and path.endswith("/recapture"):
                self.handle_child_recapture(path, body)
            elif path.startswith("/api/children/") and path.endswith("/programs"):
                self.handle_child_programs_post(path, body)
            elif path == "/api/programs/add":
                self.handle_program_add(body)
            elif path == "/api/programs/delete":
                self.handle_program_delete(body)
            elif path == "/api/programs/detect":
                self.handle_programs_detect()
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
            elif path == "/api/remote/pause":
                self.handle_remote_pause(body)
            elif path == "/api/remote/resume":
                self.handle_remote_resume(body)
            elif path == "/api/shutdown":
                if not SafePCKidsApiHandler.is_installing:
                    SafePCKidsApiHandler.shutdown_requested = True
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
        has_enrollment = False
        enrolled_names = []

        if has_db:
            try:
                store = Storage(DEFAULT_DB_FILE)
                has_pin = bool(store.get_setting(AUTH_SETTING))
                children_count = len(store.people())
                enrolled_ids = {person_id for person_id, _ in store.embeddings()}
                enrolled_names = [person[1] for person in store.people() if person[0] in enrolled_ids]
                has_enrollment = bool(enrolled_names)
                store.close()
            except Exception:
                pass

        health = verify_runtime_health() if sys.platform == "win32" else None
        runtime_ready = health is None or all((
            health["auth_service"]["registered"],
            health["filhos_agent"]["registered"],
            health["boot_auth"]["registered"],
            health["credential_provider"]["registered"],
            health["filhos_user"]["exists"],
        ))
        is_installed = has_db and has_pin and INSTALL_MARKER.exists() and runtime_ready
        u, _ = get_filhos_credentials()
        self.send_json({
            "installed": is_installed,
            "has_pin": has_pin,
            "children_count": children_count,
            "system_ready": INSTALL_MARKER.exists(),
            "face_enrolled": has_enrollment,
            "enrolled_names": enrolled_names,
            "windows_user": u,
            "default_mode": "dashboard" if is_installed else "wizard"
        })

    def handle_diagnostics(self) -> None:
        diag = get_system_diagnostics()
        self.send_json(diag)

    def handle_service_status(self) -> None:
        health = verify_runtime_health()
        try:
            from .network_guard import get_protection_status
            network_protection = get_protection_status()
        except Exception as e:
            network_protection = {"active": False, "error": str(e)}
        self.send_json({"ok": True, "health": health, "network_protection": network_protection})

    def handle_network_protection_get(self) -> None:
        try:
            from .network_guard import get_protection_status
            self.send_json(get_protection_status())
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def handle_network_protection_post(self, data: Dict[str, Any]) -> None:
        try:
            from .network_guard import enable_adguard_family_protection, disable_adguard_family_protection, get_protection_status
            enable = bool(data.get("enable", True))
            if enable:
                ok, msg = enable_adguard_family_protection()
            else:
                ok, msg = disable_adguard_family_protection()
            status = get_protection_status()
            self.send_json({"ok": ok, "message": msg, "protection": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def handle_service_restart(self, data: Optional[Dict[str, Any]] = None) -> None:
        service_name = "SafePCKidsAuthService"
        if data and data.get("service"):
            cand = str(data.get("service")).strip()
            if cand in ("SafePCKidsAuthService", "SafePCKidsFilhosAgent"):
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
        if not SafePCKidsApiHandler.install_lock.acquire(blocking=False):
            self.send_json({"ok": False, "error": "Uma instalacao ja esta em andamento."}, 409)
            return
        SafePCKidsApiHandler.is_installing = True
        SafePCKidsApiHandler.last_activity_time = time.time()
        try:
            master_pin = str(data.get("pin", "")).strip()
            raw_child = data.get("child_name")
            first_child = str(raw_child).strip() if raw_child is not None else ""
            if not first_child or first_child.lower() in ("none", "null"):
                first_child = None
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
                filhos_username=filhos_user,
                defer_services=False,
            )
            self.send_json({
                "ok": ok,
                "status": "success" if ok else "error",
                "message": msg
            })
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            logger.error(f"Erro em handle_install: {traceback.format_exc()}")
            self.send_json({"ok": False, "error": f"Erro durante a instalacao: {exc}"}, 500)
        finally:
            SafePCKidsApiHandler.is_installing = False
            SafePCKidsApiHandler.last_activity_time = time.time()
            SafePCKidsApiHandler.install_lock.release()

    def handle_install_complete(self) -> None:
        if not SafePCKidsApiHandler.install_lock.acquire(blocking=False):
            self.send_json({"ok": False, "error": "Uma instalacao ja esta em andamento."}, 409)
            return
        SafePCKidsApiHandler.is_installing = True
        try:
            if not DEFAULT_DB_FILE.exists():
                self.send_json({"ok": False, "error": "Cadastre a crianca antes de concluir."}, 400)
                return
            store = Storage(DEFAULT_DB_FILE)
            try:
                if not store.get_setting(AUTH_SETTING):
                    self.send_json({"ok": False, "error": "Configure o PIN antes de concluir."}, 400)
                    return
            finally:
                store.close()
            ok, message = setup_system(master_pin="")
            self.send_json({"ok": ok, "status": "success" if ok else "error", "message": message,
                            "error": None if ok else message})
        except Exception as exc:
            logger.error("Erro ao concluir instalacao: %s", exc)
            self.send_json({"ok": False, "error": str(exc)}, 500)
        finally:
            SafePCKidsApiHandler.is_installing = False
            SafePCKidsApiHandler.last_activity_time = time.time()
            SafePCKidsApiHandler.install_lock.release()

    def handle_auth_verify(self, data: Dict[str, Any]) -> None:
        if not self._check_pin_rate_limit():
            return
        pin = str(data.get("pin", "")).strip()
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"ok": False, "error": "Banco de dados ainda nao inicializado."}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            stored = store.get_setting(AUTH_SETTING)
            if not stored:
                self._record_pin_attempt(True)
                self.send_json({"ok": True, "message": "Sem PIN configurado."})
                return
            valid = verify_pin(pin, stored)
            self._record_pin_attempt(valid)
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
            enabled_programs = []
            try:
                programs_cfg = load_programs_config(_programs_config_path())
                enabled_programs = [p for p in programs_cfg.get("programs", []) if p.get("enabled", True)]
            except Exception as e:
                logger.debug(f"Falha ao ler politica de programas para dashboard: {e}")

            for p in people:
                cid = p[0]
                name = p[1]
                limit_sec = p[2]
                used_sec = int(store.used(cid))
                bonus_sec = int(store.bonus(cid))
                remaining_sec = int(store.remaining(cid))

                total_used_today += used_sec
                total_limit_today += limit_sec
                allowed_count = sum(1 for prog in enabled_programs if is_program_allowed_for_child(prog, cid))

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
                    "percent_remaining": round((remaining_sec / max(1, limit_sec + bonus_sec)) * 100),
                    "programs_allowed_count": allowed_count,
                    "programs_total_count": len(enabled_programs),
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

        if cid <= 0 or idx <= 0:
            self.send_error(400, "Parametros invalidos")
            return

        fotos_dir = _fotos_dir()
        sample_p = fotos_dir / f"amostras_{cid}" / f"amostra_{idx}.jpg"
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

        # Fallback para profile_photos no SQLite (estritamente filtrado por person_id=cid)
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

        # Fallback para crianca_cid.jpg apenas na amostra 1
        if idx == 1:
            fallback_p = fotos_dir / f"crianca_{cid}.jpg"
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

        if cid <= 0 or idx <= 0:
            self.send_json({"ok": False, "error": "Parametros invalidos"}, 400)
            return

        sample_p = _fotos_dir() / f"amostras_{cid}" / f"amostra_{idx}.jpg"
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

    @staticmethod
    def _parse_child_id_from_path(path: str, expected_suffix: str) -> Optional[int]:
        parts = [p for p in path.split("/") if p]
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "children" or parts[3] != expected_suffix:
            return None
        try:
            cid = int(parts[2])
        except (ValueError, TypeError):
            return None
        return cid if cid > 0 else None

    @staticmethod
    def _serialize_programs_for_child(cfg: Dict[str, Any], cid: int) -> list[Dict[str, Any]]:
        items = []
        for idx, prog in enumerate(cfg.get("programs", [])):
            items.append({
                "index": idx,
                "name": prog.get("name", "Programa"),
                "executable": prog.get("executable", ""),
                "arguments": prog.get("arguments", ""),
                "enabled": bool(prog.get("enabled", True)),
                "allowed": is_program_allowed_for_child(prog, cid),
            })
        return items

    def handle_child_programs_get(self, path: str) -> None:
        cid = self._parse_child_id_from_path(path, "programs")
        if cid is None:
            self.send_json({"ok": False, "error": "ID da crianca invalido."}, 400)
            return

        cfg = load_programs_config(_programs_config_path())
        self.send_json({
            "ok": True,
            "child_id": cid,
            "policy_enabled": bool(cfg.get("enabled", True)),
            "programs": self._serialize_programs_for_child(cfg, cid),
        })

    def handle_child_programs_post(self, path: str, data: Dict[str, Any]) -> None:
        cid = self._parse_child_id_from_path(path, "programs")
        if cid is None:
            self.send_json({"ok": False, "error": "ID da crianca invalido."}, 400)
            return

        cfg_path = _programs_config_path()
        cfg = load_programs_config(cfg_path)
        programs = cfg.get("programs", [])

        if "policy_enabled" in data:
            cfg["enabled"] = bool(data.get("policy_enabled"))

        permissions = data.get("permissions")
        if isinstance(permissions, list):
            for entry in permissions:
                if not isinstance(entry, dict):
                    continue
                try:
                    idx = int(entry.get("index", -1))
                except (ValueError, TypeError):
                    continue
                if 0 <= idx < len(programs):
                    set_program_allowed_for_child(programs[idx], cid, bool(entry.get("allowed", True)))
        elif "index" in data and "allowed" in data:
            try:
                idx = int(data.get("index", -1))
            except (ValueError, TypeError):
                idx = -1
            if not (0 <= idx < len(programs)):
                self.send_json({"ok": False, "error": "Indice de programa invalido."}, 400)
                return
            set_program_allowed_for_child(programs[idx], cid, bool(data.get("allowed", True)))
        else:
            self.send_json({"ok": False, "error": "Informe 'permissions' ou 'index' e 'allowed'."}, 400)
            return

        if not save_programs_config(cfg, cfg_path):
            self.send_json({"ok": False, "error": "Falha ao salvar permissoes de programas."}, 500)
            return

        self.send_json({
            "ok": True,
            "message": "Permissoes de programas atualizadas com sucesso.",
            "programs": self._serialize_programs_for_child(cfg, cid),
        })

    def handle_program_add(self, data: Dict[str, Any]) -> None:
        name = str(data.get("name", "")).strip()
        executable = str(data.get("executable", "")).strip().strip("\"'")
        arguments = str(data.get("arguments", "")).strip()

        if not name:
            self.send_json({"ok": False, "error": "Informe o nome do programa."}, 400)
            return
        if not executable:
            self.send_json({"ok": False, "error": "Informe o executavel ou caminho do programa."}, 400)
            return

        cfg_path = _programs_config_path()
        cfg = load_programs_config(cfg_path)
        programs = cfg.setdefault("programs", [])

        exe_name = Path(executable).name.lower()
        for existing in programs:
            if existing.get("name", "").strip().lower() == name.lower():
                self.send_json({"ok": False, "error": f"O programa '{name}' ja esta cadastrado."}, 409)
                return
            ex_exe = existing.get("executable", "").strip()
            if ex_exe and Path(ex_exe).name.lower() == exe_name:
                self.send_json({"ok": False, "error": f"O executavel '{exe_name}' ja esta cadastrado."}, 409)
                return

        entry = normalize_program_entry({
            "name": name,
            "executable": executable,
            "arguments": arguments,
            "enabled": True,
            "blocked_child_ids": [],
        })
        if data.get("child_id") is not None and data.get("allowed") is False:
            set_program_allowed_for_child(entry, data.get("child_id"), False)

        programs.append(entry)
        if not save_programs_config(cfg, cfg_path):
            self.send_json({"ok": False, "error": "Falha ao salvar programa no catalogo."}, 500)
            return

        self.send_json({"ok": True, "message": f"Programa '{name}' adicionado.", "program": entry})

    def handle_program_delete(self, data: Dict[str, Any]) -> None:
        cfg_path = _programs_config_path()
        cfg = load_programs_config(cfg_path)
        programs = cfg.get("programs", [])

        removed = None
        if "index" in data and data.get("index") is not None:
            try:
                idx = int(data.get("index"))
            except (ValueError, TypeError):
                self.send_json({"ok": False, "error": "Indice de programa invalido."}, 400)
                return
            if not (0 <= idx < len(programs)):
                self.send_json({"ok": False, "error": "Programa nao encontrado."}, 404)
                return
            removed = programs.pop(idx)
        elif data.get("name"):
            target = str(data.get("name", "")).strip().lower()
            for idx, p in enumerate(programs):
                if p.get("name", "").strip().lower() == target:
                    removed = programs.pop(idx)
                    break
            if removed is None:
                self.send_json({"ok": False, "error": "Programa nao encontrado."}, 404)
                return
        else:
            self.send_json({"ok": False, "error": "Informe o indice ou nome do programa."}, 400)
            return

        if not save_programs_config(cfg, cfg_path):
            self.send_json({"ok": False, "error": "Falha ao remover programa do catalogo."}, 500)
            return

        self.send_json({"ok": True, "message": f"Programa '{removed.get('name', '')}' removido."})

    def handle_programs_detect(self) -> None:
        cfg_path = _programs_config_path()
        cfg = load_programs_config(cfg_path)
        programs = cfg.setdefault("programs", [])

        existing_names = {p.get("name", "").strip().lower() for p in programs}
        existing_exes = {
            Path(p.get("executable", "")).name.lower()
            for p in programs
            if p.get("executable", "").strip()
        }

        added_names = []
        for item in discover_installed_programs():
            p_name = item.get("name", "").strip().lower()
            e_name = Path(item.get("executable", "")).name.lower()
            if p_name and p_name not in existing_names and e_name not in existing_exes:
                programs.append(normalize_program_entry(item))
                existing_names.add(p_name)
                if e_name:
                    existing_exes.add(e_name)
                added_names.append(item["name"])

        if added_names and not save_programs_config(cfg, cfg_path):
            self.send_json({"ok": False, "error": "Falha ao salvar programas detectados."}, 500)
            return

        self.send_json({
            "ok": True,
            "added_count": len(added_names),
            "added_names": added_names,
            "total": len(programs),
        })

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
        try:
            hours = float(data.get("daily_limit_hours", 2.0))
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "Limite diario invalido."}, 400)
            return
        if not name:
            self.send_json({"ok": False, "error": "Nome obrigatorio"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            new_id = store.add_person(name, int(hours * 60))
            if isinstance(new_id, int) and new_id > 0:
                remove_child_avatar_files(new_id)
            self.send_json({"ok": True, "id": new_id, "name": name})
        except sqlite3.IntegrityError:
            self.send_json({"ok": False, "error": f"Ja existe um perfil cadastrado com o nome '{name}'."}, 400)
        except ValueError as e:
            self.send_json({"ok": False, "error": str(e)}, 400)
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
            store.delete_person(cid)
            remove_child_avatar_files(cid)
            self.send_json({"ok": True, "message": "Perfil infantil removido com sucesso."})
        except KeyError:
            self.send_json({"ok": False, "error": f"Perfil #{cid} nao encontrado."}, 404)
        except Exception as e:
            logger.error(f"Erro ao remover perfil #{cid}: {e}")
            self.send_json({"ok": False, "error": f"Erro ao remover perfil: {e}"}, 500)
        finally:
            store.close()

    def handle_uninstall(self, body: Dict[str, Any]) -> None:
        if not self._check_pin_rate_limit():
            return
        pin = str(body.get("pin", "")).strip()
        remove_data = bool(body.get("remove_data", False))
        remove_user = bool(body.get("remove_windows_user", False))

        if DEFAULT_DB_FILE.exists():
            store = Storage(DEFAULT_DB_FILE)
            try:
                stored = store.get_setting(AUTH_SETTING)
                if stored and not verify_pin(pin, stored):
                    self._record_pin_attempt(False)
                    self.send_json({"ok": False, "error": "PIN incorreto para confirmar a desinstalacao."}, 400)
                    return
            finally:
                store.close()

        self._record_pin_attempt(True)
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
        self._send_cors_headers(allow_remote=False)
        self.end_headers()
        try:
            cam = CameraService.get_instance()
            for chunk in cam.generate_mjpeg_stream():
                SafePCKidsApiHandler.last_activity_time = time.time()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_camera_enroll_start(self, body: Dict[str, Any]) -> None:
        try:
            cid = int(body.get("child_id") or 0)
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "ID da crianca invalido."}, 400)
            return

        people = None
        if DEFAULT_DB_FILE.exists():
            try:
                store = Storage(DEFAULT_DB_FILE)
                people = store.people()
                store.close()
            except Exception:
                people = None

        if cid <= 0:
            target_name = str(body.get("child_name") or "").strip().casefold()
            if target_name and isinstance(people, list):
                matches = [person for person in people if person[1].casefold() == target_name]
                if matches:
                    cid = int(matches[0][0])

        if cid <= 0:
            self.send_json({"ok": False, "error": "Crie o perfil da crianca antes de cadastrar a biometria."}, 400)
            return

        if isinstance(people, list) and not any(person[0] == cid for person in people):
            self.send_json({"ok": False, "error": f"Perfil #{cid} nao encontrado."}, 404)
            return

        cam = CameraService.get_instance()
        res = cam.start_enrollment(cid, DEFAULT_DB_FILE)
        self.send_json(res)

    def handle_camera_enroll_status(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        req_cid: Optional[int] = None
        if "child_id" in qs and qs["child_id"]:
            try:
                req_cid = int(qs["child_id"][0])
            except (TypeError, ValueError):
                req_cid = None
        cam = CameraService.get_instance()
        if hasattr(cam, "get_enrollment_status"):
            self.send_json(cam.get_enrollment_status(child_id=req_cid))
        else:
            self.send_json(cam.enrollment_state)

    def handle_child_avatar(self, path: str) -> None:
        try:
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "child":
                cid = int(parts[2])
                if cid <= 0:
                    self.send_error(400, "ID invalido")
                    return
                fotos_dir = _fotos_dir()
                avatar_file = fotos_dir / f"crianca_{cid}_avatar.png"
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
                jpg_file = fotos_dir / f"crianca_{cid}.jpg"
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
            target = (ASSETS_DIR / "safepckids.ico").resolve()
        else:
            rel = path[len("/assets/"):] if path.startswith("/assets/") else path
            target = _resolve_safe_subpath(ASSETS_DIR, rel)
            if target is None:
                self.send_error(404, "Asset nao encontrado")
                return

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
        elif path in ("/remote", "/remote/", "/remote.html"):
            target = target_dir / "remote.html"
        else:
            rel = path[len("/ui/"):] if path.startswith("/ui/") else path
            target = _resolve_safe_subpath(target_dir, rel)
            if target is None:
                self.send_error(404, "Arquivo nao encontrado")
                return

        if not target.exists() or not target.is_file():
            target = target_dir / "app.html"

        if not target.exists():
            self.send_error(404, f"Arquivo nao encontrado em {target_dir}")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "text/html"

        try:
            content = target.read_bytes()
            if target.name == "app.html" and self._is_loopback():
                token_script = (
                    f"<script>window.__SAFEPCKIDS_TOKEN__={json.dumps(self.session_token)};</script>"
                ).encode("utf-8")
                content = content.replace(b"<head>", b"<head>" + token_script, 1)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.debug(f"Erro ao servir arquivo estatico: {e}")
            self.send_error(500, "Erro ao servir arquivo")

    def handle_remote_status(self) -> None:
        has_db = DEFAULT_DB_FILE.exists()
        is_paused = False
        pause_reason = ""
        pause_remaining = 0
        children_list = []
        child_info = None
        has_pin = False

        active_child_id = None
        try:
            last_unlock_file = unlock_metadata_path()
            if last_unlock_file.exists():
                meta = json.loads(last_unlock_file.read_text(encoding="utf-8"))
                active_child_id = meta.get("child_id")
        except Exception:
            pass

        if has_db:
            try:
                store = Storage(DEFAULT_DB_FILE)
                has_pin = bool(store.get_parent_pin())
                is_paused, pause_reason, pause_remaining = store.get_remote_pause_state()
                people = store.people()
                if people:
                    from datetime import date
                    today = date.today().isoformat()
                    fotos_dir = _fotos_dir()

                    valid_ids = [p[0] for p in people]
                    if active_child_id not in valid_ids:
                        active_child_id = valid_ids[0]

                    for c_id, c_name, c_quota in people:
                        rem = store.remaining(c_id, today)
                        avatar_file = fotos_dir / f"crianca_{c_id}_avatar.png"
                        item = {
                            "id": c_id,
                            "name": c_name,
                            "daily_limit_minutes": int(c_quota // 60),
                            "remaining_seconds": int(rem),
                            "remaining_minutes": int(rem // 60),
                            "has_avatar": avatar_file.exists(),
                            "avatar_url": f"/api/child/{c_id}/avatar" if avatar_file.exists() else None,
                            "is_active": (c_id == active_child_id),
                        }
                        children_list.append(item)
                        if c_id == active_child_id:
                            child_info = item

                    if not child_info and children_list:
                        child_info = children_list[0]
                store.close()
            except Exception as e:
                logger.debug(f"Erro ao ler status remoto do banco: {e}")

        session_active = False
        try:
            from .session import current_session_state, SessionState
            session_active = (current_session_state() is SessionState.ACTIVE)
        except Exception:
            pass

        self.send_json({
            "ok": True,
            "is_paused": is_paused,
            "pause_reason": pause_reason,
            "pause_remaining_seconds": pause_remaining,
            "child": child_info,
            "children": children_list,
            "active_child_id": active_child_id,
            "session_active": session_active,
            "has_pin": has_pin,
            "local_ip": get_local_ip(),
            "remote_hostname": DEFAULT_REMOTE_HOSTNAME,
            "server_time": time.time(),
        })

    def handle_remote_pause(self, data: Dict[str, Any]) -> None:
        if not self._check_pin_rate_limit():
            return
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"ok": False, "error": "Sistema ainda nao configurado"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            has_pin = bool(store.get_parent_pin())
            pin = str(data.get("pin", "")).strip()
            if has_pin and not store.verify_parent_pin(pin):
                self._record_pin_attempt(False)
                self.send_json({"ok": False, "error": "PIN incorreto"}, 401)
                return
            self._record_pin_attempt(True)

            dur_min = data.get("duration_minutes")
            if dur_min is None or int(dur_min) <= 0:
                duration_seconds = 0
            else:
                duration_seconds = int(dur_min) * 60

            reason = str(data.get("reason", "Pausa solicitada pelos pais")).strip()
            pause_data = store.set_remote_pause(duration_seconds, reason)

            if sys.platform == "win32":
                try:
                    from .locker import lock_current_session
                    threading.Thread(target=lock_current_session, daemon=True).start()
                except Exception as e:
                    logger.debug(f"Aviso ao solicitar bloqueio imediato: {e}")

            self.send_json({"ok": True, "message": "Pausa ativada com sucesso", "pause": pause_data})
        finally:
            store.close()

    def handle_remote_resume(self, data: Dict[str, Any]) -> None:
        if not self._check_pin_rate_limit():
            return
        if not DEFAULT_DB_FILE.exists():
            self.send_json({"ok": False, "error": "Sistema ainda nao configurado"}, 400)
            return

        store = Storage(DEFAULT_DB_FILE)
        try:
            has_pin = bool(store.get_parent_pin())
            pin = str(data.get("pin", "")).strip()
            if has_pin and not store.verify_parent_pin(pin):
                self._record_pin_attempt(False)
                self.send_json({"ok": False, "error": "PIN incorreto"}, 401)
                return
            self._record_pin_attempt(True)

            store.clear_remote_pause()
            self.send_json({"ok": True, "message": "Pausa cancelada. Computador liberado."})
        finally:
            store.close()


def get_local_ip() -> str:
    """Detecta o IP local da maquina na rede Wi-Fi / Ethernet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
    return start


def run_app_server(port: Optional[int] = None, host: str = "0.0.0.0") -> Tuple[ThreadingHTTPServer, int]:
    port = port or find_free_port()
    handler = type(
        "SafePCKidsSessionHandler",
        (SafePCKidsApiHandler,),
        {"session_token": secrets.token_urlsafe(32)},
    )
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        host = "127.0.0.1"
    if host == "0.0.0.0":
        mdns = MdnsResponder(DEFAULT_REMOTE_HOSTNAME, ip_provider=get_local_ip)
        mdns.start()
        setattr(server, "_mdns_responder", mdns)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info(f"Servidor SafePCKids ativo em http://{host}:{port}")
    return server, port


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SafePCKids Remote Server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    server, active_p = run_app_server(port=args.port, host=args.host)
    local_ip = get_local_ip()
    print(f"[OK] Servidor SafePCKids ativo em http://{args.host}:{active_p}/")
    print(f"[CELULAR] Acesse no smartphone: http://{local_ip}:{active_p}/remote")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


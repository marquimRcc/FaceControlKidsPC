"""FaceControlKidsPC - Servico de Autenticacao Facial via Named Pipe.

Escuta conexoes locais do Credential Provider (LogonUI) em:
\\\\.\\pipe\\FaceKidsAuthPipe

Quando o LogonUI consulta o servico:
1. Abre a webcam brevemente em segundo plano;
2. Localiza e identifica o rosto presente usando YuNet + SFace;
3. Consulta o saldo de quotas do SQLite local;
4. Se o filho for reconhecido e possuir saldo > 0:
   Retorna autorizacao com usuario 'Filhos' e senha '1';
5. Salva a foto/avatar do filho reconhecido e dispara a tela de boas-vindas.
"""
from __future__ import annotations

import ctypes
import argparse
from ctypes import wintypes
from datetime import date
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from .children_pilot import child_pilot_database
from .recognition import Recognizer
from .storage import Storage
from .avatar_utils import save_child_photo
from .windows_pipe_api import configure_kernel32
from .pipe_protocol import decode_pipe_command
from .boot_auth import write_status
from .agent_watchdog import AgentWatchdog, AgentWatchdogThread

from .vm_lab_paths import vm_lab_root


def authentication_log_dir() -> Path:
    """Put VM diagnostics alongside the opted-in isolated test data."""
    root = vm_lab_root()
    if root is not None:
        return root / "appdata"
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "FaceKids"
    return Path(tempfile.gettempdir()) / "FaceKids"


log_dir = authentication_log_dir()


def unlock_metadata_path() -> Path:
    """Respect the VM opt-in even if the environment changes after import."""
    root = vm_lab_root()
    if root is not None:
        return root / "appdata" / "last_unlock.json"
    if sys.platform == "win32":
        return Path("C:/ProgramData/FaceKids/last_unlock.json")
    return log_dir / "last_unlock.json"

try:
    log_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    log_dir = Path(tempfile.gettempdir()) / "FaceKids"
    log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / "auth_service.log"

try:
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="[%(asctime)s] [FaceKidsService] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
except OSError:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [FaceKidsService] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
logger = logging.getLogger("FaceKidsAuthService")

AUTH_MUTEX_NAME = os.environ.get("FACEKIDS_AUTH_MUTEX", "Global\\FaceKidsAuthServiceMutex")
PIPE_NAME = os.environ.get("FACEKIDS_AUTH_PIPE", r"\\.\pipe\FaceKidsAuthPipe")
BUFFER_SIZE = 4096

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

def auth_pipe_mode_flags() -> int:
    return PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS


# Marcador de versao do contrato IPC. Isto NAO e segredo nem mecanismo
# criptografico; a confianca local continua dependendo das ACLs do Named Pipe.
IPC_PROTOCOL_MARKER = "FACEKIDS_IPC_V1"

# Security descriptor SDDL: Full control for SYSTEM (SY) and Admins (BA); Read/Write for Interactive Users (IU)
SDDL_PERMISSIVE = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)"


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD if hasattr(wintypes, "DWORD") else ctypes.c_ulong),
        ("lpSecurityDescriptor", wintypes.LPVOID if hasattr(wintypes, "LPVOID") else ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL if hasattr(wintypes, "BOOL") else ctypes.c_int),
    ]


def create_security_attributes() -> SECURITY_ATTRIBUTES:
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(sa)
    sa.bInheritHandle = False
    advapi32 = getattr(getattr(ctypes, "windll", None), "advapi32", None)
    if advapi32 is not None:
        convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
        if isinstance(convert, ctypes._CFuncPtr):
            convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                ctypes.POINTER(wintypes.LPVOID), wintypes.LPDWORD]
            convert.restype = wintypes.BOOL
        p_sd = wintypes.LPVOID()
        if advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            SDDL_PERMISSIVE, 1, ctypes.byref(p_sd), None
        ):
            sa.lpSecurityDescriptor = p_sd
        else:
            logger.error("Falha ao criar SDDL para o pipe; recusando fallback.")
            raise RuntimeError("Named Pipe SDDL conversion failed")
    else:
        if sys.platform == "win32":
            raise RuntimeError("Named Pipe security API unavailable")
        sa.lpSecurityDescriptor = None
    return sa


class FaceAuthenticator:
    def __init__(
        self,
        models_dir: Path,
        db_path: Path,
        recognizer: Optional[Recognizer] = None,
    ):
        self.models_dir = Path(models_dir)
        self.db_path = Path(db_path)
        self._recognizer = recognizer

    @property
    def recognizer(self) -> Recognizer:
        if self._recognizer is None:
            self._recognizer = Recognizer(self.models_dir)
        return self._recognizer

    def evaluate(self, camera_index: int = 0, timeout_seconds: float = 3.0,
                 camera_backend: str = "dshow", publish_unlock_event: bool = True) -> Tuple[str, dict]:
        """Tenta reconhecer um filho e verificar sua quota restante."""
        if not self.db_path.exists():
            return "ERROR", {"message": "Banco de dados nao encontrado"}

        store = Storage(self.db_path)
        try:
            today = date.today().isoformat()
            references = list(store.embeddings())
            if not references:
                return "DENY_NO_ENROLLMENT", {"message": "Nenhum rosto cadastrado"}

            try:
                rec = self.recognizer
            except Exception as e:
                logger.error("Falha ao inicializar Recognizer: %s", e)
                return "ERROR", {"message": f"Modelos faciais indisponiveis: {e}"}

            # Mapeamento ID -> Nome
            names = {pid: name for pid, name, _ in store.people()}

            backend = camera_backend_id(camera_backend)
            cap = cv2.VideoCapture(camera_index, backend)
            if not cap.isOpened():
                cap.release()
                return "ERROR_CAMERA", {"message": "Nao foi possivel abrir a webcam"}

            deadline = time.monotonic() + timeout_seconds
            best_candidate = None
            consecutive_matches = 0
            best_frame = None
            best_face_box = None
            best_detected_ids: list[int] = []
            best_face_count: int = 0

            try:
                while time.monotonic() < deadline:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        time.sleep(0.05)
                        continue

                    faces = rec.faces(frame)
                    if len(faces) >= 1:
                        # Ordena os rostos detectados do maior (mais proximo) para o menor
                        sorted_faces = sorted(faces, key=lambda f: float(f[2]) * float(f[3]), reverse=True)
                        current_frame_detected_ids = []
                        candidate_face_box = None
                        for f_box in sorted_faces[:3]:
                            feat = rec.features(frame, f_box)
                            cid, sc = rec.identify(feat, references, threshold=0.38, min_margin=0.04)
                            if cid is not None and cid not in current_frame_detected_ids:
                                current_frame_detected_ids.append(cid)
                                if candidate_face_box is None:
                                    candidate_face_box = f_box

                        largest_face = sorted_faces[0]
                        candidate_id = current_frame_detected_ids[0] if current_frame_detected_ids else None

                        if candidate_id is not None:
                            logger.info(
                                "Rosto candidato detectado: %s (rostos=%d, detectados=%s)",
                                names.get(candidate_id, candidate_id),
                                len(faces),
                                current_frame_detected_ids,
                            )
                            if candidate_id == best_candidate:
                                consecutive_matches += 1
                                best_frame = frame.copy()
                                best_face_box = candidate_face_box
                                best_detected_ids = list(current_frame_detected_ids)
                                best_face_count = len(faces)
                                if consecutive_matches >= 2:
                                    break
                            else:
                                best_candidate = candidate_id
                                consecutive_matches = 1
                                best_frame = frame.copy()
                                best_face_box = candidate_face_box
                                best_detected_ids = list(current_frame_detected_ids)
                                best_face_count = len(faces)
                        else:
                            best_candidate = None
                            consecutive_matches = 0
                    time.sleep(0.04)
            finally:
                cap.release()

            if best_candidate is None or consecutive_matches < 2:
                return "DENY_UNKNOWN", {"message": "Rosto desconhecido ou instavel"}

            child_name = names.get(best_candidate, f"Crianca {best_candidate}")

            # 1. Verificar horario permitido (toque de recolher)
            is_curfew, curfew_msg = store.is_curfew_active()
            if is_curfew:
                logger.info("Filho identificado (%s), mas bloqueado pelo horario permitido: %s", child_name, curfew_msg)
                return "DENY_CURFEW", {
                    "child_id": best_candidate,
                    "child_name": child_name,
                    "remaining": 0,
                    "message": curfew_msg,
                    "detected_ids": best_detected_ids or [best_candidate],
                    "face_count": best_face_count or 1,
                }

            # 2. Verificar quota diaria restante
            remaining_seconds = int(store.remaining(best_candidate, today))

            if remaining_seconds <= 0:
                logger.info("Filho identificado (%s), mas quota esgotada (0s).", child_name)
                return "DENY_QUOTA", {
                    "child_id": best_candidate,
                    "child_name": child_name,
                    "remaining": 0,
                    "message": "Tempo diario esgotado",
                    "detected_ids": best_detected_ids or ([best_candidate] if best_candidate else []),
                    "face_count": best_face_count or 1,
                }

            logger.info("Filho autorizado: %s (Saldo: %ds)", child_name, remaining_seconds)

            # Salva avatar apenas se a crianca ainda nao tiver foto oficial/cadastrada
            if publish_unlock_event and best_frame is not None:
                try:
                    from .avatar_utils import get_child_avatar_path
                    if not get_child_avatar_path(best_candidate):
                        save_child_photo(best_candidate, best_frame, best_face_box)
                    else:
                        logger.debug("Avatar oficial ja existente para filho %d; foto preservada.", best_candidate)
                except Exception as e:
                    logger.warning("Falha ao salvar avatar do filho: %s", e)

            # Grava ultimo evento de desbloqueio para a tela de boas-vindas
            if publish_unlock_event:
                try:
                    unlock_data = {
                        "child_id": best_candidate,
                        "child_name": child_name,
                        "remaining_seconds": remaining_seconds,
                        "timestamp": time.time(),
                    }
                    unlock_path = unlock_metadata_path()
                    unlock_path.parent.mkdir(parents=True, exist_ok=True)
                    unlock_path.write_text(
                        json.dumps(unlock_data, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception as e:
                    logger.warning("Falha ao salvar last_unlock.json: %s", e)

            response = {
                "child_id": best_candidate,
                "child_name": child_name,
                "remaining": remaining_seconds,
                "user": "Filhos",
                "detected_ids": best_detected_ids or [best_candidate],
                "face_count": best_face_count or 1,
            }
            # Only the legacy unlock command needs the credential field.
            # Session observations must never carry a password or touch UI files.
            if publish_unlock_event:
                response["password"] = "1"
            return "ALLOW", response
        finally:
            store.close()


def camera_backend_id(name: str) -> int:
    if sys.platform != "win32":
        return cv2.CAP_ANY
    return {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}[name]


def probe_camera_access(camera_index: int = 0, camera_backend: str = "dshow") -> bool:
    """Verifica se o contexto atual de execucao tem permissao e capacidade de abrir a webcam."""
    cap = None
    try:
        backend = camera_backend_id(camera_backend)
        cap = cv2.VideoCapture(camera_index, backend)
        if not cap.isOpened():
            return False
        # Some USB webcams return empty warm-up samples at boot. The external
        # supervisor enforces a hard process deadline if a driver call hangs.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            ret, frame = cap.read()
            if ret and frame is not None:
                return True
            time.sleep(0.05)
        return False
    except Exception as e:
        logger.warning("Falha na sondagem da webcam: %s", e)
        return False
    finally:
        if cap is not None:
            cap.release()


def is_session_zero_or_system() -> bool:
    """Detecta se o processo esta executando como SYSTEM ou na Sessao 0 (sem desktop interativo)."""
    if sys.platform != "win32":
        return False
    user = os.environ.get("USERNAME", "").upper()
    if user in ("SYSTEM", ""):
        return True
    try:
        kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
        if kernel32 and hasattr(kernel32, "ProcessIdToSessionId"):
            session_id = wintypes.DWORD()
            if kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session_id)):
                return session_id.value == 0
    except Exception:
        pass
    return False


def run_pipe_server(models_dir: Optional[Path] = None, db_path: Optional[Path] = None,
                    once: bool = False, camera_backend: str = "dshow",
                    status_file: Optional[Path] = None) -> int:
    root = Path(__file__).resolve().parent.parent
    models = models_dir or (root / "models")
    db = db_path or child_pilot_database()

    logger.info("Iniciando FaceKids Auth Service...")
    logger.info("Modelos: %s", models)
    logger.info("Banco: %s", db)

    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is None:
        logger.error("Servico Named Pipe requer ambiente Windows.")
        return 1
    configure_kernel32(kernel32)

    def report(phase: str):
        if status_file is not None:
            session_id = wintypes.DWORD()
            kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id))
            evidence = dict(phase=phase, pid=os.getpid(), session_id=session_id.value,
                            backend=camera_backend)
            if phase in ("camera_ready", "allow"):
                # Diagnostic only: no usernames, photos, child IDs or passwords.
                from .windows_session_diagnostic import enumerate_local_sessions
                try:
                    evidence["logged_on_users"] = sum(
                        bool(row.username) for row in enumerate_local_sessions())
                except (OSError, RuntimeError):
                    evidence["logged_on_users"] = None
                evidence["updated_at"] = time.time()
                with (log_dir / "boot_events.jsonl").open("a", encoding="utf-8") as events:
                    events.write(json.dumps(evidence) + "\n")
            write_status(status_file, **evidence)

    sa = create_security_attributes()
    h_mutex = kernel32.CreateMutexW(
        ctypes.byref(sa) if (sa and sa.lpSecurityDescriptor) else None,
        False,
        AUTH_MUTEX_NAME,
    )
    if not h_mutex:
        err = kernel32.GetLastError()
        if err == 5:  # ERROR_ACCESS_DENIED: Outra instancia possui o mutex com DACL restrita ou SYSTEM
            report("duplicate")
            logger.info("Outra instancia do autenticador ja esta em execucao (mutex existente, erro 5).")
            if sa is not None and sa.lpSecurityDescriptor:
                kernel32.LocalFree(sa.lpSecurityDescriptor)
            return 20
        logger.error("Nao foi possivel abrir mutex (erro %d).", err)
        if sa is not None and sa.lpSecurityDescriptor:
            kernel32.LocalFree(sa.lpSecurityDescriptor)
        return 1
    # Keep the existence lock for exactly this instance's lifetime. Check BEFORE
    # touching the webcam, so retries cannot steal an interactive worker's camera.
    try:
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            report("duplicate")
            logger.info("Outra instancia do autenticador ja esta em execucao.")
            return 20
        report("camera_probe")
        if is_session_zero_or_system():
            if not probe_camera_access(0, camera_backend):
                report("camera_unavailable")
                logger.warning("Webcam indisponivel em SYSTEM via %s; liberando mutex para nova tentativa.", camera_backend)
                return 21
        report("camera_ready")
        auth = FaceAuthenticator(models, db)
        try:
            _ = auth.recognizer
        except Exception as e:
            logger.warning("Aviso ao pre-aquecer modelos faciais: %s", e)
        watchdog = AgentWatchdog()
        watchdog_thread = AgentWatchdogThread(watchdog, check_interval=15.0)
        watchdog_thread.start()
        try:
            _serve_connections(kernel32, sa, auth, camera_backend, once, report, watchdog=watchdog)
        finally:
            watchdog_thread.stop()
        return 0
    finally:
        if sa is not None and sa.lpSecurityDescriptor:
            kernel32.LocalFree(sa.lpSecurityDescriptor)
        kernel32.CloseHandle(h_mutex)


def _serve_connections(kernel32, sa, auth, camera_backend, once, report, watchdog=None):
    while True:
        report("pipe_setup")
        logger.info("Aguardando conexao do LogonUI / Credential Provider em %s...", PIPE_NAME)
        h_pipe = kernel32.CreateNamedPipeW(
            PIPE_NAME,
            PIPE_ACCESS_DUPLEX,
            auth_pipe_mode_flags(),
            PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE,
            BUFFER_SIZE,
            0,
            ctypes.byref(sa) if sa.lpSecurityDescriptor else None,
        )

        if h_pipe == INVALID_HANDLE_VALUE:
            err = kernel32.GetLastError()
            logger.error("Falha ao criar Named Pipe (erro %d). Tentando novamente em 2s...", err)
            time.sleep(2.0)
            continue

        try:
            report("listening")
            connected = kernel32.ConnectNamedPipe(h_pipe, None)
            if not connected and kernel32.GetLastError() != 535:  # ERROR_PIPE_CONNECTED
                logger.warning("Falha ao conectar cliente (erro %d).", kernel32.GetLastError())
                continue

            report("request")
            logger.info("Cliente conectado! Lendo solicitacao...")
            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD()
            success = kernel32.ReadFile(
                h_pipe, buf, BUFFER_SIZE - 1, ctypes.byref(bytes_read), None
            )

            raw_command = buf.raw[:bytes_read.value] if success else b""
            command, error = decode_pipe_command(raw_command)
            logger.info("Requisicao IPC (%d bytes, valida=%s)",
                        bytes_read.value, error is None)

            if error == "INVALID_REQUEST":
                status, data = "INVALID_REQUEST", {"message": "Enquadramento IPC invalido"}
            elif error == "INVALID_COMMAND":
                status, data = "INVALID_COMMAND", {"message": "Comando IPC desconhecido"}
            elif command in ("AUTH_QUERY", "QUERY", "SESSION_QUERY"):
                status, data = auth.evaluate(
                    camera_backend=camera_backend,
                    publish_unlock_event=command != "SESSION_QUERY")
            elif command == "PING":
                status, data = "PONG", {"version": "1.0"}
            else:
                status, data = "INVALID_REQUEST", {"message": "Requisicao IPC vazia"}

            response_payload = {
                "status": status,
                "version": "1.0",
                "user": "Filhos" if status == "ALLOW" else "",
                "data": data,
                "timestamp": time.time(),
            }
            if status in ("ALLOW", "DENY_QUOTA", "DENY_CURFEW"):
                response_payload["child_id"] = data.get("child_id")
                response_payload["child_name"] = data.get("child_name")
                response_payload["remaining"] = data.get("remaining")
                response_payload["protocol_marker"] = IPC_PROTOCOL_MARKER
                if status == "ALLOW" and command != "SESSION_QUERY":
                    report("allow")
                    if watchdog is not None:
                        watchdog.notify_allow()

            response_json = json.dumps(response_payload) + "\n"
            response_bytes = response_json.encode("utf-8")

            bytes_written = wintypes.DWORD()
            kernel32.WriteFile(
                h_pipe,
                response_bytes,
                len(response_bytes),
                ctypes.byref(bytes_written),
                None,
            )
            try:
                kernel32.FlushFileBuffers(h_pipe)
            except Exception:
                pass
            logger.info("Resposta enviada: status=%s (%d bytes)", status, bytes_written.value)

            kernel32.DisconnectNamedPipe(h_pipe)

            if once:
                logger.info("Modo --once ativado; encerrando servidor.")
                break
        finally:
            kernel32.CloseHandle(h_pipe)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--camera-backend", choices=("dshow", "msmf"), default="dshow")
    parser.add_argument("--status-file", type=Path)
    args = parser.parse_args()
    raise SystemExit(run_pipe_server(once=args.once, camera_backend=args.camera_backend,
                                    status_file=args.status_file))

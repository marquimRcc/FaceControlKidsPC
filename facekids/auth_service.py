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

if sys.platform == "win32":
    log_dir = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "FaceKids"
else:
    log_dir = Path(tempfile.gettempdir()) / "FaceKids"

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

PIPE_NAME = r"\\.\pipe\FaceKidsAuthPipe"
BUFFER_SIZE = 4096

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
INVALID_HANDLE_VALUE = -1

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
        p_sd = wintypes.LPVOID()
        if advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            SDDL_PERMISSIVE, 1, ctypes.byref(p_sd), None
        ):
            sa.lpSecurityDescriptor = p_sd
        else:
            logger.warning("Falha ao criar SDDL customizado; usando seguranca padrao.")
            sa.lpSecurityDescriptor = None
    else:
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

    def evaluate(self, camera_index: int = 0, timeout_seconds: float = 4.5) -> Tuple[str, dict]:
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

            backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
            cap = cv2.VideoCapture(camera_index, backend)
            if not cap.isOpened():
                return "ERROR_CAMERA", {"message": "Nao foi possivel abrir a webcam"}

            deadline = time.monotonic() + timeout_seconds
            best_candidate = None
            consecutive_matches = 0
            best_frame = None
            best_face_box = None

            try:
                while time.monotonic() < deadline:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        time.sleep(0.05)
                        continue

                    faces = rec.faces(frame)
                    if len(faces) >= 1:
                        # Prioriza o rosto mais proximo da camera (maior area)
                        largest_face = max(faces, key=lambda f: float(f[2]) * float(f[3]))
                        features = rec.features(frame, largest_face)
                        candidate_id, score = rec.identify(
                            features, references, threshold=0.38, min_margin=0.04
                        )
                        if candidate_id is not None:
                            logger.info(
                                "Rosto candidato detectado: %s (score=%.3f)",
                                names.get(candidate_id, candidate_id),
                                score or 0.0,
                            )
                            if candidate_id == best_candidate:
                                consecutive_matches += 1
                                best_frame = frame.copy()
                                best_face_box = largest_face
                                if consecutive_matches >= 2:
                                    break
                            else:
                                best_candidate = candidate_id
                                consecutive_matches = 1
                                best_frame = frame.copy()
                                best_face_box = largest_face
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
                }

            logger.info("Filho autorizado: %s (Saldo: %ds)", child_name, remaining_seconds)

            # Salva foto recortada de avatar da crianca reconhecida
            if best_frame is not None:
                try:
                    save_child_photo(best_candidate, best_frame, best_face_box)
                except Exception as e:
                    logger.warning("Falha ao salvar avatar do filho: %s", e)

            # Grava ultimo evento de desbloqueio para a tela de boas-vindas
            try:
                unlock_data = {
                    "child_id": best_candidate,
                    "child_name": child_name,
                    "remaining_seconds": remaining_seconds,
                    "timestamp": time.time(),
                }
                unlock_path = Path("C:/ProgramData/FaceKids/last_unlock.json") if sys.platform == "win32" else (log_dir / "last_unlock.json")
                unlock_path.parent.mkdir(parents=True, exist_ok=True)
                unlock_path.write_text(
                    json.dumps(unlock_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning("Falha ao salvar last_unlock.json: %s", e)

            return "ALLOW", {
                "child_id": best_candidate,
                "child_name": child_name,
                "remaining": remaining_seconds,
                "user": "Filhos",
            }
        finally:
            store.close()


def probe_camera_access(camera_index: int = 0) -> bool:
    """Verifica se o contexto atual de execucao tem permissao e capacidade de abrir a webcam."""
    try:
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
        cap = cv2.VideoCapture(camera_index, backend)
        if not cap.isOpened():
            return False
        ret, frame = cap.read()
        cap.release()
        return bool(ret and frame is not None)
    except Exception as e:
        logger.warning("Falha na sondagem da webcam: %s", e)
        return False


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


def run_pipe_server(models_dir: Optional[Path] = None, db_path: Optional[Path] = None, once: bool = False):
    root = Path(__file__).resolve().parent.parent
    models = models_dir or (root / "models")
    db = db_path or child_pilot_database()

    logger.info("Iniciando FaceKids Auth Service...")
    logger.info("Modelos: %s", models)
    logger.info("Banco: %s", db)

    # Verificacao de viabilidade de webcam no contexto de execucao (Sessao 0 vs Interativa)
    if is_session_zero_or_system():
        logger.info("Detectado contexto SYSTEM / Sessao 0. Realizando sondagem de acesso a webcam...")
        if not probe_camera_access(0):
            logger.error(
                "AVISO CRÍTICO: Contexto SYSTEM / Sessao 0 nao possui acesso aos dispositivos DirectShow de webcam. "
                "Encerrando processo para liberar a execucao interativa no login do usuario sem bloquear o mutex."
            )
            return

    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is None:
        logger.error("Servico Named Pipe requer ambiente Windows.")
        return

    h_mutex = kernel32.CreateMutexW(None, False, "Global\\FaceKidsAuthServiceMutex")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        logger.info("Outra instancia de FaceKids Auth Service ja esta em execucao. Encerrando duplicata.")
        return

    auth = FaceAuthenticator(models, db)

    sa = create_security_attributes()

    while True:
        logger.info("Aguardando conexao do LogonUI / Credential Provider em %s...", PIPE_NAME)
        h_pipe = kernel32.CreateNamedPipeW(
            PIPE_NAME,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
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
            connected = kernel32.ConnectNamedPipe(h_pipe, None)
            if not connected and kernel32.GetLastError() != 535:  # ERROR_PIPE_CONNECTED
                logger.warning("Falha ao conectar cliente (erro %d).", kernel32.GetLastError())
                kernel32.CloseHandle(h_pipe)
                continue

            logger.info("Cliente conectado! Lendo solicitacao...")
            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD()
            success = kernel32.ReadFile(
                h_pipe, buf, BUFFER_SIZE - 1, ctypes.byref(bytes_read), None
            )

            request_str = buf.value.decode("utf-8", errors="ignore").strip() if success else ""
            logger.info("Requisicao recebida (%d bytes): '%s'", bytes_read.value, request_str[:64])

            # Validacao estrita do protocolo IPC
            if len(request_str) > 512:
                status, data = "INVALID_REQUEST", {"message": "Tamanho da mensagem excede o maximo de 512 bytes"}
            elif request_str in ("AUTH_QUERY", "QUERY"):
                status, data = auth.evaluate()
            elif request_str == "PING":
                status, data = "PONG", {"version": "1.0"}
            else:
                status, data = "INVALID_COMMAND", {"message": f"Comando desconhecido: '{request_str[:32]}'"}

            response_payload = {
                "status": status,
                "version": "1.0",
                "user": "Filhos" if status == "ALLOW" else "",
                "data": data,
                "timestamp": time.time(),
            }
            if status == "ALLOW":
                response_payload["child_id"] = data.get("child_id")
                response_payload["child_name"] = data.get("child_name")
                response_payload["remaining"] = data.get("remaining")
                response_payload["protocol_marker"] = IPC_PROTOCOL_MARKER

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
            kernel32.FlushFileBuffers(h_pipe)
            logger.info("Resposta enviada: status=%s (%d bytes)", status, bytes_written.value)

            kernel32.DisconnectNamedPipe(h_pipe)

            if once:
                logger.info("Modo --once ativado; encerrando servidor.")
                break
        finally:
            kernel32.CloseHandle(h_pipe)


if __name__ == "__main__":
    once_flag = "--once" in sys.argv
    run_pipe_server(once=once_flag)

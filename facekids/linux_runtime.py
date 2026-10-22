"""Runtime Linux/Regata OS para reconhecimento e quota na sessão compartilhada."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import struct
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from .child_quota_pilot import ChildQuotaEngine, PilotEvent
from .linux_auth import FaceApprovalBroker
from .locker import lock_current_session
from .recognition import Recognizer
from .session import SessionState, current_linux_session_state, linux_display_session
from .storage import Storage

LOG = logging.getLogger("facekids.linux")


def protected_data_path() -> Path:
    return Path(os.environ.get("FACEKIDS_DATA_DIR", "/var/lib/facekids")) / "criancas.sqlite3"


def frame_is_usable(frame) -> bool:
    """Recusa quadros ausentes, pretos ou essencialmente uniformes."""
    return bool(
        frame is not None
        and getattr(frame, "size", 0) > 0
        and float(np.mean(frame)) >= 4.0
        and float(np.std(frame)) >= 2.0
    )


@dataclass(frozen=True)
class LinuxRuntimeConfig:
    database: Path
    models: Path
    camera: int = 0
    session_id: str | None = None
    monitored_user: str | None = None
    interval_seconds: float = 1.0
    lock_on_uncertain: bool = True

    def validate(self) -> None:
        if not 0 <= self.camera <= 32:
            raise ValueError("Câmera deve estar entre 0 e 32")
        if not 0.2 <= self.interval_seconds <= 15:
            raise ValueError("Intervalo deve estar entre 0,2 e 15 segundos")
        if self.session_id and not all(
            ch.isalnum() or ch in "_-" for ch in self.session_id
        ):
            raise ValueError("Identificador de sessão inválido")
        if self.monitored_user and not all(
            ch.isalnum() or ch in "_.-" for ch in self.monitored_user
        ):
            raise ValueError("Usuário monitorado inválido")


class LinuxFaceQuotaRuntime:
    """Mantém a autoridade de reconhecimento e contabilização num processo.

    Em instalação protegida o processo roda como root, o banco fica sob
    ``/var/lib/facekids`` e a conta compartilhada não recebe escrita nele.
    """

    def __init__(self, config: LinuxRuntimeConfig):
        config.validate()
        self.config = config
        self.store = Storage(config.database)
        self.engine = ChildQuotaEngine(self.store)
        self.recognizer = Recognizer(config.models)
        self.references = [
            (person_id, vector)
            for person_id, vector in self.store.embeddings()
            if person_id in self.engine.people
        ]
        self._stopping = False
        self._last_signal = None
        self.approvals = FaceApprovalBroker()
        self.socket_path = Path(os.environ.get(
            "FACEKIDS_AUTH_SOCKET", "/run/facekids/auth.sock"
        ))
        self._server_thread: threading.Thread | None = None

    def stop(self, *_args) -> None:
        self._stopping = True

    def close(self) -> None:
        self.store.close()

    def _serve_auth(self, server: socket.socket) -> None:
        try:
            while not self._stopping:
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                with connection:
                    try:
                        credentials = connection.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                        )
                        _pid, uid, _gid = struct.unpack("3i", credentials)
                        request = connection.recv(128).decode("ascii", "strict").strip()
                        verb, separator, session_id = request.partition(" ")
                        allowed = False
                        if (uid == 0 and verb == "AUTH" and separator
                                and session_id
                                and all(ch.isalnum() or ch in "_-" for ch in session_id)):
                            allowed = self.approvals.consume(session_id, time.monotonic()) is not None
                        connection.sendall(b"ALLOW\n" if allowed else b"DENY\n")
                    except (OSError, UnicodeError, ValueError):
                        try:
                            connection.sendall(b"DENY\n")
                        except OSError:
                            pass
        finally:
            server.close()
            self.socket_path.unlink(missing_ok=True)

    def _start_auth_server(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(4)
            server.settimeout(0.5)
        except Exception:
            server.close()
            self.socket_path.unlink(missing_ok=True)
            raise
        self._server_thread = threading.Thread(
            target=self._serve_auth, args=(server,), daemon=True
        )
        self._server_thread.start()

    def _candidate(self, capture) -> int | None:
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        # Quadros pretos/congelados não são evidência de ausência de rosto.
        if not frame_is_usable(frame):
            raise RuntimeError("A câmera forneceu quadro preto ou sem contraste")
        faces = self.recognizer.faces(frame)
        if len(faces) != 1:
            return None
        vector = self.recognizer.features(frame, faces[0])
        child_id, _score = self.recognizer.identify(vector, self.references)
        return child_id

    def run(self) -> int:
        import cv2

        if not self.references:
            raise RuntimeError("Nenhum perfil facial infantil cadastrado")
        capture = cv2.VideoCapture(self.config.camera, cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Não foi possível abrir /dev/video{self.config.camera}")
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        capture.set(cv2.CAP_PROP_FPS, 10)
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self._start_auth_server()
        try:
            while not self._stopping:
                started = time.monotonic()
                session_id = self.config.session_id or linux_display_session(
                    self.config.monitored_user
                )
                state = current_linux_session_state(session_id) if session_id else SessionState.UNKNOWN
                try:
                    candidate = self._candidate(capture) if state in {
                        SessionState.ACTIVE, SessionState.LOCKED
                    } else None
                except RuntimeError as exc:
                    LOG.error("Falha de captura: %s", exc)
                    candidate = None
                today = date.today().isoformat()
                reading = self.engine.step(started, today, state, candidate)
                curfew, reason = self.store.is_curfew_active()
                quota_available = (
                    candidate in self.engine.people
                    and self.store.remaining(candidate, today) > 0
                )
                self.approvals.observe(
                    now=started, session_id=session_id, state=state,
                    child_id=candidate, quota_available=quota_available,
                    curfew_clear=not curfew,
                )
                should_lock = reading.event is PilotEvent.QUOTA_EXHAUSTED or curfew
                if (reading.event is PilotEvent.UNCERTAIN
                        and self.config.lock_on_uncertain):
                    should_lock = True
                    reason = "identidade não confirmada"
                current_signal = (reading.event, reading.child_id, should_lock)
                if current_signal != self._last_signal:
                    LOG.info(
                        "event=%s child=%s charged=%.3f remaining=%s lock=%s",
                        reading.event.value, reading.child_id,
                        reading.charged_seconds, reading.remaining_seconds, should_lock,
                    )
                    self._last_signal = current_signal
                if should_lock and state is SessionState.ACTIVE:
                    LOG.warning("Bloqueando sessão: %s", reason)
                    lock_current_session(session_id)
                    self.engine.policy.pause()
                elapsed = time.monotonic() - started
                time.sleep(max(0.0, self.config.interval_seconds - elapsed))
        finally:
            capture.release()
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FaceKids Linux: reconhecimento local e quotas por rosto"
    )
    parser.add_argument("--database", type=Path, default=protected_data_path())
    parser.add_argument(
        "--models", type=Path,
        default=Path("/usr/lib/facekids/models"),
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--session-id")
    parser.add_argument("--user", dest="monitored_user", default="filhos")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--allow-uncertain", action="store_true",
        help="Pausa a contagem sem bloquear quando o rosto some",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime = LinuxFaceQuotaRuntime(LinuxRuntimeConfig(
        database=args.database,
        models=args.models,
        camera=args.camera,
        session_id=args.session_id,
        monitored_user=args.monitored_user,
        interval_seconds=args.interval,
        lock_on_uncertain=not args.allow_uncertain,
    ))
    try:
        return runtime.run()
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())

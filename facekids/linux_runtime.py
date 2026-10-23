"""Runtime Linux/Regata OS para reconhecimento e quota na sessão compartilhada."""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import signal
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

try:  # módulos POSIX ausentes no runner Windows que valida imports e testes comuns
    import grp
    import pwd
except ImportError:  # pragma: no cover - exercitado pelo CI Windows
    grp = None
    pwd = None

from .child_quota_pilot import ChildQuotaEngine, PilotEvent
from .linux_auth import FaceApprovalBroker, approval_still_allowed
from .locker import lock_current_session, unlock_linux_session
from .parent_face_pilot import REQUIRED_SAMPLES, _valid_features
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


def warm_up_camera(capture, frames: int = 15) -> int:
    """Descarta quadros iniciais enquanto exposição e buffers se estabilizam."""
    if type(frames) is not int or not 0 <= frames <= 120:
        raise ValueError("Quantidade de quadros de aquecimento inválida")
    successful = 0
    for _ in range(frames):
        ok, frame = capture.read()
        if ok and frame is not None:
            successful += 1
    return successful


def enrollments_complete(
    references: list[tuple[int, np.ndarray]], people, minimum_samples: int = 3
) -> bool:
    """Exige evidência facial mínima para cada perfil configurado."""
    if type(minimum_samples) is not int or minimum_samples < 1:
        raise ValueError("Mínimo de amostras inválido")
    expected = set(people)
    if not expected:
        return False
    counts = {person_id: 0 for person_id in expected}
    for person_id, _vector in references:
        if person_id in counts:
            counts[person_id] += 1
    return all(count >= minimum_samples for count in counts.values())


def determine_lock_state(
    reading_event: PilotEvent,
    curfew_active: bool,
    curfew_reason: str,
    enrollments_ready: bool,
    lock_on_uncertain: bool = True,
) -> tuple[bool, str]:
    """Determina se a sessão ativa deve ser bloqueada e o motivo fechado."""
    if not enrollments_ready:
        return True, "cadastro facial incompleto ou revogado"
    if curfew_active:
        return True, curfew_reason
    if reading_event is PilotEvent.QUOTA_EXHAUSTED:
        return True, "quota esgotada"
    if reading_event is PilotEvent.UNCERTAIN and lock_on_uncertain:
        return True, "identidade não confirmada"
    return False, ""


@dataclass(frozen=True)
class LinuxRuntimeConfig:
    database: Path
    models: Path
    camera: int = 0
    session_id: str | None = None
    monitored_user: str | None = None
    interval_seconds: float = 1.0
    lock_on_uncertain: bool = True
    auto_unlock: bool = True
    admin_group: str = "wheel"

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
        if not self.admin_group or not all(
            ch.isalnum() or ch in "_-" for ch in self.admin_group
        ):
            raise ValueError("Grupo administrador inválido")


def uid_is_admin(uid: int, group_name: str) -> bool:
    """Autoriza root ou membro real do grupo administrativo configurado."""
    if uid == 0:
        return True
    if grp is None or pwd is None:
        return False
    try:
        account = pwd.getpwuid(uid)
        group = grp.getgrnam(group_name)
    except KeyError:
        return False
    return account.pw_gid == group.gr_gid or account.pw_name in group.gr_mem


class LinuxFaceQuotaRuntime:
    """Mantém a autoridade de reconhecimento e contabilização num processo.

    Em instalação protegida o processo roda como root, o banco fica sob
    ``/var/lib/facekids`` e a conta compartilhada não recebe escrita nele.
    """

    def __init__(self, config: LinuxRuntimeConfig):
        config.validate()
        self.config = config
        self.store = Storage(config.database)
        people = {pid: name for pid, name, _limit in self.store.people()}
        self.engine = ChildQuotaEngine(self.store, people=people)
        self.recognizer = Recognizer(config.models)
        self.references = [
            (person_id, vector)
            for person_id, vector in self.store.embeddings()
            if person_id in self.engine.people
        ]
        self._reference_signature = self._references_signature(self.references)
        self._last_reference_refresh = float("-inf")
        self._stopping = False
        self._last_signal = None
        self.approvals = FaceApprovalBroker()
        self.socket_path = Path(os.environ.get(
            "FACEKIDS_AUTH_SOCKET", "/run/facekids/auth.sock"
        ))
        self.admin_socket_path = Path(os.environ.get(
            "FACEKIDS_ADMIN_SOCKET", "/run/facekids/admin.sock"
        ))
        self._server_thread: threading.Thread | None = None
        self._admin_server_thread: threading.Thread | None = None
        self._admin_lock = threading.Lock()
        self._enrollment: dict | None = None
        self._current_child_id: int | None = None
        self._session_state = SessionState.UNKNOWN
        self._last_unlock_request = float("-inf")
        self._last_lock_request = float("-inf")

    @staticmethod
    def _references_signature(references) -> tuple:
        return tuple(
            sorted((person_id, np.asarray(vector).tobytes())
                   for person_id, vector in references)
        )

    def _refresh_references(self, now: float, force: bool = False) -> bool:
        """Aplica alterações administrativas e revoga evidência facial antiga."""
        if not force and now - self._last_reference_refresh < 2.0:
            return enrollments_complete(self.references, self.engine.people)
        fresh_people = {pid: name for pid, name, _limit in self.store.people()}
        if fresh_people != self.engine.people:
            self.engine.people = fresh_people
            self.approvals.reset()
            self.engine.policy.pause()
            LOG.info("Lista de crianças recarregada; autorizações anteriores revogadas")
        fresh = [
            (person_id, vector)
            for person_id, vector in self.store.embeddings()
            if person_id in fresh_people
        ]
        signature = self._references_signature(fresh)
        if signature != self._reference_signature:
            self.references = fresh
            self._reference_signature = signature
            self.approvals.reset()
            self.engine.policy.pause()
            LOG.info("Cadastros faciais recarregados; autorizações anteriores revogadas")
        self._last_reference_refresh = now
        return enrollments_complete(self.references, self.engine.people)

    def stop(self, *_args) -> None:
        self._stopping = True

    def close(self) -> None:
        self._stopping = True
        for thread in (
            getattr(self, "_server_thread", None),
            getattr(self, "_admin_server_thread", None),
        ):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        self.socket_path.unlink(missing_ok=True)
        admin_socket = getattr(self, "admin_socket_path", None)
        if admin_socket is not None:
            admin_socket.unlink(missing_ok=True)
        self.store.close()

    def _enrollment_snapshot(self) -> dict | None:
        with self._admin_lock:
            if self._enrollment is None:
                return None
            return {
                "childId": self._enrollment["child_id"],
                "samples": len(self._enrollment["vectors"]),
                "requiredSamples": REQUIRED_SAMPLES,
                "state": self._enrollment["state"],
                "error": self._enrollment.get("error"),
            }

    def _admin_status(self, store: Storage) -> dict:
        today = date.today().isoformat()
        enabled, start, end = store.get_curfew_config()
        current = self._current_child_id
        children = []
        for person_id, name, limit_seconds in store.people():
            photo = store.selected_profile_photo(person_id)
            children.append({
                "id": person_id,
                "name": name,
                "initials": "".join(part[0] for part in name.split()[:2]).upper()[:3] or "?",
                "remainingSeconds": int(store.remaining(person_id, today)),
                "dailyLimitSeconds": int(limit_seconds),
                "bonusSeconds": int(store.bonus(person_id, today)),
                "enrollmentSamples": store.enrollment_count(person_id),
                "isPresent": person_id == current,
                "avatarPhoto": (
                    "data:image/jpeg;base64," + base64.b64encode(photo).decode("ascii")
                    if photo else None
                ),
            })
        return {
            "ok": True,
            "snapshot": {
                "generatedAt": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                "service": "online",
                "camera": "ready",
                "session": {
                    SessionState.ACTIVE: "active",
                    SessionState.LOCKED: "locked",
                }.get(self._session_state, "absent"),
                "curfew": {"enabled": enabled, "start": start, "end": end},
                "children": children,
            },
            "enrollment": self._enrollment_snapshot(),
        }

    def _dispatch_admin(self, store: Storage, request: dict) -> dict:
        op = request.get("op")
        if op == "status":
            return self._admin_status(store)
        if op in {"add_child", "add_child_and_start_enrollment"}:
            name, minutes = request.get("name"), request.get("minutes")
            if not isinstance(name, str) or type(minutes) is not int:
                raise ValueError("Nome ou limite inválido")
            if op == "add_child_and_start_enrollment":
                with self._admin_lock:
                    if self._enrollment and self._enrollment["state"] == "capturing":
                        raise RuntimeError("Já existe um cadastro facial em andamento")
            person_id = store.add_person(name, minutes)
            index = next(i for i, row in enumerate(store.people(), 1) if row[0] == person_id)
            if op == "add_child_and_start_enrollment":
                with self._admin_lock:
                    self._enrollment = {
                        "child_id": person_id, "vectors": [], "state": "capturing",
                        "photos": [], "last_at": float("-inf"), "error": None,
                        "new_profile": True,
                    }
            return {"ok": True, "childId": person_id, "childIndex": index}
        if op == "start_enrollment":
            child_id = request.get("childId")
            if type(child_id) is not int or child_id <= 0:
                raise ValueError("Identificador de criança inválido")
            if child_id not in {row[0] for row in store.people()}:
                raise KeyError(child_id)
            with self._admin_lock:
                if self._enrollment and self._enrollment["state"] == "capturing":
                    raise RuntimeError("Já existe um cadastro facial em andamento")
                self._enrollment = {
                    "child_id": child_id, "vectors": [], "state": "capturing",
                    "photos": [], "last_at": float("-inf"), "error": None,
                    "new_profile": False,
                }
            return {"ok": True}
        if op == "list_photos":
            child_id = request.get("childId")
            if type(child_id) is not int or child_id <= 0:
                raise ValueError("Identificador de criança inválido")
            if child_id not in {row[0] for row in store.people()}:
                raise KeyError(child_id)
            return {"ok": True, "photos": [
                {
                    "id": photo_id,
                    "dataUrl": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
                    "selected": selected,
                }
                for photo_id, jpeg, selected in store.profile_photos(child_id)
            ]}
        if op == "select_photo":
            child_id, photo_id = request.get("childId"), request.get("photoId")
            store.select_profile_photo(child_id, photo_id)
            return {"ok": True}
        if op == "cancel_enrollment":
            with self._admin_lock:
                enrollment = self._enrollment
                self._enrollment = None
            if (enrollment and enrollment.get("new_profile")
                    and not store.remove_unenrolled_person(enrollment["child_id"])):
                raise RuntimeError("O perfil já possui dados e não pode ser removido")
            return {"ok": True}
        raise ValueError("Operação administrativa desconhecida")

    def _serve_admin(self, server: socket.socket) -> None:
        store = Storage(self.config.database)
        try:
            while not self._stopping:
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(3.0)
                    response = {"ok": False, "error": "Pedido recusado"}
                    try:
                        credentials = connection.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                        )
                        _pid, uid, _gid = struct.unpack("3i", credentials)
                        if not uid_is_admin(uid, self.config.admin_group):
                            raise PermissionError("Conta sem permissão administrativa")
                        raw = connection.recv(4097)
                        if len(raw) > 4096 or not raw.endswith(b"\n"):
                            raise ValueError("Pedido administrativo inválido")
                        request = json.loads(raw.decode("utf-8"))
                        if not isinstance(request, dict):
                            raise TypeError("Pedido administrativo inválido")
                        response = self._dispatch_admin(store, request)
                    except Exception as exc:  # noqa: BLE001 - limite IPC deve responder fechado
                        response = {"ok": False, "error": str(exc) or type(exc).__name__}
                    connection.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode())
        finally:
            store.close()
            server.close()
            self.admin_socket_path.unlink(missing_ok=True)

    def _start_admin_server(self) -> None:
        if grp is None:
            raise RuntimeError("Grupos POSIX indisponíveis nesta plataforma")
        group = grp.getgrnam(self.config.admin_group)
        self.admin_socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.admin_socket_path.parent.stat().st_gid != group.gr_gid:
            raise RuntimeError("Diretório de runtime não pertence ao grupo administrador")
        os.chmod(self.admin_socket_path.parent, 0o750)
        self.admin_socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.admin_socket_path))
            if self.admin_socket_path.stat().st_gid != group.gr_gid:
                raise RuntimeError("Socket administrativo criado com grupo incorreto")
            os.chmod(self.admin_socket_path, 0o660)
            server.listen(4)
            server.settimeout(0.5)
        except Exception:
            server.close()
            self.admin_socket_path.unlink(missing_ok=True)
            raise
        self._admin_server_thread = threading.Thread(
            target=self._serve_admin, args=(server,), daemon=True
        )
        self._admin_server_thread.start()

    def _process_enrollment(self, capture, now: float) -> bool:
        with self._admin_lock:
            enrollment = self._enrollment
            if enrollment is None or enrollment["state"] != "capturing":
                return False
        ok, frame = capture.read()
        if not ok or not frame_is_usable(frame):
            return True
        faces = self.recognizer.faces(frame)
        if len(faces) != 1:
            return True
        vector = self.recognizer.features(frame, faces[0])
        if not _valid_features(vector):
            return True
        with self._admin_lock:
            if self._enrollment is not enrollment or now - enrollment["last_at"] < 0.55:
                return True
            enrollment["vectors"].append(np.asarray(vector, dtype=np.float32).reshape(128).copy())
            sample_number = len(enrollment["vectors"])
            if sample_number in {1, 6, REQUIRED_SAMPLES}:
                photo = self._encode_profile_photo(frame, faces[0])
                if photo is not None:
                    enrollment["photos"].append(photo)
            enrollment["last_at"] = now
            if sample_number >= REQUIRED_SAMPLES:
                try:
                    self.store.replace_embeddings_and_add_photos(
                        enrollment["child_id"], enrollment["vectors"], enrollment["photos"]
                    )
                    enrollment["state"] = "complete"
                    self._refresh_references(now, force=True)
                except Exception as exc:  # noqa: BLE001 - mantém serviço vivo e expõe erro
                    enrollment["state"] = "error"
                    enrollment["error"] = str(exc)
        return True

    @staticmethod
    def _encode_profile_photo(frame, face) -> bytes | None:
        """Recorta um retrato JPEG local; não participa do reconhecimento."""
        import cv2

        height, width = frame.shape[:2]
        x, y, face_width, face_height = (int(value) for value in face[:4])
        margin_x, margin_y = int(face_width * 0.35), int(face_height * 0.25)
        left, top = max(0, x - margin_x), max(0, y - margin_y)
        right = min(width, x + face_width + margin_x)
        bottom = min(height, y + face_height + margin_y)
        if right - left < 48 or bottom - top < 48:
            return None
        crop = cv2.resize(frame[top:bottom, left:right], (256, 256))
        ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 86])
        if not ok:
            return None
        payload = encoded.tobytes()
        return payload if 100 <= len(payload) <= 100000 else None

    def _serve_auth(self, server: socket.socket) -> None:
        verifier = Storage(self.config.database)
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
                            approval = self.approvals.consume(session_id, time.monotonic())
                            if approval is not None:
                                allowed = approval_still_allowed(
                                    verifier, approval, date.today().isoformat()
                                )
                        connection.sendall(b"ALLOW\n" if allowed else b"DENY\n")
                    except (OSError, UnicodeError, ValueError):
                        try:
                            connection.sendall(b"DENY\n")
                        except OSError:
                            pass
        finally:
            verifier.close()
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

    def _maybe_unlock(
        self, approval, now: float, day: str
    ) -> bool:
        """Revalida e solicita desbloqueio, limitando repetição do comando."""
        if (not self.config.auto_unlock or approval is None
                or now - self._last_unlock_request < 10.0
                or not approval_still_allowed(self.store, approval, day)):
            return False
        try:
            unlock_linux_session(approval.session_id)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            self._last_unlock_request = now
            LOG.exception(
                "Falha ao solicitar desbloqueio da sessão %s",
                approval.session_id,
            )
            return False
        self._last_unlock_request = now
        LOG.info(
            "Desbloqueio facial solicitado para sessão %s e criança %s",
            approval.session_id, approval.child_id,
        )
        return True

    def _maybe_lock(self, session_id: str | None, reason: str, now: float) -> bool:
        """Solicita bloqueio sem derrubar o controlador se o logind falhar."""
        if now - self._last_lock_request < 10.0:
            return False
        try:
            lock_current_session(session_id)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            self._last_lock_request = now
            LOG.exception("Falha ao bloquear sessão %s: %s", session_id, reason)
            return False
        self._last_lock_request = now
        LOG.warning("Sessão %s bloqueada: %s", session_id, reason)
        self.engine.policy.pause()
        return True

    def run(self) -> int:
        import cv2

        capture = cv2.VideoCapture(self.config.camera, cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Não foi possível abrir /dev/video{self.config.camera}")
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        capture.set(cv2.CAP_PROP_FPS, 10)
        warmed = warm_up_camera(capture)
        LOG.info("Aquecimento da câmera: %s/15 quadros recebidos", warmed)
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self._start_auth_server()
        self._start_admin_server()
        try:
            while not self._stopping:
                started = time.monotonic()
                enrollments_ready = self._refresh_references(started)
                session_id = self.config.session_id or linux_display_session(
                    self.config.monitored_user
                )
                state = current_linux_session_state(session_id) if session_id else SessionState.UNKNOWN
                self._session_state = state
                try:
                    enrolling = self._process_enrollment(capture, started)
                    candidate = self._candidate(capture) if not enrolling and enrollments_ready and state in {
                        SessionState.ACTIVE, SessionState.LOCKED
                    } else None
                except RuntimeError as exc:
                    LOG.error("Falha de captura: %s", exc)
                    candidate = None
                self._current_child_id = candidate
                today = date.today().isoformat()
                reading = self.engine.step(started, today, state, candidate)
                curfew, reason = self.store.is_curfew_active()
                quota_available = (
                    candidate in self.engine.people
                    and self.store.remaining(candidate, today) > 0
                )
                approval = self.approvals.observe(
                    now=started, session_id=session_id, state=state,
                    child_id=candidate, quota_available=quota_available,
                    curfew_clear=not curfew,
                )
                self._maybe_unlock(approval, started, today)
                should_lock, lock_reason = determine_lock_state(
                    reading.event,
                    curfew_active=curfew,
                    curfew_reason=reason,
                    enrollments_ready=enrollments_ready,
                    lock_on_uncertain=self.config.lock_on_uncertain,
                )
                current_signal = (reading.event, reading.child_id, should_lock)
                if current_signal != self._last_signal:
                    LOG.info(
                        "event=%s child=%s charged=%.3f remaining=%s lock=%s",
                        reading.event.value, reading.child_id,
                        reading.charged_seconds, reading.remaining_seconds, should_lock,
                    )
                    self._last_signal = current_signal
                if should_lock and state is SessionState.ACTIVE:
                    self._maybe_lock(session_id, lock_reason, started)
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
    parser.add_argument("--admin-group", default="wheel")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--allow-uncertain", action="store_true",
        help="Pausa a contagem sem bloquear quando o rosto some",
    )
    parser.add_argument(
        "--no-auto-unlock", action="store_true",
        help="Desativa o pedido de desbloqueio facial pelo logind",
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
        auto_unlock=not args.no_auto_unlock,
        admin_group=args.admin_group,
    ))
    try:
        return runtime.run()
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())

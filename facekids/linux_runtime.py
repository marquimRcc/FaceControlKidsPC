"""Runtime Linux/Regata OS para reconhecimento e quota na sessão compartilhada."""
from __future__ import annotations

import argparse
import base64
import collections
import json
import logging
import os
import signal
import socket
import statistics
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
    admin_group: str = "wheel,sudo"

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
            ch.isalnum() or ch in "_-," for ch in self.admin_group
        ):
            raise ValueError("Grupo administrador inválido")


def resolve_admin_gids(group_names: str | tuple[str, ...]) -> set[int]:
    """Descobre os GIDs válidos para os grupos administrativos indicados."""
    if grp is None:
        return set()
    if isinstance(group_names, str):
        candidates = [g.strip() for g in group_names.split(",") if g.strip()]
    else:
        candidates = list(group_names)
    gids: set[int] = set()
    for name in candidates:
        try:
            gids.add(grp.getgrnam(name).gr_gid)
        except KeyError:
            continue
    return gids


def uid_is_admin(uid: int, group_name: str = "wheel,sudo") -> bool:
    """Autoriza root ou membro real de grupo administrativo (wheel, sudo, etc.)."""
    if uid == 0:
        return True
    if grp is None or pwd is None:
        return False
    try:
        account = pwd.getpwuid(uid)
    except KeyError:
        return False

    admin_gids = resolve_admin_gids(group_name)
    if not admin_gids:
        # Tenta fallback se nenhum dos grupos configurados existir na distro
        admin_gids = resolve_admin_gids(("wheel", "sudo"))
    if not admin_gids:
        return False

    if account.pw_gid in admin_gids:
        return True

    # os.getgrouplist resolve grupos suplementares de forma confiável (inclusive NSS/SSSD/homed)
    if hasattr(os, "getgrouplist"):
        try:
            user_gids = set(os.getgrouplist(account.pw_name, account.pw_gid))
            if admin_gids & user_gids:
                return True
        except OSError:
            LOG.warning("Não foi possível consultar grupos suplementares de UID %s", uid)

    # Fallback para membros estáticos em /etc/group
    for gid in admin_gids:
        try:
            group = grp.getgrgid(gid)
            if account.pw_name in group.gr_mem:
                return True
        except KeyError:
            continue
    return False


def uid_is_monitored_user(uid: int, user_name: str | None) -> bool:
    """Autoriza somente root ou a conta infantil configurada."""
    if uid == 0:
        return True
    if pwd is None or not user_name:
        return False
    try:
        return pwd.getpwnam(user_name).pw_uid == uid
    except KeyError:
        return False


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
        self.child_socket_path = Path(os.environ.get(
            "FACEKIDS_CHILD_SOCKET", "/run/facekids-child/status.sock"
        ))
        self._server_thread: threading.Thread | None = None
        self._admin_server_thread: threading.Thread | None = None
        self._child_server_thread: threading.Thread | None = None
        self._admin_lock = threading.Lock()
        self._enrollment: dict | None = None
        self._current_child_id: int | None = None
        self._session_state = SessionState.UNKNOWN
        self._camera_state = "ready"
        self._last_unlock_request = float("-inf")
        self._last_lock_request = float("-inf")
        self._camera_samples: collections.deque = collections.deque(maxlen=30)
        self._pause_camera_until = float("-inf")

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
            getattr(self, "_child_server_thread", None),
        ):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        self.socket_path.unlink(missing_ok=True)
        admin_socket = getattr(self, "admin_socket_path", None)
        if admin_socket is not None:
            admin_socket.unlink(missing_ok=True)
        child_socket = getattr(self, "child_socket_path", None)
        if child_socket is not None:
            child_socket.unlink(missing_ok=True)
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
                "preview": self._enrollment.get("preview"),
                "feedback": self._enrollment.get("feedback", "waiting"),
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
                "camera": getattr(self, "_camera_state", "ready"),
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
        if op == "set_daily_limit":
            child_id, minutes = request.get("childId"), request.get("minutes")
            if (type(child_id) is not int or child_id <= 0
                    or type(minutes) is not int or not 1 <= minutes <= 1440):
                raise ValueError("Criança ou limite diário inválido")
            store.set_daily_limit(child_id, minutes)
            return {"ok": True}
        if op == "add_bonus":
            child_id, minutes = request.get("childId"), request.get("minutes")
            if (type(child_id) is not int or child_id <= 0
                    or type(minutes) is not int or not 1 <= minutes <= 480):
                raise ValueError("Criança ou bônus inválido")
            store.add_bonus(child_id, minutes)
            return {"ok": True}
        if op == "set_curfew":
            enabled, start, end = (
                request.get("enabled"), request.get("start"), request.get("end")
            )
            if type(enabled) is not bool or not isinstance(start, str) or not isinstance(end, str):
                raise ValueError("Horário permitido inválido")
            store.set_curfew_config(enabled, start, end)
            return {"ok": True}
        if op == "cancel_enrollment":
            with self._admin_lock:
                enrollment = self._enrollment
                self._enrollment = None
            if (enrollment and enrollment.get("new_profile")
                    and not store.remove_unenrolled_person(enrollment["child_id"])):
                raise RuntimeError("O perfil já possui dados e não pode ser removido")
            return {"ok": True}
        if op == "probe":
            seconds = float(request.get("seconds", 5.0))
            with self._admin_lock:
                samples = list(self._camera_samples)
            now = time.monotonic()
            recent = [s for s in samples if now - s["timestamp"] <= max(seconds, 10.0)]
            if not recent and samples:
                recent = samples[-10:]
            frames = len(recent)
            usable_frames = sum(1 for s in recent if s["usable"])
            faces_seen = sum(s["faces"] for s in recent)
            brightness_vals = [s["brightness"] for s in recent if s["brightness"] is not None]
            mean_brightness = (
                float(statistics.fmean(brightness_vals)) if brightness_vals else None
            )
            return {
                "ok": True,
                "probe": {
                    "opened": self._camera_state != "offline",
                    "frames": frames,
                    "usable_frames": usable_frames,
                    "faces_seen": faces_seen,
                    "elapsed_seconds": seconds,
                    "mean_brightness": mean_brightness,
                },
            }
        if op == "pause_camera":
            duration = min(max(float(request.get("seconds", 5.0)), 1.0), 30.0)
            self._pause_camera_until = time.monotonic() + duration
            return {"ok": True, "pausedSeconds": duration}
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

    def _child_status(self, store: Storage) -> dict:
        """Expõe somente a criança atualmente reconhecida, sem controles."""
        status = self._admin_status(store)
        current = self._current_child_id
        status["snapshot"]["children"] = [
            child for child in status["snapshot"]["children"]
            if child["id"] == current
        ]
        status["enrollment"] = None
        return status

    def _serve_child_status(self, server: socket.socket) -> None:
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
                        if not uid_is_monitored_user(uid, self.config.monitored_user):
                            raise PermissionError("Conta sem permissão para a tela infantil")
                        raw = connection.recv(257)
                        if len(raw) > 256 or not raw.endswith(b"\n"):
                            raise ValueError("Pedido de estado inválido")
                        request = json.loads(raw.decode("utf-8"))
                        if request != {"op": "status"}:
                            raise ValueError("Operação infantil desconhecida")
                        response = self._child_status(store)
                    except Exception as exc:  # noqa: BLE001 - IPC responde fechado
                        response = {"ok": False, "error": str(exc) or type(exc).__name__}
                    connection.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode())
        finally:
            store.close()
            server.close()
            self.child_socket_path.unlink(missing_ok=True)

    def _start_child_status_server(self) -> None:
        if pwd is None or not self.config.monitored_user:
            raise RuntimeError("Conta infantil POSIX indisponível")
        account = pwd.getpwnam(self.config.monitored_user)
        self.child_socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(self.child_socket_path.parent, 0, account.pw_gid)
            os.chmod(self.child_socket_path.parent, 0o2750)
        except PermissionError:
            pass
        self.child_socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.child_socket_path))
            try:
                os.chown(self.child_socket_path, 0, account.pw_gid)
            except PermissionError:
                pass
            os.chmod(self.child_socket_path, 0o660)
            server.listen(4)
            server.settimeout(0.5)
        except Exception:
            server.close()
            self.child_socket_path.unlink(missing_ok=True)
            raise
        self._child_server_thread = threading.Thread(
            target=self._serve_child_status, args=(server,), daemon=True
        )
        self._child_server_thread.start()

    def _process_enrollment_frame(self, frame, faces, now: float) -> bool:
        with self._admin_lock:
            enrollment = self._enrollment
            if enrollment is None or enrollment["state"] != "capturing":
                return False
        if frame is None or not frame_is_usable(frame):
            with self._admin_lock:
                if self._enrollment is enrollment:
                    enrollment["feedback"] = "waiting"
            return True
        preview_data = self._encode_camera_preview(frame, faces)
        feedback = "waiting"
        vector = None
        if len(faces) > 1:
            feedback = "multiple"
        elif len(faces) == 1:
            vector = self.recognizer.features(frame, faces[0])
            feedback = "ok" if _valid_features(vector) else "low_quality"

        with self._admin_lock:
            if self._enrollment is not enrollment:
                return True
            enrollment["preview"] = preview_data
            enrollment["feedback"] = feedback
            if feedback != "ok" or vector is None or now - enrollment["last_at"] < 0.55:
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

    def _process_enrollment(self, capture, now: float) -> bool:
        with self._admin_lock:
            if self._enrollment is None or self._enrollment["state"] != "capturing":
                return False
        ok, frame = capture.read()
        if not ok or frame is None:
            return True
        faces = self.recognizer.faces(frame) if frame_is_usable(frame) else []
        return self._process_enrollment_frame(frame, faces, now)

    @staticmethod
    def _encode_camera_preview(frame, faces) -> str | None:
        """Gera uma miniatura JPEG leve com guia facial para visualização no painel."""
        import cv2

        preview = cv2.resize(frame, (320, 240))
        scale_x = 320.0 / frame.shape[1]
        scale_y = 240.0 / frame.shape[0]
        for face in faces[:2]:
            x, y, w, h = (int(v) for v in face[:4])
            px, py, pw, ph = int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)
            color = (235, 240, 25) if len(faces) == 1 else (50, 50, 240)
            cv2.rectangle(preview, (px, py), (px + pw, py + ph), color, 2)
        ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 65])
        if not ok:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

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
            raise RuntimeError("A câmera parou de fornecer quadros")
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
        self._start_child_status_server()
        try:
            while not self._stopping:
                started = time.monotonic()
                if self._pause_camera_until > started:
                    if capture.isOpened():
                        capture.release()
                    self._camera_state = "paused"
                    time.sleep(0.5)
                    continue
                elif not capture.isOpened():
                    capture.open(self.config.camera, cv2.CAP_V4L2)
                    warm_up_camera(capture)

                enrollments_ready = self._refresh_references(started)
                session_id = self.config.session_id or linux_display_session(
                    self.config.monitored_user
                )
                state = current_linux_session_state(session_id) if session_id else SessionState.UNKNOWN
                self._session_state = state

                ok, frame = capture.read()
                if not ok or frame is None:
                    self._camera_state = "offline"
                    LOG.error("Falha de captura: a câmera parou de fornecer quadros")
                    time.sleep(0.5)
                    continue

                usable = frame_is_usable(frame)
                brightness = float(np.mean(frame))
                faces = self.recognizer.faces(frame) if usable else []
                with self._admin_lock:
                    self._camera_samples.append({
                        "timestamp": started,
                        "usable": usable,
                        "brightness": brightness,
                        "faces": len(faces),
                    })

                enrolling = self._process_enrollment_frame(frame, faces, started)
                if enrolling:
                    self._camera_state = "busy"
                    self._current_child_id = None
                    # Suspende débito de quota e bloqueios enquanto o cadastro facial estiver ativo
                    self.engine.policy.pause()
                    elapsed = time.monotonic() - started
                    time.sleep(max(0.0, 0.4 - elapsed))
                    continue

                self._camera_state = "ready"
                if not usable:
                    self._camera_state = "offline"
                    LOG.error("Falha de captura: a câmera forneceu quadro preto ou sem contraste")
                    candidate = None
                elif enrollments_ready and state in {SessionState.ACTIVE, SessionState.LOCKED} and len(faces) == 1:
                    vector = self.recognizer.features(frame, faces[0])
                    candidate, _score = self.recognizer.identify(vector, self.references)
                else:
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
    parser.add_argument("--admin-group", default="wheel,sudo")
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

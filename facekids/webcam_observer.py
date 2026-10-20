"""Opt-in webcam observer for the FACE ACCESS GATE DEMO only.

IMPORTANT: Reads the existing SQLite in read-only mode. No quotas are written.
Never locks or unlocks Windows, does not store video, and is NOT liveness-safe.
Tk widgets must be managed by the main thread; this worker uses a Queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from queue import Queue, Full
import os
import sqlite3
import threading
import time

from .recognition import Recognizer


@dataclass(frozen=True)
class Enrollments:
    names: dict[int, str]
    balances: dict[int, float]
    embeddings: list[tuple[int, object]]
    unenrolled: tuple[str, ...]


def load_enrollments(database: Path) -> Enrollments:
    """Read the account's existing enrollments; never create a fresh database."""
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            "Nenhum cadastro encontrado. Cadastre os filhos e rostos pelo painel "
            "na mesma conta Windows em que executará a demonstração."
        )
    import numpy as np
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        today = date.today().isoformat()
        rows = connection.execute(
            """SELECT p.id,p.name,p.daily_limit_seconds,
                      COALESCE(u.seconds,0),COALESCE(b.seconds,0)
               FROM people p
               LEFT JOIN daily_usage u ON u.person_id=p.id AND u.day=?
               LEFT JOIN daily_bonus b ON b.person_id=p.id AND b.day=?
               ORDER BY p.id""",
            (today, today)
        ).fetchall()
        raw = connection.execute("SELECT person_id,vector FROM embeddings").fetchall()
    finally:
        connection.close()

    names = {int(pid): str(name) for pid,name,*_ in rows}
    if not names:
        raise ValueError("Cadastre pelo menos uma criança no painel.")
    balances = {int(pid): max(0.0, float(limit)+float(bonus)-float(used))
                for pid,_,limit,used,bonus in rows}
    features = []
    for pid, blob in raw:
        if pid not in names:
            continue
        vector = np.frombuffer(blob, dtype=np.float32)
        if vector.size == 128 and np.all(np.isfinite(vector)) and np.linalg.norm(vector) > 0:
            features.append((int(pid), vector.copy()))
    if not features:
        raise ValueError("Nenhum rosto facial SFace cadastrado; use 'Cadastrar rosto' no painel.")
    enrolled = {pid for pid,_ in features}
    missing = tuple(name for pid,name in names.items() if pid not in enrolled)
    return Enrollments(names, balances, features, missing)


def classify_face_sample(face_count: int, matched_id: int | None):
    """Return an event understood by GateModel; ambiguous frames never authorize."""
    if face_count < 0:
        raise ValueError("Invalid face count")
    if face_count == 0:
        return None
    if face_count > 1:
        return "multiple"
    if matched_id is None:
        return "unknown"
    if type(matched_id) is not int or matched_id <= 0:
        raise ValueError("Invalid matched id")
    return matched_id


class WebcamObserver:
    def __init__(self, models: Path, embeddings, *, camera_index=0,
                 interval=2.0, max_queue=6, observer_factory=Recognizer,
                 camera_factory=None):
        if not isinstance(camera_index, int) or camera_index < 0:
            raise ValueError("Índice de webcam inválido.")
        if not 0.5 <= interval <= 10:
            raise ValueError("Intervalo de leitura permitido: 0,5 a 10 segundos.")
        self.models = Path(models)
        self.embeddings = embeddings
        self.camera_index = camera_index
        self.interval = float(interval)
        self.observer_factory = observer_factory
        self.camera_factory = camera_factory
        self.events = Queue(maxsize=max_queue)
        self.stop_event = threading.Event()
        self.thread = None

    def _emit(self, observation, note):
        # Only the latest few observations are retained; never buffer images.
        try:
            self.events.put_nowait((observation, note))
        except Full:
            try:
                self.events.get_nowait()
            except Exception:
                pass
            try:
                self.events.put_nowait((observation, note))
            except Full:
                pass

    def start(self):
        if self.thread is not None:
            raise RuntimeError("Webcam observer already started")
        self.thread = threading.Thread(target=self._run, name="facekids-webcam", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        cap = None
        try:
            recognizer = self.observer_factory(self.models)
            import cv2
            factory = self.camera_factory or (lambda index: cv2.VideoCapture(
                index, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY))
            cap = factory(self.camera_index)
            if not cap.isOpened():
                raise OSError("Não foi possível abrir a webcam.")
            while not self.stop_event.is_set():
                started = time.monotonic()
                ok, image = cap.read()
                if not ok or image is None:
                    raise OSError("Falha de captura da webcam.")
                faces = recognizer.faces(image)
                if len(faces) == 1:
                    feature = recognizer.features(image, faces[0])
                    matched, score = recognizer.identify(feature, self.embeddings)
                    event = classify_face_sample(1, matched)
                    note = ("Rosto reconhecido" if event is not None and event != "unknown"
                            else "Rosto não identificado")
                else:
                    event = classify_face_sample(len(faces), None)
                    note = ("Nenhuma face detectada" if event is None
                            else "Mais de uma face no quadro")
                self._emit(event, note)
                self.stop_event.wait(max(0.0, self.interval - (time.monotonic()-started)))
        except Exception as error:
            # Never expose image contents or biometric vectors in logs.
            self._emit("camera_error", f"Webcam indisponível: {type(error).__name__}.")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

"""Diagnostic-only face matching while the CURRENT Windows session is locked.

No Windows login, unlocking, Credential Provider, service, file writes,
face-image storage or network access. Reads the existing adult pilot
enrollment read-only and discards camera frames immediately.
WTS reports are diagnostic, not trusted Secure Desktop provenance.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import sqlite3
import time

import numpy as np

from .hardware_camera_probe import process_session_id, live_session_state
from .parent_face_pilot import PROFILE_NAME, REQUIRED_SAMPLES, pilot_database
from .recognition import Recognizer
from .windows_session_diagnostic import LockView


class Status(str, Enum):
    NOT_ENOUGH_LOCKED_SAMPLES = "INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES"
    NO_LOCKED_FRAMES = "NO_USABLE_LOCKED_FRAMES"
    NO_MATCH = "LOCKED_FRAMES_WITHOUT_MATCH"
    MATCH_DIAGNOSTIC = "MATCH_OBSERVED_DURING_WIN_L_DIAGNOSTIC_ONLY"


def load_adult_templates_read_only(database: Path) -> tuple[int, list[tuple[int, np.ndarray]]]:
    """Never create/update enrollment or access children's enrollment storage."""
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Cadastro do piloto adulto ausente. Execute Testar-Meu-Rosto.ps1.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT id FROM people WHERE name=?", (PROFILE_NAME,)
        ).fetchone()
        if row is None:
            raise ValueError("O cadastro do responsavel nao existe neste banco.")
        person_id = int(row[0])
        rows = connection.execute(
            "SELECT vector FROM embeddings WHERE person_id=? ORDER BY id",
            (person_id,)
        ).fetchall()
        if len(rows) != REQUIRED_SAMPLES:
            raise ValueError("Cadastro do responsavel incompleto; faca novo cadastro.")
        vectors: list[tuple[int, np.ndarray]] = []
        for (blob,) in rows:
            if blob is None or len(blob) != 512:
                raise ValueError("Vetores do cadastro em formato invalido.")
            vector = np.frombuffer(blob, dtype=np.float32)
            if (vector.size != 128 or not np.isfinite(vector).all()
                    or float(np.linalg.norm(vector)) <= 1e-8):
                raise ValueError("Vetor invalido; necessario refazer o cadastro.")
            vectors.append((person_id, vector.copy()))
        return person_id, vectors
    finally:
        connection.close()


@dataclass
class LockedFaceStats:
    """All decisions are diagnostics only, never Windows authorization."""
    adult_id: int
    total: int = 0
    locked_samples: int = 0
    locked_frames: int = 0
    single_face: int = 0
    matching_frames: int = 0
    confirmation_windows: int = 0
    camera_errors: int = 0
    unknown_samples: int = 0
    consecutive: int = 0
    first_match_at: float = 0.0

    def record(self, before: LockView, after: LockView, *,
               frame_ok: bool, face_count: int = 0,
               candidate_id: int | None = None,
               now: float = 0.0) -> None:
        self.total += 1
        if before is LockView.UNKNOWN or after is LockView.UNKNOWN:
            self.unknown_samples += 1
        if not frame_ok:
            self.camera_errors += 1
        # Both WTS queries must report locked: exclude frames from a
        # lock/unlock transition or any missing/unknown session state.
        if not (before is LockView.LOCKED and after is LockView.LOCKED):
            self.consecutive = 0
            return
        self.locked_samples += 1
        if not frame_ok:
            self.consecutive = 0
            return
        self.locked_frames += 1
        if face_count != 1:
            self.consecutive = 0
            return
        self.single_face += 1
        if candidate_id != self.adult_id:
            self.consecutive = 0
            return
        self.matching_frames += 1
        if self.consecutive and (now < self.first_match_at or now - self.first_match_at > 5.0):
            self.consecutive = 0
        if not self.consecutive:
            self.first_match_at = now
        self.consecutive += 1
        if self.consecutive == 3:
            self.confirmation_windows += 1

    def status(self) -> Status:
        if self.locked_samples < 5:
            return Status.NOT_ENOUGH_LOCKED_SAMPLES
        if self.confirmation_windows:
            return Status.MATCH_DIAGNOSTIC
        if not self.locked_frames:
            return Status.NO_LOCKED_FRAMES
        return Status.NO_MATCH


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostico de reconhecimento do responsavel durante Win+L (SEM LOGIN)")
    parser.add_argument("--database", type=Path, default=pilot_database())
    parser.add_argument("--models", type=Path, default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args(argv)
    if not 20 <= args.duration <= 300 or not 0 <= args.camera_index <= 10:
        parser.error("duration precisa ser 20..300, camera-index 0..10")
    if os.name != "nt":
        parser.error("Diagnostico exige Windows 10/11")
    import cv2

    adult_id, templates = load_adult_templates_read_only(args.database)
    recognizer = Recognizer(args.models)
    session_id = process_session_id()
    capture = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    if not capture.isOpened():
        capture.release()
        print("NO_CAMERA: a webcam nao abriu.")
        return 3

    stats = LockedFaceStats(adult_id)
    print("DIAGNOSTICO DE RECONHECIMENTO COM Win+L - NAO DESBLOQUEIA WINDOWS", flush=True)
    print("Pressione Win+L; fique diante da webcam durante 40-60 segundos.", flush=True)
    print("Depois desbloqueie com PIN/senha normal e leia o resumo no terminal.", flush=True)
    print("Dados biometricos lidos do banco adulto somente leitura; fotos nao serao gravadas.", flush=True)
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.duration:
            begun = time.monotonic()
            try:
                before = live_session_state(session_id)
            except (OSError, RuntimeError):
                before = LockView.UNKNOWN
            frame_ok, frame = capture.read()
            face_count = 0
            candidate = None
            if frame_ok and frame is not None and before is LockView.LOCKED:
                try:
                    faces = recognizer.faces(frame)
                    face_count = len(faces)
                    if face_count == 1:
                        embedding = recognizer.features(frame, faces[0])
                        candidate, _ = recognizer.identify(embedding, templates)
                except (cv2.error, ValueError, RuntimeError):
                    # Recognition failed; deny any positive observation.
                    face_count = 0
                    candidate = None
            frame = None
            try:
                after = live_session_state(session_id)
            except (OSError, RuntimeError):
                after = LockView.UNKNOWN
            stats.record(before, after, frame_ok=bool(frame_ok), face_count=face_count,
                         candidate_id=candidate, now=time.monotonic())
            if stats.total % 10 == 0:
                print(f"sample={stats.total} wts={after.value} "
                      f"locked_frames={stats.locked_frames} "
                      f"locked_matches={stats.matching_frames}", flush=True)
            time.sleep(max(0.0, 1.0 - (time.monotonic() - begun)))
    except KeyboardInterrupt:
        print("Interrompido pelo usuario.", flush=True)
    finally:
        capture.release()

    print(f"Resumo: total={stats.total}; amostras_lock={stats.locked_samples}; "
          f"frames_lock={stats.locked_frames}; um_rosto={stats.single_face}; "
          f"matches={stats.matching_frames}; confirmacoes={stats.confirmation_windows}; "
          f"erros_camera={stats.camera_errors}; wts_desconhecido={stats.unknown_samples}",
          flush=True)
    print(stats.status().value, flush=True)
    print("Nao prova autenticacao no LogonUI, liveness ou acesso ao Secure Desktop.", flush=True)
    return 0 if stats.status() is Status.MATCH_DIAGNOSTIC else 4


if __name__ == "__main__":
    raise SystemExit(main())

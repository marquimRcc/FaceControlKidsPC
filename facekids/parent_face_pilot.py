"""Adult-only opt-in webcam enrollment and live recognition pilot.

This is a local functional demo, NOT Windows sign-in or anti-spoofing.
No photos/videos are saved or sent. Facial embeddings are sensitive data:
stored only under the current Windows account's LOCALAPPDATA in a dedicated
test database. They are NOT protected by the future LocalSystem broker ACL.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import time
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .recognition import Recognizer
from .storage import Storage

PROFILE_NAME = "Responsavel - Teste"
REQUIRED_SAMPLES = 12


def pilot_database() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and base:
        return Path(base) / "FaceKids" / "piloto-responsavel" / "piloto.sqlite3"
    return Path.home() / ".local" / "share" / "FaceKids" / "piloto-responsavel" / "piloto.sqlite3"


class Outcome(str, Enum):
    NO_FACE = "SEM_ROSTO"
    MANY_FACES = "MULTIPLOS_ROSTOS"
    UNKNOWN = "NAO_IDENTIFICADO"
    VERIFYING = "CONFIRMANDO"
    VERIFIED_DEMO = "IDENTIFICADO_DEMO"


@dataclass
class RecognitionWindow:
    """Three independent observations, all of the SAME expected adult."""
    adult_id: int
    count: int = 0
    first: float = 0.0
    last: float = 0.0

    def observe(self, number_faces: int, candidate: int | None, now: float) -> Outcome:
        if number_faces == 0:
            self.count = 0
            return Outcome.NO_FACE
        if number_faces != 1:
            self.count = 0
            return Outcome.MANY_FACES
        if candidate != self.adult_id:
            self.count = 0
            return Outcome.UNKNOWN
        if self.count and (now < self.last or now - self.first > 3.0):
            self.count = 0
        if not self.count:
            self.first = now
        self.last = now
        self.count = min(self.count + 1, 3)
        return Outcome.VERIFIED_DEMO if self.count == 3 else Outcome.VERIFYING


def _valid_features(vector: np.ndarray) -> bool:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    return (values.size == 128 and bool(np.isfinite(values).all())
            and bool(np.linalg.norm(values) > 1e-8))


def replace_templates(store: Storage, adult_id: int, vectors: list[np.ndarray]) -> None:
    """Atomic replacement only after complete adult enrollment."""
    if len(vectors) != REQUIRED_SAMPLES or any(not _valid_features(v) for v in vectors):
        raise ValueError("Cadastro incompleto: nenhum template anterior foi alterado.")
    payload = [(adult_id, np.asarray(v, dtype=np.float32).reshape(128).tobytes())
               for v in vectors]
    with store.db:
        if store.db.execute("SELECT 1 FROM people WHERE id=?", (adult_id,)).fetchone() is None:
            raise KeyError(adult_id)
        store.db.execute("DELETE FROM embeddings WHERE person_id=?", (adult_id,))
        store.db.executemany(
            "INSERT INTO embeddings(person_id,vector) VALUES (?,?)", payload
        )


def _open_camera(index: int):
    import cv2
    if os.name == "nt":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    else:
        backends = [cv2.CAP_ANY]
    for backend in backends:
        cam = cv2.VideoCapture(index, backend)
        if cam.isOpened():
            return cam
        cam.release()
    raise RuntimeError("Nao foi possivel abrir a webcam; feche outros aplicativos de camera.")


def _frame_text(frame, lines: list[str]):
    """Text only on an in-memory OpenCV preview; never save the frame."""
    import cv2
    for index, line in enumerate(lines):
        cv2.putText(frame, line, (12, 32 + index * 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.68, (40, 235, 230), 2)
    cv2.imshow("FaceKids - Responsavel (ESC ou Q encerra)", frame)
    key = cv2.waitKey(40) & 0xFF
    return key not in (ord("q"), 27)


def _collect(camera, recognizer: Recognizer, samples: int = REQUIRED_SAMPLES):
    vectors: list[np.ndarray] = []
    next_sample = time.monotonic()
    print("CADASTRO: olhe para a webcam. Mova a cabeca levemente e altere a expressao.")
    print("Somente um rosto no quadro. ESC/Q cancela sem salvar um cadastro parcial.")
    while len(vectors) < samples:
        ok, frame = camera.read()
        if not ok or frame is None:
            raise RuntimeError("A webcam parou de fornecer quadros.")
        faces = recognizer.faces(frame)
        now = time.monotonic()
        if len(faces) == 1 and now >= next_sample:
            v = recognizer.features(frame, faces[0])
            if _valid_features(v):
                vectors.append(np.asarray(v, dtype=np.float32).reshape(128).copy())
                next_sample = now + 0.55
        if not _frame_text(frame, [
            "CADASTRO ADULTO - NAO E LOGIN WINDOWS",
            f"Amostras: {len(vectors)}/{samples}",
            "Um rosto apenas; ESC ou Q cancela",
        ]):
            return None
    return vectors


def _verify(camera, recognizer: Recognizer, store: Storage,
            adult_id: int, seconds: int) -> None:
    refs = [(pid, vector) for pid, vector in store.embeddings() if pid == adult_id]
    if len(refs) != REQUIRED_SAMPLES:
        raise RuntimeError("Cadastro facial adulto incompleto.")
    window = RecognitionWindow(adult_id)
    print("TESTE REAL: saia do enquadramento e volte; depois vire levemente o rosto.")
    print("Sem liveness; uma foto ou video ainda pode enganar este prototipo.")
    print("Nenhum bloqueio ou desbloqueio Windows sera executado.")
    last_state = None
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ok, frame = camera.read()
        if not ok or frame is None:
            raise RuntimeError("Falha ao ler a camera na validacao.")
        faces = recognizer.faces(frame)
        candidate = None
        if len(faces) == 1:
            vector = recognizer.features(frame, faces[0])
            candidate, _ = recognizer.identify(vector, refs)
        result = window.observe(len(faces), candidate, time.monotonic())
        if result != last_state:
            print("VALIDACAO:", result.value)
            last_state = result
        if not _frame_text(frame, [
            "PILOTO - RECONHECIMENTO FACIAL",
            f"Estado: {result.value}",
            "NAO AUTORIZA LOGIN - ESC/Q encerra",
        ]):
            break


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Cadastro e validacao real do rosto do responsavel; sem login Windows."
    )
    parser.add_argument("--database", type=Path, default=pilot_database())
    parser.add_argument("--models", type=Path, default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--verify-seconds", type=int, default=60)
    parser.add_argument("--re-enroll", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.camera_index <= 10 or not 10 <= args.verify_seconds <= 300:
        parser.error("Camera de 0 a 10; validacao de 10 a 300 segundos")
    if os.name != "nt":
        parser.error("Piloto presencial disponivel apenas no Windows.")
    import cv2
    store = Storage(args.database)
    camera = None
    try:
        person = store.get_person(PROFILE_NAME)
        if person is None:
            adult_id = store.add_person(PROFILE_NAME, 120)
            enrolled = 0
        else:
            adult_id = person[0]
            enrolled = store.enrollment_count(adult_id)
        print("PILOTO ADULTO - FaceControlKidsPC")
        print("Dados locais:", args.database)
        print("Banco separado dos perfis e quotas das criancas.")
        print("Armazena APENAS vetores faciais locais, nao fotos ou videos.")
        print("Nao tem protecao de biometricos do servico Windows.")
        recognizer = Recognizer(args.models)
        camera = _open_camera(args.camera_index)
        if enrolled == 0 or args.re_enroll:
            print("Abrindo webcam para cadastrar 12 amostras do seu rosto...")
            collected = _collect(camera, recognizer)
            if collected is None:
                print("Cancelado: nenhum cadastro parcial foi gravado.")
                return 2
            replace_templates(store, adult_id, collected)
            print("Cadastro completo: 12 vetores locais gravados.")
        else:
            print(f"Cadastro anterior encontrado ({enrolled} amostras); validando.")
            if enrolled != REQUIRED_SAMPLES:
                print("Para substituir cadastro incompleto, use --re-enroll.")
                return 3
        _verify(camera, recognizer, store, adult_id, args.verify_seconds)
        print("Teste finalizado. O login do Windows nao foi alterado.")
        return 0
    finally:
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

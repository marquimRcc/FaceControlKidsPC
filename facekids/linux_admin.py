"""Administração local do FaceKids Linux; destinada à conta responsável/root."""
from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import numpy as np

from .child_quota_pilot import provision_three_children
from .linux_runtime import protected_data_path, warm_up_camera
from .parent_face_pilot import (
    REQUIRED_SAMPLES,
    _open_camera,
    _valid_features,
    replace_templates,
)
from .recognition import Recognizer
from .storage import Storage


def enroll_child(store: Storage, child: int, models: Path, camera_index: int) -> bool:
    """Cadastra vetores na memória; não grava fotografia ou vídeo."""
    import cv2

    people = provision_three_children(store)
    ordered = sorted(people)
    child_id = ordered[child - 1]
    recognizer = Recognizer(models)
    camera = _open_camera(camera_index)
    warm_up_camera(camera)
    vectors = []
    next_sample = time.monotonic()
    print(f"Cadastro da criança {child}: {REQUIRED_SAMPLES} amostras locais.")
    print("Mantenha apenas um rosto no quadro. ESC ou Q cancela sem alterar o cadastro.")
    try:
        while len(vectors) < REQUIRED_SAMPLES:
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("A câmera parou de fornecer quadros")
            if float(np.mean(frame)) < 4.0 or float(np.std(frame)) < 2.0:
                raise RuntimeError("A câmera está fornecendo imagem preta ou sem contraste")
            faces = recognizer.faces(frame)
            now = time.monotonic()
            if len(faces) == 1 and now >= next_sample:
                vector = recognizer.features(frame, faces[0])
                if _valid_features(vector):
                    vectors.append(np.asarray(vector, dtype=np.float32).reshape(128).copy())
                    next_sample = now + 0.55
            cv2.putText(
                frame, f"FaceKids Linux - Crianca {child}: {len(vectors)}/{REQUIRED_SAMPLES}",
                (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (25, 240, 235), 2,
            )
            cv2.imshow("FaceKids Linux - cadastro", frame)
            if cv2.waitKey(40) & 0xFF in (ord("q"), 27):
                return False
        replace_templates(store, child_id, vectors)
        return True
    finally:
        camera.release()
        cv2.destroyAllWindows()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administração do FaceKids no Linux")
    parser.add_argument("--database", type=Path, default=protected_data_path())
    parser.add_argument("--models", type=Path, default=Path("/usr/lib/facekids/models"))
    parser.add_argument("--camera", type=int, default=0)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup")
    enrollment = commands.add_parser("enroll")
    enrollment.add_argument("child", type=int, choices=(1, 2, 3))
    commands.add_parser("status")
    limit = commands.add_parser("set-limit")
    limit.add_argument("child", type=int, choices=(1, 2, 3))
    limit.add_argument("minutes", type=int)
    bonus = commands.add_parser("bonus")
    bonus.add_argument("child", type=int, choices=(1, 2, 3))
    bonus.add_argument("minutes", type=int)
    curfew = commands.add_parser("curfew")
    curfew.add_argument("start")
    curfew.add_argument("end")
    commands.add_parser("disable-curfew")
    erase = commands.add_parser("erase-face")
    erase.add_argument("child", type=int, choices=(1, 2, 3))
    return parser


def _person_id(store: Storage, child: int) -> int:
    people = provision_three_children(store)
    return sorted(people)[child - 1]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.camera <= 32:
        raise SystemExit("Câmera deve estar entre 0 e 32")
    store = Storage(args.database)
    try:
        provision_three_children(store)
        if args.command == "setup":
            print(f"Banco inicializado: {args.database}")
        elif args.command == "enroll":
            if not enroll_child(store, args.child, args.models, args.camera):
                return 2
            print(f"Cadastro concluído para criança {args.child}")
        elif args.command == "status":
            today = date.today().isoformat()
            for index, (person_id, name, _limit) in enumerate(store.people(), 1):
                print(
                    f"{index}: {name}; amostras={store.enrollment_count(person_id)}; "
                    f"restante={int(store.remaining(person_id, today)) // 60} min"
                )
        elif args.command == "set-limit":
            store.set_daily_limit(_person_id(store, args.child), args.minutes)
        elif args.command == "bonus":
            store.add_bonus(_person_id(store, args.child), args.minutes)
        elif args.command == "curfew":
            store.set_curfew_config(True, args.start, args.end)
            store.is_curfew_active("12:00")  # valida formato imediatamente
        elif args.command == "disable-curfew":
            _enabled, start, end = store.get_curfew_config()
            store.set_curfew_config(False, start, end)
        elif args.command == "erase-face":
            removed = store.remove_embeddings(_person_id(store, args.child))
            print(f"Vetores removidos: {removed}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

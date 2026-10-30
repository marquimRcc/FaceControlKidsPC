"""Opt-in Windows facial enrollment + screen-time test for a shared Filhos account.

The local SQLite file is per-Windows-user and can be edited by that user.
This is a pilot, NOT a protected parental-control installation.
Photos/videos are kept only in camera memory; only local face embeddings
are saved after successful explicit enrollment. Do not add them to Git.
"""
from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import time

from .child_quota_pilot import ChildQuotaEngine, PilotEvent
from .parent_face_pilot import (
    REQUIRED_SAMPLES, _open_camera, _valid_features, replace_templates,
)
from .recognition import Recognizer
from .session import SessionState, current_session_state
from .storage import Storage
from .vm_lab_paths import vm_lab_root

def child_pilot_database() -> Path:
    vm_root = vm_lab_root()
    if vm_root is not None:
        return vm_root / "data" / "criancas.sqlite3"
    shared = Path("C:/ProgramData/FaceKids/criancas.sqlite3")
    if shared.exists():
        return shared
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "FaceKids" / "piloto-filhos" / "criancas.sqlite3"
    return Path.home() / ".local" / "share" / "FaceKids" / "piloto-filhos" / "criancas.sqlite3"


def windows_token_user() -> str:
    """Get actual Windows account from OS, not spoofable USERNAME env var."""
    if os.name != "nt":
        raise RuntimeError("Bloqueio Windows exige Windows 10/11")
    import ctypes
    from ctypes import wintypes
    name = ctypes.create_unicode_buffer(256)
    length = wintypes.DWORD(len(name))
    func = ctypes.windll.advapi32.GetUserNameW
    func.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    func.restype = wintypes.BOOL
    if not func(name, ctypes.byref(length)) or not name.value:
        raise RuntimeError("Nao foi possivel confirmar a conta pelo Windows")
    return name.value


def validate_real_lock(os_type: str, account: str, *, confirmed: bool) -> None:
    if not confirmed or os_type != "nt" or account.casefold() != "filhos":
        raise PermissionError(
            "Bloqueio real autorizado APENAS manualmente na conta Windows Filhos. "
            "Nunca na conta MarcosMiniPC."
        )


def _child_id(store: Storage, index: int) -> int:
    if type(index) is not int or index <= 0:
        raise ValueError("O perfil precisa ter ID positivo.")
    for p in store.people():
        if p[0] == index:
            return int(p[0])
    raise KeyError(f"Perfil {index} nao encontrado; cadastre-o antes.")


def _enroll(store: Storage, index: int, models: Path, camera: int):
    import cv2
    import numpy as np
    target = _child_id(store, index)
    cap = _open_camera(camera)
    recognizer = Recognizer(models)
    vectors = []
    enroll_samples = []
    next_frame = time.monotonic()
    best_enroll_frame = None
    best_enroll_face = None
    print(f"CADASTRO CONSENTIDO: perfil {index}, {REQUIRED_SAMPLES} amostras.")
    print("Um rosto por vez. Q/ESC cancela SEM substituir cadastro anterior.")
    cv2.namedWindow("FaceKids - cadastro acompanhado", cv2.WINDOW_AUTOSIZE)
    try:
        cv2.setWindowProperty("FaceKids - cadastro acompanhado", cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass
    try:
        while len(vectors) < REQUIRED_SAMPLES:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("A webcam deixou de fornecer quadros.")
            clean_frame = frame.copy()
            preview = frame.copy()
            faces = recognizer.faces(clean_frame)
            now = time.monotonic()
            if len(faces) == 1:
                fx, fy, fw, fh = int(faces[0][0]), int(faces[0][1]), int(faces[0][2]), int(faces[0][3])
                # Desenha retangulo verde visual apenas na visualizacao (preview)
                cv2.rectangle(preview, (fx, fy), (fx + fw, fy + fh), (50, 230, 80), 2)
                if now >= next_frame:
                    vector = recognizer.features(clean_frame, faces[0])
                    if _valid_features(vector):
                        vectors.append(np.asarray(vector, dtype=np.float32).reshape(128).copy())
                        best_enroll_frame = clean_frame.copy()
                        best_enroll_face = faces[0]
                        # Recorta o rosto da imagem limpa (SEM o retangulo verde da tela)
                        H, W = clean_frame.shape[:2]
                        x, y, w, h = fx, fy, fw, fh
                        mx, my = int(w * 0.30), int(h * 0.30)
                        x1, y1 = max(0, x - mx), max(0, y - my)
                        x2, y2 = min(W, x + w + mx), min(H, y + h + my)
                        cropped = clean_frame[y1:y2, x1:x2].copy()
                        enroll_samples.append(cropped)
                        next_frame = now + 0.55
            cv2.putText(preview, f"FaceKids PERFIL {index} - {len(vectors)}/{REQUIRED_SAMPLES} fotos",
                        (15,35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (25,240,235),2)
            cv2.putText(preview,"Mova levemente o rosto. Q ou ESC cancela.",
                        (15,68), cv2.FONT_HERSHEY_SIMPLEX, 0.56,(25,240,235),2)
            cv2.imshow("FaceKids - cadastro acompanhado", preview)
            if cv2.waitKey(40) & 0xFF in (ord("q"),27):
                print("Cadastro cancelado; nenhum dado parcial gravado.")
                return False
        # Salva vetores biometricos
        replace_templates(store, target, vectors)

        # Salva todas as 12 fotos amostradas no disco e no SQLite
        from .avatar_utils import get_child_samples_dir, select_child_sample_photo
        samples_dir = get_child_samples_dir(target)
        samples_dir.mkdir(parents=True, exist_ok=True)
        for old_f in samples_dir.glob("amostra_*.jpg"):
            try:
                old_f.unlink()
            except Exception:
                pass

        if hasattr(store, "clear_profile_photos"):
            store.clear_profile_photos(target)

        for i, sample_crop in enumerate(enroll_samples, start=1):
            sample_p = samples_dir / f"amostra_{i}.jpg"
            cv2.imwrite(str(sample_p), sample_crop)
            try:
                ok_enc, buf_enc = cv2.imencode(".jpg", sample_crop)
                if ok_enc and hasattr(store, "add_profile_photo"):
                    store.add_profile_photo(target, buf_enc.tobytes(), select=(i == 1))
            except Exception:
                pass

        # Define a primeira foto como a foto oficial inicial
        if enroll_samples:
            try:
                select_child_sample_photo(target, enroll_samples[0], store=store, sample_index=1)
            except Exception:
                pass
        print(f"CADASTRO_CONCLUIDO: perfil {index}, {len(vectors)} modelos e {len(enroll_samples)} fotos salvas com sucesso.")
        return True
    finally:
        cap.release()
        cv2.destroyAllWindows()


def _status(store: Storage, engine: ChildQuotaEngine):
    day = date.today().isoformat()
    for pid, alias in engine.people.items():
        print(f"{alias}: {store.enrollment_count(pid)} amostras; "
              f"{int(store.remaining(pid,day))//60} minutos restantes hoje.")


def _monitor(store: Storage, engine: ChildQuotaEngine,
             models: Path, camera: int, seconds: int, real_lock: bool):
    import cv2
    if real_lock:
        # Must be the current OS process identity, not a process argument.
        validate_real_lock(os.name, windows_token_user(), confirmed=True)
        from .locker import lock_current_session
    else:
        lock_current_session = None
    references = [(pid,v) for pid,v in store.embeddings() if pid in engine.people]
    enrolled = {pid for pid,_ in references}
    if not enrolled:
        raise RuntimeError("Nenhum rosto infantil cadastrado neste perfil Windows.")
    recognizer = Recognizer(models)
    cap = None
    end = time.monotonic() + seconds
    last = None
    print("MONITOR FACEKIDS: nao e login do Windows. Ctrl+C encerra.")
    print("Quotas em SQLite local modificavel; teste inicial, NAO imposicao segura.")
    print("LockWorkStation:", "ATIVADO NA CONTA FILHOS" if real_lock else "DESATIVADO - DRY RUN")
    try:
        while time.monotonic() < end:
            started = time.monotonic()
            state = current_session_state()
            candidate = None
            if state is SessionState.ACTIVE:
                try:
                    if cap is None:
                        cap = _open_camera(camera)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        cap.release()
                        cap = None
                    else:
                        faces = recognizer.faces(frame)
                        if len(faces) == 1:
                            features = recognizer.features(frame, faces[0])
                            candidate, _ = recognizer.identify(features, references)
                    frame = None
                except (cv2.error, ValueError, RuntimeError) as exc:
                    print("Camera ou reconhecimento indisponivel:", exc)
                    if cap is not None:
                        cap.release()
                        cap = None
            elif cap is not None:
                cap.release()
                cap = None
            reading = engine.step(started, date.today().isoformat(), state, candidate)
            signal = (reading.event, reading.child_id)
            if signal != last or reading.event is PilotEvent.QUOTA_EXHAUSTED:
                alias = engine.people.get(reading.child_id, "-")
                remaining = (int(reading.remaining_seconds)
                             if reading.remaining_seconds is not None else "-")
                print(f"{reading.event.value}: {alias}, saldo {remaining}s",flush=True)
                last = signal
            if reading.lock_candidate:
                if real_lock:
                    # Recheck OS account at the moment of the requested lock.
                    validate_real_lock(os.name, windows_token_user(), confirmed=True)
                    if current_session_state() is SessionState.ACTIVE:
                        print("Quota esgotada; solicitando Win+L nesta conta Filhos.")
                        lock_current_session()
                else:
                    print("DRY_RUN_WIN_L: quota esgotada. Nenhuma sessao bloqueada.")
            time.sleep(max(0, 1.0 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("Monitor parado pelo responsavel.")
    finally:
        if cap is not None:
            cap.release()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="FaceKids: piloto de um ou mais perfis (sem instalador)")
    parser.add_argument("--database", type=Path, default=child_pilot_database())
    parser.add_argument("--models", type=Path,
                        default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--camera", type=int, default=0)
    sub = parser.add_subparsers(dest="action", required=True)
    enroll = sub.add_parser("enroll", help="Cadastrar uma crianca com responsavel presente")
    enroll.add_argument("child", type=int, help="ID de qualquer perfil cadastrado")
    create = sub.add_parser("add-profile", help="Adicionar mais um perfil de teste")
    create.add_argument("alias", type=str)
    create.add_argument("--minutes", type=int, default=120)
    sub.add_parser("status")
    monitor = sub.add_parser("monitor")
    monitor.add_argument("--seconds", type=int, default=90)
    monitor.add_argument("--real-lock", action="store_true",
                         help="Somente Filhos, pedido manual de Win+L por quota")
    monitor.add_argument("--confirm-real-lock", action="store_true")
    erase = sub.add_parser("erase", help="Apagar apenas biometria do perfil indicado")
    erase.add_argument("child", type=int, help="ID de qualquer perfil cadastrado")
    args = parser.parse_args(argv)
    if os.name != "nt" or not 0 <= args.camera <= 10:
        parser.error("Piloto requer Windows e camera 0..10")
    if args.action == "monitor" and not 10 <= args.seconds <= 3600:
        parser.error("monitor --seconds deve ser 10..3600")
    if args.action == "monitor" and args.real_lock:
        validate_real_lock(os.name, windows_token_user(), confirmed=args.confirm_real_lock)
    store = Storage(args.database)
    try:
        if args.action == "add-profile":
            alias = args.alias.strip()
            if not 1 <= len(alias) <= 50 or not 1 <= args.minutes <= 1440:
                parser.error("Apelido: 1..50 caracteres; minutos: 1..1440")
            person_id = store.add_person(alias, args.minutes)
            print(f"PERFIL_CRIADO: id={person_id}, alias={alias}")
            return 0
        engine = ChildQuotaEngine(store)
        if args.action == "enroll":
            return 0 if _enroll(store, args.child, args.models, args.camera) else 2
        if args.action == "erase":
            count = store.remove_embeddings(_child_id(store, args.child))
            print(f"PERFIL_{args.child}_APAGADO: {count} vetores removidos; quotas mantidas.")
            return 0
        if args.action == "status":
            _status(store, engine)
            return 0
        _monitor(store, engine, args.models, args.camera, args.seconds, args.real_lock)
        _status(store, engine)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

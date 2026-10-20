"""Opt-in Windows 10/11 Win+L camera diagnostic. No facial identity or logon.

Samples webcam frames only in process memory, never saves images,
embeddings or video. The result is NOT anti-spoof/liveness evidence.
This script cannot establish trusted capture from Secure Desktop/LogonUI.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import time
from dataclasses import dataclass
from ctypes import wintypes
from .windows_session_diagnostic import LockView, enumerate_local_sessions


@dataclass
class ProbeStats:
    samples: int = 0
    locked_samples: int = 0
    locked_frames: int = 0
    locked_nonuniform: int = 0
    camera_errors: int = 0
    unknown_sessions: int = 0

    def record(self, state: LockView, *, frame_read: bool,
               nonuniform: bool = False) -> None:
        self.samples += 1
        if not frame_read:
            self.camera_errors += 1
        if state is LockView.LOCKED:
            self.locked_samples += 1
            if frame_read:
                self.locked_frames += 1
                if nonuniform:
                    self.locked_nonuniform += 1
        if state is LockView.UNKNOWN:
            self.unknown_sessions += 1

    def outcome(self) -> str:
        if self.locked_samples < 5:
            return "INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES"
        if self.locked_nonuniform >= 3:
            return "FRAMES_DURING_WIN_L_PRELIMINARY_ONLY"
        return "NO_USABLE_LOCKED_FRAMES"


def process_session_id() -> int:
    """Ask the OS for the actual session ID; never trust user JSON."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel32.ProcessIdToSessionId
    function.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    function.restype = wintypes.BOOL
    session = wintypes.DWORD()
    if not function(os.getpid(), ctypes.byref(session)):
        raise OSError(ctypes.get_last_error(), "ProcessIdToSessionId")
    return int(session.value)


def live_session_state(session_id: int) -> LockView:
    for item in enumerate_local_sessions():
        if item.session_id == session_id:
            return item.state
    return LockView.UNKNOWN


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostico local de frames com Win+L (sem salvar imagens)."
    )
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args(argv)
    if not 10 <= args.duration <= 600 or args.camera_index < 0:
        parser.error("duration must be 10..600 seconds and camera-index >= 0")
    if os.name != "nt":
        print("Este diagnostico requer Windows 10/11.")
        return 2
    import cv2

    session = process_session_id()
    camera = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    if not camera.isOpened():
        print("NO_CAMERA: webcam indisponivel para este processo.")
        camera.release()
        return 3
    result = ProbeStats()
    print("FaceKids: apenas diagnostico Win+L na sessao atual.")
    print("Bloqueie com Win+L; aguarde o teste. Desbloqueie normalmente.")
    print("Nenhum frame ou modelo facial sera salvo, e o login nao muda.")
    beginning = time.monotonic()
    try:
        while time.monotonic() - beginning < args.duration:
            start = time.monotonic()
            ok, frame = camera.read()
            uniform = False
            if ok and frame is not None:
                _, deviations = cv2.meanStdDev(frame)
                uniform = float(deviations.mean()) >= 2.0
            else:
                ok = False
            # Release the reference before reading the Windows session state.
            frame = None
            try:
                state = live_session_state(session)
            except (OSError, RuntimeError):
                state = LockView.UNKNOWN
            result.record(state, frame_read=ok, nonuniform=uniform)
            if result.samples % 10 == 0:
                print(f"sample={result.samples} state={state.value} frame={bool(ok)}")
            time.sleep(max(0.0, 1.0 - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("Interrompido pelo usuario.")
    finally:
        camera.release()
    print(
        f"Resumo: {result.samples} amostras; {result.locked_samples} Win+L; "
        f"{result.locked_frames} frames; {result.locked_nonuniform} nao uniformes; "
        f"{result.camera_errors} erros de captura."
    )
    print(result.outcome())
    print("Nao prova captura confiavel no LogonUI, liveness ou reconhecimento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

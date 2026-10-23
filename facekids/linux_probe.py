"""Diagnóstico não biométrico da webcam e do reconhecimento no Linux."""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .linux_runtime import frame_is_usable, warm_up_camera
from .recognition import Recognizer


@dataclass(frozen=True)
class ProbeResult:
    opened: bool
    frames: int
    usable_frames: int
    faces_seen: int
    elapsed_seconds: float
    mean_brightness: float | None

    @property
    def status(self) -> str:
        if not self.opened:
            return "CAMERA_NAO_ABRIU"
        if self.frames == 0:
            return "SEM_QUADROS"
        if self.usable_frames == 0:
            return "QUADROS_PRETOS_OU_UNIFORMES"
        return "CAMERA_UTILIZAVEL"


def probe_via_daemon(admin_socket: Path, seconds: float) -> ProbeResult | None:
    """Consulta diagnóstico seguro do daemon FaceKids ativo se disponível."""
    if not admin_socket.is_socket():
        return None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(seconds + 3.0)
        client.connect(str(admin_socket))
        client.sendall((json.dumps({"op": "probe", "seconds": seconds}) + "\n").encode("utf-8"))
        buffer = b""
        while b"\n" not in buffer:
            chunk = client.recv(4096)
            if not chunk:
                break
            buffer += chunk
        client.close()
        payload = json.loads(buffer.decode("utf-8").strip())
        if payload.get("ok") and "probe" in payload:
            data = payload["probe"]
            return ProbeResult(
                opened=bool(data.get("opened", True)),
                frames=int(data.get("frames", 0)),
                usable_frames=int(data.get("usable_frames", 0)),
                faces_seen=int(data.get("faces_seen", 0)),
                elapsed_seconds=float(data.get("elapsed_seconds", seconds)),
                mean_brightness=float(data["mean_brightness"]) if data.get("mean_brightness") is not None else None,
            )
    except Exception:
        return None
    return None


def run_probe(camera_index: int, models: Path, seconds: float) -> ProbeResult:
    admin_socket = Path(os.environ.get("FACEKIDS_ADMIN_SOCKET", "/run/facekids/admin.sock"))
    daemon_result = probe_via_daemon(admin_socket, seconds)
    if daemon_result is not None:
        return daemon_result

    import cv2

    recognizer = Recognizer(models)
    capture = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
    if not capture.isOpened():
        capture.release()
        return ProbeResult(False, 0, 0, 0, 0.0, None)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    capture.set(cv2.CAP_PROP_FPS, 10)
    warm_up_camera(capture)
    started = time.monotonic()
    deadline = started + seconds
    frames = usable = faces_seen = 0
    brightness = []
    try:
        while time.monotonic() < deadline:
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            frames += 1
            brightness.append(float(np.mean(frame)))
            if not frame_is_usable(frame):
                continue
            usable += 1
            faces_seen += len(recognizer.faces(frame))
    finally:
        capture.release()
    elapsed = time.monotonic() - started
    return ProbeResult(
        True, frames, usable, faces_seen, elapsed,
        statistics.fmean(brightness) if brightness else None,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico da câmera FaceKids Linux")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    if not 0 <= args.camera <= 32 or not 1 <= args.seconds <= 30:
        parser.error("Câmera 0..32 e duração 1..30 segundos")
    result = run_probe(args.camera, args.models, args.seconds)
    fps = result.frames / result.elapsed_seconds if result.elapsed_seconds else 0.0
    print(f"STATUS={result.status}")
    print(f"FRAMES={result.frames}")
    print(f"USABLE_FRAMES={result.usable_frames}")
    print(f"FPS={fps:.2f}")
    print(f"MEAN_BRIGHTNESS={result.mean_brightness}")
    print(f"FACE_DETECTIONS={result.faces_seen}")
    return 0 if result.status == "CAMERA_UTILIZAVEL" else 2


if __name__ == "__main__":
    raise SystemExit(main())

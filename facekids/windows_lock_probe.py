"""Windows P0-1 feasibility probe: can an interactive webcam read while locked?

Read-only diagnostic. No face templates, pictures, passwords or video storage.
The user manually presses Win+L after starting this probe. It never locks or
unlocks Windows and does not require administrative privileges.
"""
from __future__ import annotations

import argparse
import csv
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .session import SessionState, current_session_state


@dataclass(frozen=True)
class ProbeSample:
    elapsed_seconds: float
    session: str
    capture_ok: bool
    frame_nonuniform: bool
    width: int
    height: int
    brightness_mean: float
    brightness_stddev: float
    error: str


def assess_sample(
    elapsed_seconds: float,
    state: SessionState,
    capture_ok: bool,
    dimensions: tuple[int, int] | None = None,
    brightness: tuple[float, float] | None = None,
    error: str = "",
) -> ProbeSample:
    """Build a privacy-preserving log row using only dimensions and light stats.

    Uniform/black frames are weak evidence even if camera.read() returns True.
    The 2.0 threshold is diagnostic only; it does NOT guarantee a usable face.
    """
    width, height = dimensions or (0, 0)
    mean, std = brightness or (0.0, 0.0)
    usable = bool(capture_ok and width > 0 and height > 0 and std >= 2.0)
    return ProbeSample(
        round(elapsed_seconds, 3),
        state.value,
        bool(capture_ok),
        usable,
        int(width), int(height),
        round(mean, 3), round(std, 3),
        str(error)[:64],
    )


def summarize(samples: list[ProbeSample]) -> dict[str, int | str]:
    locked = [s for s in samples if s.session == SessionState.LOCKED.value]
    active = [s for s in samples if s.session == SessionState.ACTIVE.value]
    unknown = [s for s in samples if s.session == SessionState.UNKNOWN.value]
    good_locked = sum(s.frame_nonuniform for s in locked)
    good_active = sum(s.frame_nonuniform for s in active)
    result = "INCONCLUSIVE"
    if len(locked) >= 5:
        result = "CAMERA_READS_DURING_LOCK" if good_locked >= 3 else "NO_USABLE_LOCKED_FRAMES"
    return {
        "result": result,
        "locked_samples": len(locked),
        "locked_nonuniform_frames": good_locked,
        "active_samples": len(active),
        "active_nonuniform_frames": good_active,
        "unknown_samples": len(unknown),
    }


def default_output_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(base) / "FaceKids" / "diagnostics" / f"winlock_probe_{stamp}.csv"


def frame_statistics(frame) -> tuple[tuple[int, int], tuple[float, float]]:
    """No frames are returned to the caller's logger."""
    import cv2
    height, width = frame.shape[:2]
    means, stds = cv2.meanStdDev(frame)
    return (width, height), (float(means.mean()), float(stds.mean()))


def observe(
    camera,
    session_fn: Callable[[], SessionState],
    elapsed: float,
    *,
    stats_fn: Callable = frame_statistics,
) -> ProbeSample:
    """Exactly one read; easy to test with injected camera and WTS state."""
    try:
        state = session_fn()
    except Exception:
        state = SessionState.UNKNOWN
    try:
        ok, frame = camera.read()
        if not ok or frame is None:
            return assess_sample(elapsed, state, False, error="camera_read_failed")
        dimensions, brightness = stats_fn(frame)
        return assess_sample(elapsed, state, True, dimensions, brightness)
    except Exception as exc:
        # Do not log exception message; drivers may include device identifiers.
        return assess_sample(elapsed, state, False, error=type(exc).__name__)


def run_probe(camera, output: Path, *, duration: float, interval: float,
              session_fn=current_session_state,
              now=time.monotonic, wait=time.sleep,
              sample_fn=observe) -> dict:
    if duration <= 0 or interval <= 0 or interval > 15:
        raise ValueError("duration must be positive; 0 < interval <= 15")
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[ProbeSample] = []
    started = now()
    with output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(ProbeSample.__dataclass_fields__))
        writer.writeheader()
        target.flush()
        while now() - started < duration:
            tick = now()
            row = sample_fn(camera, session_fn, tick - started)
            records.append(row)
            writer.writerow(asdict(row))
            target.flush()  # Keep evidence even when session stays locked.
            wait(max(0.0, interval - (now() - tick)))
    return summarize(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description="FaceKids Windows locked-webcam P0-1 diagnostic")
    parser.add_argument("--duration", type=float, default=120,
                        help="Diagnostic duration, seconds (default: 120)")
    parser.add_argument("--interval", type=float, default=1,
                        help="Frame sampling interval (default: 1)")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--backend", choices=["dshow", "msmf", "any"], default="dshow")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("This probe must run on a real Windows interactive session.")
    if args.camera < 0 or args.duration <= 0 or not 0 < args.interval <= 15:
        parser.error("Invalid camera index, duration or interval.")

    import cv2
    mode = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}[args.backend]
    camera = cv2.VideoCapture(args.camera, mode)
    if not camera.isOpened():
        raise SystemExit("Unable to open camera. Close other webcam applications.")
    output = args.output or default_output_path()
    print("FaceControlKidsPC: Windows LOCKED webcam probe (NO login/unlock changes).")
    print(f"Writing camera statistics only to: {output}")
    print("Now press Win+L, leave it locked for 30–60 s, then sign in normally.")
    print("Ctrl+C stops. The camera will be released on exit.")
    try:
        report = run_probe(camera, output, duration=args.duration, interval=args.interval)
        print("Diagnostic result:", report)
        if report["result"] == "INCONCLUSIVE":
            print("Need at least five observations with WTS state LOCKED to draw conclusions.")
        elif report["result"] == "CAMERA_READS_DURING_LOCK":
            print("Preliminary positive evidence only: capture != viable face authentication.")
        else:
            print("Camera frames unavailable/uniform while locked in this configuration.")
    except KeyboardInterrupt:
        print(f"Diagnostic interrupted. Existing CSV remains at: {output}")
    finally:
        camera.release()


if __name__ == "__main__":
    main()

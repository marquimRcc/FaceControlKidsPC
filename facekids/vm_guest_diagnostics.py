"""Portable VM diagnostics invoked as a module, not via PowerShell -c.

No biometric data is persisted; CAMERA is interactive only, not Winlogon
or service Session 0. This utility never authorizes a login or a lock.
"""
from __future__ import annotations

import argparse


def verify_dependencies() -> int:
    import tkinter  # noqa: F401
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    print("Python, Tkinter, OpenCV e NumPy: OK")
    return 0


def probe_interactive_camera(index: int) -> int:
    """Return 0 for a frame; 2/3 for missing camera/frame; always release."""
    import cv2

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            print("CAMERA_GUEST_INTERACTIVE=UNAVAILABLE")
            return 2
        ok, frame = cap.read()
        available = bool(ok and frame is not None)
        print("CAMERA_GUEST_INTERACTIVE=" +
              ("FRAME_OBSERVED" if available else "NO_FRAME"))
        return 0 if available else 3
    finally:
        cap.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FaceKids disposable VM diagnostics")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("dependencies")
    camera = actions.add_parser("camera")
    camera.add_argument("--index", type=int, default=0, choices=range(10))
    args = parser.parse_args(argv)
    if args.action == "dependencies":
        return verify_dependencies()
    return probe_interactive_camera(args.index)


if __name__ == "__main__":
    raise SystemExit(main())

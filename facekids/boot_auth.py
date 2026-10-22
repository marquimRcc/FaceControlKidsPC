"""Boot supervisor for the existing facial server (no automatic Windows logon).

Runs as SYSTEM through Task Scheduler. Camera drivers may not be ready at boot,
so a failed or stuck child is replaced, alternating DirectShow and MSMF. Only
the exact subprocess created here is terminated; existing interactive workers
are never killed. No biometric data or passwords are written to this status.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

STARTUP_TIMEOUT = 30.0
REQUEST_TIMEOUT = 15.0
RETRY_DELAY = 5.0
BACKENDS = ("dshow", "msmf")


def write_status(path: Path, **data) -> None:
    """Atomic status replacement, so the supervisor never reads partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".tmp")
    staging.write_text(json.dumps({**data, "updated_at": time.time()}), encoding="utf-8")
    staging.replace(path)


def read_status(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def worker_expired(state: dict, elapsed: float, unchanged_for: float) -> bool:
    """Use supervisor monotonic time; an idle pipe can legitimately wait forever."""
    if state.get("phase") == "listening":
        return False
    if state.get("phase") in ("request", "allow", "pipe_setup"):
        return unchanged_for >= REQUEST_TIMEOUT
    return elapsed >= STARTUP_TIMEOUT


def supervise(*, state_path: Path, popen=subprocess.Popen,
              clock=time.monotonic, sleep=time.sleep, max_attempts: int | None = None) -> None:
    root = Path(__file__).resolve().parent.parent
    attempt = 0
    # A separate directory per supervisor prevents stale state from a previous
    # boot (or an interactive process) from keeping a dead worker alive.
    with tempfile.TemporaryDirectory(prefix="FaceKids-boot-") as td:
        worker_state = Path(td) / "worker.json"
        while max_attempts is None or attempt < max_attempts:
            backend = BACKENDS[attempt % len(BACKENDS)]
            attempt += 1
            worker_state.unlink(missing_ok=True)
            command = [sys.executable, "-m", "facekids.auth_service",
                       "--camera-backend", backend, "--status-file", str(worker_state)]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            env["FACEKIDS_BOOT_WORKER"] = "1"
            process = popen(command, cwd=str(root), env=env)
            started = clock()
            changed = started
            previous = None
            timed_out = False
            try:
                while process.poll() is None:
                    state = read_status(worker_state)
                    signature = (state.get("phase"), state.get("updated_at"))
                    now = clock()
                    if signature != previous:
                        previous, changed = signature, now
                    write_status(state_path, phase=state.get("phase", "starting"),
                                 backend=backend, worker_pid=process.pid, attempt=attempt,
                                 supervisor_pid=os.getpid())
                    if worker_expired(state, now - started, now - changed):
                        timed_out = True
                        break
                    sleep(0.5)
            finally:
                # Terminate only our child, including when Python exits on an
                # exception. No taskkill /im python*, no registry/logon changes.
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            write_status(state_path, phase="retry_wait", backend=backend,
                         attempt=attempt, worker_pid=process.pid,
                         timed_out=timed_out, exit_code=process.returncode,
                         supervisor_pid=os.getpid())
            if max_attempts is None or attempt < max_attempts:
                sleep(RETRY_DELAY)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path,
                        default=Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) /
                        "FaceKids" / "boot_status.json")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("O supervisor de boot requer Windows.")
    supervise(state_path=args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

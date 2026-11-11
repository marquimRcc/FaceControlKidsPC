"""Supervised lifecycle for the read-only Windows quota BROKER LAB.

Designed to run under the Windows SCM in a disposable VM after explicit
administrative registration. It does not install, configure, or register
services and is not a replacement for the live Filhos quota agent.
"""
from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Mapping

from .quota_broker_transport_win import serve_one_lab_request


class QuotaLabSupervisor:
    """Cancelable one-instance-at-a-time service loop.

    Stops promptly if no client connects, never spins on repeated failures,
    and never enables database writes or mutating requests.
    """

    def __init__(
        self, *,
        pipe_name: str,
        data_path: Path,
        enrolled_child_by_sid: Mapping[str, int],
        serve_one: Callable[..., bool] = serve_one_lab_request,
        stop_event: threading.Event | None = None,
        max_consecutive_failures: int = 3,
        retry_interval_seconds: float = 0.5,
    ):
        if type(max_consecutive_failures) is not int or not 1 <= max_consecutive_failures <= 10:
            raise ValueError("Invalid failure threshold")
        if not isinstance(retry_interval_seconds, (int, float)) or not 0.05 <= retry_interval_seconds <= 5:
            raise ValueError("Invalid retry interval")
        if not pipe_name or not enrolled_child_by_sid:
            raise ValueError("Lab pipe name and trusted SID map required")
        self.pipe_name = pipe_name
        self.data_path = Path(data_path)
        self.mapping = dict(enrolled_child_by_sid)
        self.serve_one = serve_one
        self.stop_event = stop_event or threading.Event()
        self.max_failures = max_consecutive_failures
        self.retry = float(retry_interval_seconds)
        self.processed = 0
        self.errors = 0
        self.timeout_cycles = 0
        self.last_error: str | None = None

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        consecutive_failures = 0
        while not self.stop_event.is_set():
            try:
                served = self.serve_one(
                    pipe_name=self.pipe_name,
                    data_path=self.data_path,
                    enrolled_child_by_sid=self.mapping,
                    stop_event=self.stop_event,
                    timeout_seconds=2.0,
                )
                consecutive_failures = 0
                if served is True:
                    self.processed += 1
                else:
                    self.timeout_cycles += 1
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                self.errors += 1
                consecutive_failures += 1
                self.last_error = type(exc).__name__
                if consecutive_failures >= self.max_failures:
                    raise RuntimeError("Quota lab broker hit its fail-closed error limit") from exc
                if self.stop_event.wait(self.retry):
                    break

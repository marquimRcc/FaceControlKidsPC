"""Diagnostic-only optional comparison against the VM quota broker.

This code must never decide login, charging, switching, or Windows locking.
Its response source is not authenticated by the lab client.
"""
from __future__ import annotations

import math
import re
import threading
import time
from typing import Any

from .quota_broker_client_win import query_lab_balance
from .quota_broker_transport_win import LAB_PIPE_PREFIX


def compare_shadow_balance(local_seconds: float, reply: Any) -> tuple[str, float | None]:
    """Telemetry only; no authority, no side effects."""
    if (type(local_seconds) not in (float, int) or
            not math.isfinite(local_seconds) or local_seconds < 0):
        return "local-invalid", None
    if type(reply) is not dict or reply.get("status") != "OK":
        return "broker-unavailable", None
    remote = reply.get("remaining_seconds")
    if type(remote) not in (float, int) or not math.isfinite(remote) or remote < 0:
        return "broker-invalid", None
    delta = float(remote) - float(local_seconds)
    return ("matched" if abs(delta) < 2.0 else "diverged"), delta


class QuotaBrokerShadowProbe:
    """Rate-limited background lab probe; never blocks Filhos quota loop."""

    def __init__(self, pipe_suffix: str, *, interval_seconds: float = 120.0):
        if type(pipe_suffix) is not str or not re.fullmatch(r"[0-9a-f]{32}", pipe_suffix):
            raise ValueError("Shadow mode requires a unique lab pipe identifier")
        if (type(interval_seconds) not in (int, float) or
                not math.isfinite(interval_seconds) or interval_seconds < 15):
            raise ValueError("Shadow interval too short or invalid")
        self.pipe_name = LAB_PIPE_PREFIX + pipe_suffix
        self.interval_seconds = float(interval_seconds)
        self._last_check = 0.0
        self._lock = threading.Lock()
        self._pending: Any = None
        self._thread: threading.Thread | None = None

    def trigger_if_due(self):
        now = time.monotonic()
        if now - self._last_check < self.interval_seconds:
            return
        if self._thread and self._thread.is_alive():
            return
        self._last_check = now

        def run_once():
            try:
                reply = query_lab_balance(self.pipe_name)
            except (OSError, RuntimeError, ValueError, TimeoutError):
                reply = {"status": "DENY"}
            with self._lock:
                self._pending = reply

        self._thread = threading.Thread(target=run_once, daemon=True)
        self._thread.start()

    def take_result(self) -> Any:
        with self._lock:
            result = self._pending
            self._pending = None
            return result

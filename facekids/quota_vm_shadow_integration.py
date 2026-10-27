"""P5: explicitly opted-in, non-authoritative Windows VM shadow telemetry.

Queries only the face-bound READ-ONLY SCM pipe, never shares a camera,
never supplies identity/elapsed time, and cannot influence quota or lock.
The optional diagnostic is OFF by default, including on family installs.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import threading
import time
from typing import Callable

from .quota_broker_bound_protocol import BoundBalance
from .quota_broker_bound_client_win import query_current_bound_vm_balance


@dataclass(frozen=True)
class ShadowComparison:
    outcome: str
    child_id: int | None
    difference_seconds: float | None
    sample_age_seconds: float


class VmBoundShadow:
    def __init__(self, *, query: Callable[[], BoundBalance | None] =
                 query_current_bound_vm_balance, interval_seconds: float = 120.0,
                 clock: Callable[[], float] = time.monotonic):
        if (not callable(query) or not callable(clock) or
                type(interval_seconds) not in (int, float) or
                not math.isfinite(interval_seconds) or interval_seconds < 15):
            raise ValueError("Invalid VM shadow probe configuration")
        self._query = query
        self._clock = clock
        self._interval = float(interval_seconds)
        self._last = float("-inf")
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pending: tuple[int, str, float, float, BoundBalance | None, str] | None = None

    def trigger_if_due(self, *, child_id: int | None, day: str,
                       remaining_seconds: float) -> None:
        if (type(child_id) is not int or child_id <= 0 or
                type(day) is not str or len(day) != 10 or
                type(remaining_seconds) not in (int, float) or
                not math.isfinite(remaining_seconds) or remaining_seconds < 0):
            return
        with self._lock:
            now = self._clock()
            if (self._thread is not None and self._thread.is_alive()) or (
                    now - self._last < self._interval):
                return
            self._last = now

            def run():
                try:
                    reply = self._query()
                    if reply is not None and type(reply) is not BoundBalance:
                        raise ValueError("Invalid SCM shadow response")
                    outcome = "sample" if reply is not None else "unbound"
                except Exception:
                    reply, outcome = None, "unavailable"
                with self._lock:
                    self._pending = (child_id, day, float(remaining_seconds),
                                     now, reply, outcome)

            self._thread = threading.Thread(
                target=run, name="FaceKidsVmReadOnlyShadow", daemon=True)
            self._thread.start()

    def take_result(self, *, current_child_id: int | None,
                    current_day: str, current_remaining: float
                    ) -> ShadowComparison | None:
        with self._lock:
            item = self._pending
            self._pending = None
        if item is None:
            return None
        child_id, day, local, then, reply, outcome = item
        age = max(0.0, float(self._clock()) - then)
        if (child_id != current_child_id or day != current_day or
                type(current_remaining) not in (int, float) or
                not math.isfinite(current_remaining) or current_remaining < 0):
            return ShadowComparison("local-context-changed", child_id, None, age)
        if outcome != "sample":
            return ShadowComparison(outcome, child_id, None, age)
        if reply is None or reply.child_id != child_id:
            return ShadowComparison("different-face-lease", child_id, None, age)
        # A snapshot taken before an async request is stale as soon as the
        # legacy agent debits; don't report a false convergence/divergence.
        # Substantial local movement is marked as an incomparable sample.
        if age > 6 or abs(float(current_remaining) - local) > 2:
            return ShadowComparison("incomparable-sample", child_id, None, age)
        delta = float(reply.remaining_seconds) - local
        return ShadowComparison(
            "matched" if abs(delta) < 2 else "diverged", child_id, delta, age)


def shadow_enabled_for_vm(environment: dict[str, str] | None = None,
                          *, windows: bool | None = None) -> bool:
    """Requires TWO explicit opt-ins; neither enables broker billing.

    Runtime VM evidence (hypervisor snapshot) must still be checked via P6.
    """
    import sys
    env = os.environ if environment is None else environment
    is_windows = sys.platform == "win32" if windows is None else windows
    return bool(is_windows and env.get("FACEKIDS_VM_SHADOW") == "1"
                and env.get("FACEKIDS_VM_SHADOW_ACK") == "DISPOSABLE_VM_ONLY")

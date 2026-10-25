"""Service Control Manager host for the service-owned quota runtime.

Only the SCM callback supplies lock state. Only the service's own camera
recognizer supplies child identity. Only the worker's monotonic clock supplies
charge duration. There is deliberately NO mutating client IPC endpoint.

This module does not register/install a service. A protected Windows service
wrapper may host this worker after explicitly validating machine policy,
filesystem ACLs, the service process principal and VM recovery readiness.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from .quota_broker_face_binding import FaceBindingOutcome
from .quota_broker_policy import BrokerTick
from .quota_broker_bound_protocol import BoundBalance
from .quota_broker_runtime import ServiceOwnedQuotaRuntime


class ServiceOwnedScmHost:
    """Cancelable SCM event + service-owned camera/tick orchestration."""

    def __init__(
        self,
        runtime: ServiceOwnedQuotaRuntime,
        *,
        stop_event: threading.Event | None = None,
        tick_interval_seconds: float = 1.0,
        face_retry_seconds: float = 15.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(runtime, ServiceOwnedQuotaRuntime):
            raise ValueError("Service-owned quota runtime required")
        if type(tick_interval_seconds) not in (float, int) or not 0.2 <= tick_interval_seconds <= 15:
            raise ValueError("Tick interval out of range")
        if type(face_retry_seconds) not in (float, int) or not 5 <= face_retry_seconds <= 120:
            raise ValueError("Face retry interval out of range")
        if not callable(monotonic):
            raise ValueError("Service-local monotonic source required")
        self._runtime = runtime
        self._stop = stop_event if stop_event is not None else threading.Event()
        self._interval = float(tick_interval_seconds)
        self._retry = float(face_retry_seconds)
        self._now = monotonic
        self._lock = threading.RLock()
        self._needs_face = False
        self._next_face_attempt = 0.0
        self._generation = 0
        self.attempts = 0
        self.ticks = 0
        self.charged_total = 0.0
        self.last_tick: BrokerTick | None = None
        self._last_tick_at: float | None = None
        self.last_face: FaceBindingOutcome | None = None

    def on_scm_session_change(self, code: int, payload: tuple[int]) -> None:
        """Called exclusively by SCM SvcOtherEx, NEVER from an IPC request."""
        with self._lock:
            if self._stop.is_set():
                return
            self._generation += 1
            self.last_tick = None
            self._last_tick_at = None
            # Fail closed even when Windows gives an unsupported event.
            self._needs_face = False
            try:
                self._runtime.on_service_session_change(code, payload)
            except (ValueError, TypeError):
                self._runtime.stop()
                raise
            if code == 8:  # WTS_SESSION_UNLOCK
                self._needs_face = True
                self._next_face_attempt = 0.0

    def step(self) -> BrokerTick:
        """One serialized service-generated attempt and tick.

        SC M notifications can interrupt a blocked face capture. On return the
        runtime cross-checks WTS token SID, connected state and SCM revision.
        """
        if self._stop.is_set():
            return BrokerTick(None, 0, 0, False, "service-stopped")
        capture = False
        with self._lock:
            now = self._now()
            if self._needs_face and now >= self._next_face_attempt:
                capture = True
                self._next_face_attempt = now + self._retry
                generation = self._generation
                # The former face's balance must not be published during
                # a new service-owned recognition attempt.
                self.last_tick = None
                self._last_tick_at = None
        if capture:
            result = self._runtime.bind_from_service_camera()
            with self._lock:
                self.attempts += 1
                self.last_face = result
                if self._generation == generation and result.accepted:
                    self._needs_face = False
        with self._lock:
            if self._stop.is_set():
                return BrokerTick(None, 0, 0, False, "service-stopped")
            tick = self._runtime.service_tick()
            self.last_tick = tick
            self._last_tick_at = self._now()
            self.ticks += 1
            self.charged_total += tick.charged_seconds
            if tick.reason in ("quota", "curfew", "session-switched", "wts-unverified", "wts-inactive"):
                # Never silently rebind after session switches or exhausted time.
                self._needs_face = False
            return tick

    def read_bound_balance(self, *, verified_client_sid: str) -> BoundBalance | None:
        """Read the latest service-generated result for the *face-bound* child.

        No SQLite connection is used in the Named Pipe thread. Refuse stale
        samples, stop, unknown face, lock, SID/session change or unverified
        camera capture. The only input is the caller's OS TOKEN_USER.
        """
        with self._lock:
            if self._stop.is_set():
                return None
            tick = self.last_tick
            sampled = self._last_tick_at
            if tick is None or sampled is None or tick.reason not in (
                "charged", "paused"
            ):
                return None
            now = self._now()
            if now < sampled or now - sampled > max(3.0, 3.0 * self._interval):
                return None
            child = self._runtime.verified_child_for_client(
                token_sid=verified_client_sid
            )
            if type(child) is not int or child != tick.child_id:
                return None
            remaining = tick.remaining_seconds
            if type(remaining) not in (int, float):
                return None
            import math
            if not math.isfinite(remaining) or remaining < 0:
                return None
            return BoundBalance(
                child_id=child,
                remaining_seconds=float(remaining),
                allowed_now=not tick.locked and remaining > 0,
            )

    def run(self) -> None:
        try:
            while not self._stop.is_set():
                self.step()
                self._stop.wait(self._interval)
        finally:
            self._runtime.stop()

    def request_stop(self) -> None:
        # On a stop during a camera capture, revoking the WTS generation means
        # any late ALLOW result is rejected, not persisted as a lease.
        self._stop.set()
        self._runtime.stop()
        with self._lock:
            self._generation += 1
            self._needs_face = False
            self.last_tick = None
            self._last_tick_at = None

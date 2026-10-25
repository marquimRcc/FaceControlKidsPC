"""Single-process quota runtime for a future privileged Windows service.

This is the *wiring*, not a service installer. On real Windows the host MUST
run as an ACL-protected service and pass its OWN recognizer and WTS/token probe.
There is intentionally no JSON/API/child-facing method to set child identity,
elapsed time, WTS state or debit receipts. SCM activation is not performed.
"""
from __future__ import annotations

from datetime import date
import threading
import time
from typing import Callable, Mapping

from .quota_broker_face_binding import PrivilegedLocalFaceBinder, FaceBindingOutcome
from .quota_broker_policy import ServiceOwnedQuotaBroker, BrokerTick
from .quota_broker_wts import VerifiedWtsQuotaWorker, WtsLockTracker, WtsSnapshot
from .storage import Storage


class ServiceOwnedQuotaRuntime:
    def __init__(
        self,
        store: Storage,
        *,
        expected_windows_sid: str,
        observe_wts: Callable[[], WtsSnapshot | None],
        capture_face_locally: Callable[[], tuple[str, Mapping[str, object]]],
        monotonic: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._lock = threading.RLock()
        self._locks = WtsLockTracker()
        self._broker = ServiceOwnedQuotaBroker(
            store, monotonic=monotonic, today=today
        )
        self._worker = VerifiedWtsQuotaWorker(
            self._broker, expected_sid=expected_windows_sid,
            snapshot=observe_wts, locks=self._locks,
        )
        self._face = PrivilegedLocalFaceBinder(
            worker=self._worker, locks=self._locks,
            recognize_locally=capture_face_locally,
        )

    @classmethod
    def from_service_authenticator(
        cls, store: Storage, *,
        expected_windows_sid: str,
        authenticator: object,
        observe_wts: Callable[[], WtsSnapshot | None],
        monotonic: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> "ServiceOwnedQuotaRuntime":
        """Connect actual FaceAuthenticator in-process, without legacy JSON.

        Does not make camera recognition spoof-resistant. A privileged SCM
        host must protect its code, verify session/token and perform VM
        hardware testing before enabling any billing.
        """
        from .auth_service import FaceAuthenticator
        if not isinstance(authenticator, FaceAuthenticator):
            raise ValueError("Service-owned FaceAuthenticator instance required")
        return cls(
            store, expected_windows_sid=expected_windows_sid,
            observe_wts=observe_wts,
            capture_face_locally=lambda: authenticator.evaluate(
                persist_unlock_metadata=False
            ),
            monotonic=monotonic, today=today,
        )

    def on_service_session_change(self, code: int, payload: tuple[int]) -> None:
        with self._lock:
            try:
                self._locks.record_windows_scm_notification(code, payload)
            except (ValueError, TypeError):
                self._locks.reset()
                self._worker.end_trusted_face_binding()
                raise
            # Revoke on every lock/transition: no previous child's face
            # authorization survives a lock, logon, logout or disconnect.
            if code != 8:  # only WTS_SESSION_UNLOCK; unlocking still requires face
                self._worker.end_trusted_face_binding()

    def bind_from_service_camera(self) -> FaceBindingOutcome:
        with self._lock:
            return self._face.recognize_and_bind()

    def service_tick(self) -> BrokerTick:
        with self._lock:
            return self._worker.observe_service_tick()

    def stop(self) -> None:
        with self._lock:
            self._locks.reset()
            self._worker.end_trusted_face_binding()

"""Service-local facial recognition -> WTS quota lease bridge.

A face capture may block for seconds. NEVER hold the SCM session-event lock
while capturing: Win+L must revoke the lease immediately and the revision
must be compared atomically with binding. Client IPC cannot pass the child ID
or a duration into this object.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, ContextManager, Mapping

from .quota_broker_policy import BrokerTick
from .quota_broker_wts import VerifiedWtsQuotaWorker, WtsLockTracker


@dataclass(frozen=True)
class FaceBindingOutcome:
    accepted: bool
    reason: str
    tick: BrokerTick | None = None


class PrivilegedLocalFaceBinder:
    """Bound to a service-owned recognizer at construction, not child IPC."""

    def __init__(
        self, *,
        worker: VerifiedWtsQuotaWorker,
        locks: WtsLockTracker,
        recognize_locally: Callable[[], tuple[str, Mapping[str, object]]],
        state_lock: ContextManager | None = None,
    ) -> None:
        if not callable(recognize_locally):
            raise ValueError("Service-owned face capture callback required")
        self._worker = worker
        self._locks = locks
        self._recognize = recognize_locally
        self._state_lock = state_lock if state_lock is not None else nullcontext()

    def recognize_and_bind(self) -> FaceBindingOutcome:
        """Never charge during capture; retain identity for bounded failed checks.

        Only OS-observed session/lock continuity may preserve grace. Client
        mouse activity cannot extend or authorize a service-owned lease.
        """
        with self._state_lock:
            before = self._worker.observed_snapshot()
            epoch = self._locks.revision
            if (before is None or not before.connected or
                    not self._locks.is_unlocked(before.session_id)):
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, "session-unverified")
            has_prior = self._worker.begin_trusted_face_recheck(
                session_id=before.session_id)

        def fail(reason: str, *, transient: bool = False) -> FaceBindingOutcome:
            with self._state_lock:
                after = self._worker.observed_snapshot()
                unchanged = (after == before and self._locks.revision == epoch
                             and self._locks.is_unlocked(before.session_id))
                if not unchanged:
                    self._worker.end_trusted_face_binding()
                    return FaceBindingOutcome(False, "session-changed-during-capture")
                if transient and has_prior and self._worker.transient_face_grace(
                        session_id=before.session_id):
                    return FaceBindingOutcome(False, "face-grace")
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, reason)

        # Do not hold SCM event lock over camera calls. Lock/disconnect must
        # invalidate this observation even during a delayed or failed capture.
        try:
            status, data = self._recognize()
        except Exception:
            return fail("local-recognizer-error", transient=True)

        with self._state_lock:
            after = self._worker.observed_snapshot()
            if (after != before or self._locks.revision != epoch or
                    not self._locks.is_unlocked(before.session_id)):
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, "session-changed-during-capture")
            if status != "ALLOW":
                if (status in ("DENY_UNKNOWN", "DENY_NO_FACE", "ERROR_CAMERA")
                        and has_prior and self._worker.transient_face_grace(
                            session_id=before.session_id)):
                    return FaceBindingOutcome(False, "face-grace")
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, "face-not-authorized")
            if type(data) is not dict or data.get("user") != "Filhos":
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, "face-not-authorized")
            child_id = data.get("child_id")
            if type(child_id) is not int or child_id <= 0:
                self._worker.end_trusted_face_binding()
                return FaceBindingOutcome(False, "invalid-enrollment")
            tick = self._worker.start_trusted_face_binding(
                enrolled_child_id=child_id, session_id=before.session_id)
            return FaceBindingOutcome(tick.reason == "verified", tick.reason, tick)

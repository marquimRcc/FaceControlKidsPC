"""Service-local facial recognition -> WTS quota lease bridge.

Only invoke from the privileged service's OWN recognizer/camera path.
No JSON, named-pipe input, unlock notification file or child-provided
child_id is accepted here. The legacy FaceAuthenticator DOES NOT establish
liveness/anti-replay, and camera access from Session 0 is not proven.
This module intentionally does not register a service or change Winlogon.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .quota_broker_policy import BrokerTick
from .quota_broker_wts import VerifiedWtsQuotaWorker, WtsLockTracker, WtsSnapshot


@dataclass(frozen=True)
class FaceBindingOutcome:
    accepted: bool
    reason: str
    tick: BrokerTick | None = None


class PrivilegedLocalFaceBinder:
    """Bound to a co-located recognizer at service construction, not child IPC."""

    def __init__(
        self, *,
        worker: VerifiedWtsQuotaWorker,
        locks: WtsLockTracker,
        recognize_locally: Callable[[], tuple[str, Mapping[str, object]]],
    ) -> None:
        if not callable(recognize_locally):
            raise ValueError("Service-owned face capture callback required")
        self._worker = worker
        self._locks = locks
        self._recognize = recognize_locally

    def recognize_and_bind(self) -> FaceBindingOutcome:
        before = self._worker.observed_snapshot()
        epoch = self._locks.revision
        if (before is None or not before.connected or
                not self._locks.is_unlocked(before.session_id)):
            return FaceBindingOutcome(False, "session-unverified")
        try:
            # This callback MUST invoke FaceAuthenticator.evaluate in the
            # privileged process. Its output is never read from child IPC.
            status, data = self._recognize()
        except Exception:
            self._worker.end_trusted_face_binding()
            return FaceBindingOutcome(False, "local-recognizer-error")
        after = self._worker.observed_snapshot()
        if (after != before or self._locks.revision != epoch or
                not self._locks.is_unlocked(before.session_id)):
            self._worker.end_trusted_face_binding()
            return FaceBindingOutcome(False, "session-changed-during-capture")
        if (status != "ALLOW" or type(data) is not dict or
                data.get("user") != "Filhos"):
            self._worker.end_trusted_face_binding()
            return FaceBindingOutcome(False, "face-not-authorized")
        child_id = data.get("child_id")
        if type(child_id) is not int or child_id <= 0:
            self._worker.end_trusted_face_binding()
            return FaceBindingOutcome(False, "invalid-enrollment")
        # Broker independently checks existence, actual quota and curfew.
        tick = self._worker.start_trusted_face_binding(
            enrolled_child_id=child_id, session_id=before.session_id
        )
        return FaceBindingOutcome(
            tick.reason == "verified", tick.reason, tick
        )

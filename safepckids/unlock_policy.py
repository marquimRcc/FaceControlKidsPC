"""P0-3 offline quota gate for a future native Windows Credential Provider.

Pure, locally testable policy plus one-use ticket lifecycle. NOT a Windows
service, Credential Provider interface, verified camera channel or IPC server.
Only a trusted SYSTEM-side process may issue tickets in the final design.
"""
from __future__ import annotations

import math
import secrets
import threading
import time
from dataclasses import dataclass
from enum import Enum


class UnlockReason(str, Enum):
    ALLOW = "allow"
    CAMERA_ERROR = "camera_error"
    NO_SINGLE_FACE = "no_single_face"
    UNKNOWN_FACE = "unknown_face"
    NOT_LIVE = "not_live"
    NOT_CONFIRMED = "not_confirmed"
    STALE_OBSERVATION = "stale_observation"
    NO_QUOTA = "no_quota"
    INVALID_QUOTA = "invalid_quota"


@dataclass(frozen=True)
class FacialEvidence:
    child_id: int | None
    face_count: int
    confirmations: int
    live: bool
    observed_at: float
    camera_ok: bool = True


@dataclass(frozen=True)
class UnlockVerdict:
    reason: UnlockReason
    child_id: int | None = None

    @property
    def permitted(self) -> bool:
        return self.reason is UnlockReason.ALLOW


def evaluate_unlock(
    evidence: FacialEvidence,
    remaining_by_child: dict[int, float],
    now: float,
    *,
    min_confirmations: int = 3,
    max_age_seconds: float = 3.0,
) -> UnlockVerdict:
    """Evaluate evidence from a *trusted* capture channel against recent quotas.

    Never treat an arbitrary request JSON from the children's account as
    trusted FacialEvidence. This function cannot establish camera provenance.
    """
    if not isinstance(evidence, FacialEvidence):
        raise TypeError("Expected FacialEvidence")
    if min_confirmations < 1 or max_age_seconds <= 0:
        raise ValueError("Invalid policy configuration")
    if not math.isfinite(now):
        raise ValueError("Invalid monotonic time")
    if not evidence.camera_ok:
        return UnlockVerdict(UnlockReason.CAMERA_ERROR)
    if type(evidence.face_count) is not int or evidence.face_count != 1:
        return UnlockVerdict(UnlockReason.NO_SINGLE_FACE)
    if type(evidence.child_id) is not int or evidence.child_id < 1:
        return UnlockVerdict(UnlockReason.UNKNOWN_FACE)
    if not evidence.live:
        return UnlockVerdict(UnlockReason.NOT_LIVE)
    if type(evidence.confirmations) is not int or evidence.confirmations < min_confirmations:
        return UnlockVerdict(UnlockReason.NOT_CONFIRMED)
    if not math.isfinite(evidence.observed_at) or not 0 <= now - evidence.observed_at <= max_age_seconds:
        return UnlockVerdict(UnlockReason.STALE_OBSERVATION)
    remaining = remaining_by_child.get(evidence.child_id)
    if remaining is None:
        return UnlockVerdict(UnlockReason.NO_QUOTA)
    if type(remaining) not in (int, float) or not math.isfinite(remaining):
        return UnlockVerdict(UnlockReason.INVALID_QUOTA)
    if remaining <= 0:
        return UnlockVerdict(UnlockReason.NO_QUOTA)
    return UnlockVerdict(UnlockReason.ALLOW, evidence.child_id)


@dataclass(frozen=True)
class TicketResult:
    verdict: UnlockVerdict
    ticket: str | None = None


class OneUseTicketRegistry:
    """In-memory lifecycle reference; no native Windows credentials are issued.

    A ticket binds the child identity to an existing Windows session ID and
    expires after a short time. On consumption, the quota MUST be read again
    from trusted storage. All caller authorization is the responsibility
    of a future privileged service (not implemented here).
    """

    def __init__(self, *, ttl_seconds: float = 8.0, clock=None):
        if not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 30:
            raise ValueError("Ticket TTL must be positive and at most 30 seconds")
        self.ttl_seconds = ttl_seconds
        self.clock = clock or time.monotonic
        self._tickets: dict[str, tuple[int, int, float]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_session(session_id: int) -> None:
        if type(session_id) is not int or session_id < 0:
            raise ValueError("Expected nonnegative Windows session ID")

    def issue(
        self,
        evidence: FacialEvidence,
        remaining_by_child: dict[int, float],
        session_id: int,
    ) -> TicketResult:
        self._validate_session(session_id)
        with self._lock:
            now = self.clock()
            verdict = evaluate_unlock(evidence, remaining_by_child, now)
            if not verdict.permitted:
                return TicketResult(verdict)
            # Short nonce is not proof of a trusted IPC client. It must never
            # be delivered to arbitrary processes running as the child.
            token = secrets.token_urlsafe(32)
            self._tickets[token] = (verdict.child_id, session_id, now + self.ttl_seconds)
            return TicketResult(verdict, token)

    def consume(
        self,
        ticket: str,
        session_id: int,
        remaining_by_child: dict[int, float],
    ) -> int | None:
        self._validate_session(session_id)
        if not isinstance(ticket, str) or not ticket:
            return None
        with self._lock:
            # Pop first: tickets are single-use, including mismatched-session
            # or revoked/quota-exhausted attempts.
            record = self._tickets.pop(ticket, None)
            if record is None:
                return None
            child_id, bound_session, deadline = record
            now = self.clock()
            if not math.isfinite(now) or now > deadline or session_id != bound_session:
                return None
            remaining = remaining_by_child.get(child_id)
            if type(remaining) not in (int, float) or not math.isfinite(remaining) or remaining <= 0:
                return None
            return child_id

    def revoke_all(self) -> None:
        with self._lock:
            self._tickets.clear()

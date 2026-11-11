"""Tickets faciais de uso único para uma futura integração PAM no Linux."""
from __future__ import annotations

import math
import sqlite3
import threading
from dataclasses import dataclass

from .session import SessionState


@dataclass(frozen=True)
class FaceApproval:
    session_id: str
    child_id: int
    issued_at: float


class FaceApprovalBroker:
    """Exige três observações e consome a autorização exatamente uma vez."""

    def __init__(self, confirmations: int = 3, ttl_seconds: float = 10.0):
        if confirmations < 2 or not 1 <= ttl_seconds <= 30:
            raise ValueError("Política de autorização inválida")
        self.confirmations = confirmations
        self.ttl_seconds = ttl_seconds
        self._candidate = None
        self._session = None
        self._count = 0
        self._last_at = None
        self._approval: FaceApproval | None = None
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self._candidate = None
        self._session = None
        self._count = 0
        self._last_at = None
        self._approval = None

    def observe(
        self, *, now: float, session_id: str | None, state: SessionState,
        child_id: int | None, quota_available: bool, curfew_clear: bool,
    ) -> FaceApproval | None:
        with self._lock:
            if (not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0
                    or state is not SessionState.LOCKED or not session_id
                    or not all(ch.isalnum() or ch in "_-" for ch in session_id)
                    or type(child_id) is not int or child_id <= 0
                    or not quota_available or not curfew_clear):
                self._reset_unlocked()
                return None
            if self._last_at is not None and now < self._last_at:
                self._reset_unlocked()
                return None
            same = self._candidate == child_id and self._session == session_id
            timely = self._last_at is not None and now - self._last_at <= 3.0
            if not same or not timely:
                self._candidate = child_id
                self._session = session_id
                self._count = 1
            else:
                self._count += 1
            self._last_at = now
            if self._count < self.confirmations:
                return None
            self._approval = FaceApproval(session_id, child_id, now)
            self._count = 0
            return self._approval

    def consume(self, session_id: str, now: float) -> FaceApproval | None:
        with self._lock:
            approval = self._approval
            self._approval = None
            if (approval is None or approval.session_id != session_id
                    or not isinstance(now, (int, float)) or not math.isfinite(now)):
                return None
            age = now - approval.issued_at
            if age < 0 or age > self.ttl_seconds:
                return None
            return approval


def approval_still_allowed(store, approval: FaceApproval, day: str) -> bool:
    """Revalida horário e saldo no instante em que o PAM consome o ticket."""
    try:
        curfew, _reason = store.is_curfew_active()
        return not curfew and store.remaining(approval.child_id, day) > 0
    except (KeyError, ValueError, sqlite3.Error):
        return False

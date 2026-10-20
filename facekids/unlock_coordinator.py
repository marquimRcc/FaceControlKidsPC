"""Offline-only face/quota to Windows unlock authorization model.

No privileged service, protected IPC, real facial recognition or Windows
credential issuance is implemented here. Do not expose this object directly
to an application running under the Filhos account.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .unlock_policy import FacialEvidence, OneUseTicketRegistry, UnlockReason

_LOCAL_SID = re.compile(r"S-1-5-21-\d+-\d+-\d+-\d+\Z", re.ASCII)


@dataclass(frozen=True)
class WindowsSession:
    """Facts from a trusted WTS/OS reader, never from caller-provided JSON."""
    session_id: int
    user_sid: str
    locked: bool


class BridgeStatus(str, Enum):
    PENDING = "pending"
    GRANTED = "granted"
    WRONG_ACCOUNT = "wrong_account"
    WRONG_SESSION = "wrong_session"
    UNLOCKED = "unlocked"
    NO_AUTHORIZATION = "no_authorization"
    EVIDENCE_DENIED = "evidence_denied"
    REVOKED_OR_EXPIRED = "revoked_or_expired"
    SERVICE_ERROR = "service_error"


@dataclass(frozen=True)
class BridgeResult:
    status: BridgeStatus
    child_id: int | None = None
    evidence_reason: UnlockReason | None = None

    @property
    def permitted(self) -> bool:
        return self.status is BridgeStatus.GRANTED


class OfflineUnlockCoordinator:
    """Policy-only boundary for a future privileged broker.

    Both reader callbacks must be implemented by a trusted Windows service.
    Only that service's trusted camera worker may call record_trusted_face;
    only its OS-authenticated LogonUI handler may call consume_for_logonui.
    """

    def __init__(
        self,
        *,
        target_sid: str,
        parent_sid: str,
        read_session: Callable[[int], WindowsSession],
        read_remaining: Callable[[int], float],
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = 8.0,
    ):
        if not isinstance(target_sid, str) or not _LOCAL_SID.fullmatch(target_sid):
            raise ValueError("Expected local child-account Windows SID")
        if not isinstance(parent_sid, str) or not _LOCAL_SID.fullmatch(parent_sid):
            raise ValueError("Expected local administrator-account Windows SID")
        if target_sid == parent_sid:
            raise ValueError("Cannot approve the administrator account")
        if not callable(read_session) or not callable(read_remaining) or not callable(clock):
            raise ValueError("Trusted readers and clock are required")
        self._target_sid = target_sid
        self._read_session = read_session
        self._read_remaining = read_remaining
        self._tickets = OneUseTicketRegistry(ttl_seconds=ttl_seconds, clock=clock)
        self._lock = threading.RLock()
        self._pending_ticket: str | None = None
        self._pending_session: int | None = None
        self._pending_child: int | None = None

    def _clear(self) -> None:
        self._pending_ticket = None
        self._pending_session = None
        self._pending_child = None

    def _revoke(self) -> None:
        self._clear()
        self._tickets.revoke_all()

    def invalidate(self) -> None:
        """Revoke on camera failure, logout, changed face, worker death or WTS event."""
        with self._lock:
            self._revoke()

    def _session_status(self, session_id: int) -> BridgeStatus | None:
        if type(session_id) is not int or session_id < 0:
            return BridgeStatus.WRONG_SESSION
        try:
            session = self._read_session(session_id)
        except Exception:
            return BridgeStatus.SERVICE_ERROR
        if not isinstance(session, WindowsSession):
            return BridgeStatus.SERVICE_ERROR
        if type(session.session_id) is not int or session.session_id != session_id:
            return BridgeStatus.WRONG_SESSION
        if not isinstance(session.user_sid, str) or session.user_sid != self._target_sid:
            return BridgeStatus.WRONG_ACCOUNT
        if session.locked is not True:
            return BridgeStatus.UNLOCKED
        return None

    def _balance(self, child_id: int) -> dict[int, float] | None:
        try:
            return {child_id: self._read_remaining(child_id)}
        except Exception:
            return None

    def record_trusted_face(self, evidence: FacialEvidence, session_id: int) -> BridgeResult:
        """Trusted camera event only; it is NOT a public child-facing IPC API."""
        with self._lock:
            self._revoke()  # face switching or failure discards old approvals
            status = self._session_status(session_id)
            if status is not None:
                return BridgeResult(status)
            if not isinstance(evidence, FacialEvidence):
                return BridgeResult(BridgeStatus.EVIDENCE_DENIED)
            if type(evidence.child_id) is not int or evidence.child_id < 1:
                return BridgeResult(
                    BridgeStatus.EVIDENCE_DENIED, evidence_reason=UnlockReason.UNKNOWN_FACE
                )
            balance = self._balance(evidence.child_id)
            if balance is None:
                return BridgeResult(BridgeStatus.SERVICE_ERROR)
            grant = self._tickets.issue(evidence, balance, session_id)
            if not grant.verdict.permitted:
                return BridgeResult(
                    BridgeStatus.EVIDENCE_DENIED, evidence_reason=grant.verdict.reason
                )
            self._pending_ticket = grant.ticket
            self._pending_session = session_id
            self._pending_child = grant.verdict.child_id
            return BridgeResult(BridgeStatus.PENDING, grant.verdict.child_id)

    def consume_for_logonui(self, session_id: int) -> BridgeResult:
        """Internal privileged service call. No credential or token returned.

        A future transport MUST independently authenticate its caller and
        disallow direct access by the child Windows account.
        """
        with self._lock:
            ticket = self._pending_ticket
            bound_session = self._pending_session
            child_id = self._pending_child
            self._clear()  # one-shot even if WTS/quota read fails
            if ticket is None or child_id is None:
                return BridgeResult(BridgeStatus.NO_AUTHORIZATION)
            if type(session_id) is not int or session_id != bound_session:
                self._tickets.revoke_all()
                return BridgeResult(BridgeStatus.WRONG_SESSION)
            status = self._session_status(session_id)
            if status is not None:
                self._tickets.revoke_all()
                return BridgeResult(status)
            quota = self._balance(child_id)
            if quota is None:
                self._tickets.revoke_all()
                return BridgeResult(BridgeStatus.SERVICE_ERROR)
            approved = self._tickets.consume(ticket, session_id, quota)
            if approved != child_id:
                return BridgeResult(BridgeStatus.REVOKED_OR_EXPIRED)
            return BridgeResult(BridgeStatus.GRANTED, child_id)

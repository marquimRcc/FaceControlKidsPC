"""Windows WTS observation and lock event state for a future privileged quota worker.

The active-console connection state DOES NOT reveal Win+L lock state.
Only trusted SCM session-change notifications update the lock tracker.
Unknown state fails closed (no debit). No subprocess, install, SCM changes,
camera access, or child IPC commands originate from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from .quota_broker_policy import BrokerTick, ServiceOwnedQuotaBroker

_SID_PATTERN = re.compile(r"S-1-(?:[0-9]+-)+[0-9]+$")


@dataclass(frozen=True, slots=True)
class WtsSnapshot:
    """Provided by OS WTS and the session's Windows TOKEN_USER, never child IPC."""
    session_id: int
    token_sid: str
    connected: bool

    def __post_init__(self) -> None:
        if type(self.session_id) is not int or self.session_id <= 0:
            raise ValueError("Invalid observed WTS session")
        if type(self.token_sid) is not str or not _SID_PATTERN.fullmatch(self.token_sid):
            raise ValueError("Invalid observed Windows token SID")
        if type(self.connected) is not bool:
            raise ValueError("Invalid console connection flag")


class WtsLockTracker:
    """SCM-exclusive session notification sink. Unknown lock state means locked."""

    def __init__(self) -> None:
        self._unlocked: dict[int, bool] = {}

    def record_scm_event(self, *, event: str, session_id: int) -> None:
        # This method must never be exposed through child-facing IPC.
        if type(session_id) is not int or session_id <= 0:
            raise ValueError("Invalid SCM WTS session")
        if event == "unlock":
            self._unlocked[session_id] = True
        elif event in ("lock", "logoff", "disconnect", "logon", "connect"):
            # A reconnected session may still display Winlogon; require an
            # actual unlock notification before resuming any debit.
            self._unlocked[session_id] = False
        else:
            raise ValueError("Unexpected SCM session event")

    def is_unlocked(self, session_id: int) -> bool:
        return type(session_id) is int and self._unlocked.get(session_id) is True

    def reset(self) -> None:
        self._unlocked.clear()


class VerifiedWtsQuotaWorker:
    """Host-side policy bridge, NOT exposed over Named Pipe.

    A service must obtain child_id from a trusted face binding, expected_sid
    from protected configuration and snapshots from privileged WTS/token APIs.
    The existing family agent is NOT wired to this implementation.
    """

    def __init__(
        self,
        broker: ServiceOwnedQuotaBroker,
        *,
        expected_sid: str,
        snapshot: Callable[[], WtsSnapshot | None],
        locks: WtsLockTracker,
    ):
        if type(expected_sid) is not str or not _SID_PATTERN.fullmatch(expected_sid):
            raise ValueError("Trusted child Windows SID required")
        self._broker = broker
        self._expected_sid = expected_sid
        self._snapshot = snapshot
        self._locks = locks

    def _observed(self) -> WtsSnapshot | None:
        try:
            value = self._snapshot()
        except (OSError, ValueError, PermissionError):
            return None
        return value if type(value) is WtsSnapshot else None

    def start_trusted_face_binding(self, *, enrolled_child_id: int, session_id: int) -> BrokerTick:
        """Only a privileged recognized-face callback may call this method."""
        state = self._observed()
        if (state is None or state.session_id != session_id
                or state.token_sid != self._expected_sid
                or not state.connected or not self._locks.is_unlocked(session_id)):
            self._broker.end_verified_session()
            return BrokerTick(None, 0.0, 0.0, False, "wts-unverified")
        return self._broker.start_verified_session(
            child_id=enrolled_child_id, session_id=state.session_id,
            console_active=True,
        )

    def observe_service_tick(self) -> BrokerTick:
        """Never accept client-supplied elapsed seconds, child ID or lock state."""
        state = self._observed()
        if state is None or state.token_sid != self._expected_sid:
            self._broker.end_verified_session()
            return BrokerTick(None, 0.0, 0.0, False, "wts-unverified")
        return self._broker.observe(
            observed_wts_session_id=state.session_id,
            observed_console_active=(state.connected and self._locks.is_unlocked(state.session_id)),
        )

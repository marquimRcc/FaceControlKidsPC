"""Prototype of a future service-owned quota broker (NOT deployed).

Only privileged, independently verified WTS/face-recognition observations may
call this API. No IPC listener is provided here. The existing Filhos agent and
SQLite ACLs remain unchanged; this is not yet an authorization boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import time
from typing import Callable, Optional

from .quota_broker_clock import ServerObservedQuotaClock
from .storage import Storage


@dataclass(frozen=True, slots=True)
class BrokerTick:
    child_id: Optional[int]
    charged_seconds: float
    remaining_seconds: float
    locked: bool
    reason: str


class ServiceOwnedQuotaBroker:
    """Policy engine to be hosted by a future protected Windows service.

    The host MUST determine observed session/face from trusted Windows WTS
    state and trusted biometric service. Nothing returned by the Filhos agent
    can establish the child identity, active session or elapsed time.
    """

    def __init__(
        self,
        store: Storage,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._store = store
        self._mono = monotonic
        self._today = today
        self._lease: Optional[ServerObservedQuotaClock] = None

    def _now(self) -> float:
        value = self._mono()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("Trusted monotonic clock is invalid")
        return float(value)

    def start_verified_session(self, *, child_id: int, session_id: int,
                               console_active: bool) -> BrokerTick:
        """A new verified child/session replaces any previous lease.

        A caller must never map an IPC child_id to a verified identity.
        """
        self._lease = None
        if type(console_active) is not bool or not console_active:
            return BrokerTick(None, 0.0, 0.0, False, "not-active")
        if type(child_id) is not int or child_id <= 0 or type(session_id) is not int or session_id <= 0:
            raise ValueError("Verified child/session IDs must be positive integers")
        now = self._now()
        day = self._today().isoformat()
        try:
            remaining = self._store.remaining(child_id, day)
        except KeyError:
            return BrokerTick(None, 0.0, 0.0, False, "unknown-child")
        blocked, _ = self._store.is_curfew_active()
        if blocked or remaining <= 0:
            return BrokerTick(None, 0.0, remaining, True, "curfew" if blocked else "quota")
        self._lease = ServerObservedQuotaClock(
            child_id=child_id, session_id=session_id, last_mono=now
        )
        return BrokerTick(child_id, 0.0, remaining, False, "verified")

    def end_verified_session(self) -> None:
        self._lease = None

    def observe(self, *, observed_wts_session_id: int,
                observed_console_active: bool) -> BrokerTick:
        """Update a lease from authoritative WTS state, never client duration."""
        lease = self._lease
        if lease is None:
            return BrokerTick(None, 0.0, 0.0, False, "no-verified-lease")
        if type(observed_wts_session_id) is not int or observed_wts_session_id <= 0:
            raise ValueError("Invalid WTS session ID")
        if observed_wts_session_id != lease.session_id:
            self._lease = None
            return BrokerTick(None, 0.0, 0.0, False, "session-switched")
        now = self._now()
        delta = lease.sample(
            observed_child_id=lease.child_id,
            observed_wts_session_id=observed_wts_session_id,
            observed_wts_active=observed_console_active,
            now_mono=now,
        )
        day = self._today().isoformat()
        blocked, _ = self._store.is_curfew_active()
        if blocked:
            self._lease = None
            return BrokerTick(lease.child_id, 0.0, self._store.remaining(lease.child_id, day), True, "curfew")
        remaining_before = self._store.remaining(lease.child_id, day)
        # Never debit beyond the available balance (no negative quotas).
        charged = min(delta, remaining_before)
        if charged > 0:
            self._store.charge(lease.child_id, charged, day)
        remaining = self._store.remaining(lease.child_id, day)
        locked = remaining <= 0
        if locked:
            self._lease = None
        return BrokerTick(lease.child_id, charged, remaining, locked,
                          "quota" if locked else ("paused" if delta == 0 else "charged"))

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
import uuid
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
        new_receipt_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._store = store
        self._mono = monotonic
        self._today = today
        self._new_receipt_id = new_receipt_id
        self._lease: Optional[ServerObservedQuotaClock] = None
        self._rechecking = False
        self._grace_until: float | None = None

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
        self._rechecking = False
        self._grace_until = None
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

    def verified_lease_child(self, *, session_id: int) -> int | None:
        """Read a *currently held* service-only face lease, without SQLite IO.

        The external caller must still verify WTS token/lock under the same
        service state lock. This never accepts an IPC-selected child.
        """
        lease = self._lease
        if (lease is None or type(session_id) is not int or
                lease.session_id != session_id):
            return None
        return lease.child_id

    def end_verified_session(self) -> None:
        self._lease = None
        self._rechecking = False
        self._grace_until = None

    def begin_recheck(self, *, session_id: int) -> bool:
        """Pause charging while retaining the last verified identity."""
        lease = self._lease
        if lease is None or type(session_id) is not int or lease.session_id != session_id:
            return False
        lease.last_mono = self._now()
        self._rechecking = True
        self._grace_until = None
        return True

    def allow_transient_grace(self, *, session_id: int, seconds: float = 30.0) -> bool:
        """Bounded *non-charging* grace. Not a renewed authentication."""
        lease = self._lease
        if (lease is None or type(session_id) is not int or lease.session_id != session_id
                or not self._rechecking or type(seconds) not in (int, float)
                or not math.isfinite(seconds) or not 0 < seconds <= 30):
            return False
        now = self._now()
        lease.last_mono = now
        self._rechecking = False
        self._grace_until = now + float(seconds)
        return True

    def observe(self, *, observed_wts_session_id: int,
                observed_console_active: bool) -> BrokerTick:
        """Update a lease from authoritative WTS state, never client duration."""
        lease = self._lease
        if lease is None:
            return BrokerTick(None, 0.0, 0.0, False, "no-verified-lease")
        if type(observed_wts_session_id) is not int or observed_wts_session_id <= 0:
            raise ValueError("Invalid WTS session ID")
        if observed_wts_session_id != lease.session_id or not observed_console_active:
            self.end_verified_session()
            return BrokerTick(None, 0.0, 0.0, False, "session-switched")
        now = self._now()
        if self._rechecking or self._grace_until is not None:
            lease.last_mono = now  # never charge the camera capture or grace
            if self._grace_until is not None and now >= self._grace_until:
                self.end_verified_session()
                return BrokerTick(None, 0.0, 0.0, False, "face-grace-expired")
            return BrokerTick(lease.child_id, 0.0,
                              self._store.remaining(lease.child_id, self._today().isoformat()),
                              False, "rechecking" if self._rechecking else "face-grace")
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
        # A single BEGIN IMMEDIATE transaction caps debit even if another
        # broker process is writing. The legacy Filhos agent is unchanged.
        # Only the service mints receipt IDs; a Filhos IPC message must never
        # provide one. The insert and debit commit atomically in SQLite.
        charged = self._store.charge_capped_once(
            self._new_receipt_id(), lease.child_id, delta, day
        ) if delta > 0 else 0.0
        remaining = self._store.remaining(lease.child_id, day)
        locked = remaining <= 0
        if locked:
            self._lease = None
        return BrokerTick(lease.child_id, charged, remaining, locked,
                          "quota" if locked else ("paused" if delta == 0 else "charged"))

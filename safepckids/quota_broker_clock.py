"""Pure clock policy for a FUTURE service-owned quota ledger.

Only a privileged service may call this policy with WTS session state
observed independently of untrusted Filhos-agent messages. The current
deployment still debits SQLite from the child session: this module is
NOT wired into it and must not be presented as a security boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def _valid_clock(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


@dataclass(slots=True)
class ServerObservedQuotaClock:
    child_id: int
    session_id: int
    last_mono: float
    max_tick_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not _positive_id(self.child_id) or not _positive_id(self.session_id):
            raise ValueError("Child and WTS session IDs must be positive integers")
        if not _valid_clock(self.last_mono):
            raise ValueError("Initial monotonic clock must be finite")
        if not _valid_clock(self.max_tick_seconds) or self.max_tick_seconds <= 0:
            raise ValueError("Maximum tick interval must be positive and finite")

    def sample(
        self,
        *,
        observed_child_id: int,
        observed_wts_session_id: int,
        observed_wts_active: bool,
        now_mono: float,
    ) -> float:
        """Compute a debit amount, never trusting a client-supplied duration.

        Observed child/session/active status MUST originate from privileged
        enrollment and WTS state, not IPC fields claimed by a child process.
        Mismatches are rejected without advancing the clock.
        """
        if (observed_child_id != self.child_id or
                observed_wts_session_id != self.session_id or
                type(observed_child_id) is not int or
                type(observed_wts_session_id) is not int):
            raise ValueError("Quota lease does not match enrolled child/WTS session")
        if type(observed_wts_active) is not bool or not _valid_clock(now_mono):
            raise ValueError("WTS state or monotonic clock is invalid")
        delta = float(now_mono) - float(self.last_mono)
        self.last_mono = float(now_mono)
        if not observed_wts_active or delta < 0 or delta > self.max_tick_seconds:
            return 0.0
        return delta

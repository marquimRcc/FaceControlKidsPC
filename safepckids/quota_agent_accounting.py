"""Explicit quota ownership boundary for the Filhos agent.

LegacyLedgerQuota is the ONLY charging adapter used by the installed agent
until the service cutover is independently approved. The experimental
read-only broker client has NO debit/lock API and its responses are
non-authoritative until server process provenance has been validated.

Do not infer child identity or elapsed time from broker IPC payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Protocol


class LegacyLedger(Protocol):
    def charge(self, person_id: int, seconds: float, day: str) -> float: ...
    def remaining(self, person_id: int, day: str) -> float: ...


@dataclass(frozen=True, slots=True)
class QuotaTick:
    remaining_seconds: float
    charged_locally: bool
    may_enforce_lock: bool


class LegacyLedgerQuota:
    """Compatibility adapter until a secure service-only cutover occurs.

    Never instantiate this with the service-owned protected SQLite fixture.
    """

    def __init__(self, store: LegacyLedger):
        self._store = store

    def active_tick(self, *, child_id: int, seconds: float, day: str) -> QuotaTick:
        if type(child_id) is not int or child_id <= 0:
            raise ValueError("Invalid locally enrolled profile")
        if (type(seconds) not in (int, float) or not math.isfinite(seconds)
                or not 0.5 <= seconds <= 15.0):
            raise ValueError("Legacy elapsed seconds must be capped by session loop")
        if type(day) is not str:
            raise ValueError("Invalid local quota date")
        self._store.charge(child_id, float(seconds), day)
        remaining = self._store.remaining(child_id, day)
        if (type(remaining) not in (int, float) or
                not math.isfinite(remaining) or remaining < 0):
            raise ValueError("Legacy ledger returned invalid remaining time")
        return QuotaTick(float(remaining), charged_locally=True, may_enforce_lock=True)


@dataclass(frozen=True, slots=True)
class UntrustedBrokerObservation:
    """Telemetry only. It MUST NOT control Windows locking or facial login."""

    status: str
    remaining_seconds: float | None
    allowed_now: bool | None
    charged_locally: bool = False
    may_enforce_lock: bool = False


class BrokerLabReadOnlyQuota:
    """Read-only VM lab bridge, deliberately NOT an enforcement adapter.

    The current lab IPC client does not authenticate its server process.
    Even a syntactically valid GET_BALANCE is therefore only observational.
    This class does not accept a Storage instance or expose active_tick.
    """

    def __init__(self, query: Callable[[], Any]) -> None:
        if not callable(query):
            raise ValueError("Read-only quota query required")
        self._query = query

    def observe(self) -> UntrustedBrokerObservation:
        try:
            reply = self._query()
        except (OSError, RuntimeError, ValueError, TimeoutError):
            return UntrustedBrokerObservation("unavailable", None, None)
        if type(reply) is not dict or reply.get("status") != "OK":
            return UntrustedBrokerObservation("denied", None, None)
        from .quota_broker_protocol import BROKER_PROTOCOL
        if (set(reply) != {"status", "version", "remaining_seconds", "allowed_now"}
                or reply["version"] != BROKER_PROTOCOL
                or type(reply["allowed_now"]) is not bool):
            return UntrustedBrokerObservation("invalid", None, None)
        remaining = reply["remaining_seconds"]
        if (type(remaining) not in (int, float) or
                not math.isfinite(remaining) or remaining < 0 or
                (remaining == 0 and reply["allowed_now"])):
            return UntrustedBrokerObservation("invalid", None, None)
        return UntrustedBrokerObservation(
            "observed", float(remaining), reply["allowed_now"]
        )

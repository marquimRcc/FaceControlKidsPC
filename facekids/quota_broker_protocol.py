"""Minimal READ-ONLY protocol for a future protected quota broker.

Not a running Windows service. The Windows transport must impersonate the
connected client, extract its real token SID and independently resolve a
child ID from trusted session state; never take either from this JSON.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Any

from .ipc_json import parse_local_json
from .storage import Storage

MAX_REQUEST_BYTES = 512
BROKER_PROTOCOL = "FACEKIDS_QUOTA_V1"


@dataclass(frozen=True)
class VerifiedClient:
    """Values MUST be supplied by a trusted Windows token/WTS adapter."""
    token_sid: str
    expected_sid: str
    enrolled_child_id: int

    def authorized(self) -> bool:
        return (type(self.token_sid) is str and
                type(self.expected_sid) is str and
                self.token_sid.startswith("S-1-") and
                self.token_sid == self.expected_sid and
                type(self.enrolled_child_id) is int and
                self.enrolled_child_id > 0)


def _decode_request(raw: bytes) -> str:
    if type(raw) is not bytes or len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("Invalid broker request length or type")
    obj = parse_local_json(raw, max_bytes=MAX_REQUEST_BYTES)
    if type(obj) is not dict or set(obj) != {"version", "action"}:
        raise ValueError("Unexpected broker request fields")
    if obj["version"] != BROKER_PROTOCOL or type(obj["action"]) is not str:
        raise ValueError("Unsupported broker protocol")
    if obj["action"] not in ("PING", "GET_BALANCE"):
        raise ValueError("Broker mutation or unknown operation denied")
    return obj["action"]


def handle_broker_read(raw: bytes, identity: VerifiedClient, store: Storage,
                       *, observed_day: date | None = None) -> dict[str, Any]:
    """Serve a read-only status after the host authenticates the token.

    In particular, the caller cannot choose the enrolled child, a date,
    bonus, active WTS session, elapsed seconds or a debit identifier.
    This function does not authenticate the OS caller on its own.
    """
    try:
        if type(identity) is not VerifiedClient or not identity.authorized():
            return {"status": "DENY"}
        action = _decode_request(raw)
        if action == "PING":
            return {"status": "OK", "version": BROKER_PROTOCOL}
        today = date.today() if observed_day is None else observed_day
        if type(today) is not date:
            return {"status": "DENY"}
        remaining = store.remaining(identity.enrolled_child_id, today.isoformat())
        if not math.isfinite(remaining) or remaining < 0:
            return {"status": "DENY"}
        blocked, _ = store.is_curfew_active()
        return {
            "status": "OK", "version": BROKER_PROTOCOL,
            "remaining_seconds": remaining,
            "allowed_now": bool(remaining > 0 and not blocked),
        }
    except (TypeError, ValueError, KeyError, OverflowError):
        return {"status": "DENY"}

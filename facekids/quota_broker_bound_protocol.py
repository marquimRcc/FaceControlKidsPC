"""Dedicated read-only wire contract for a service-recognized child (VM ONLY).

One shared Windows SID may represent multiple children, so the reply comes
from the ACTIVE SERVICE FACE LEASE. No request field can select a child,
session, date, quota, clock, unlock state or mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Callable

from .ipc_json import parse_local_json

BOUND_PROTOCOL = "FACEKIDS_BOUND_QUOTA_V1"
BOUND_ACTION = "GET_BOUND_BALANCE"
MAX_BOUND_REQUEST_BYTES = 256


@dataclass(frozen=True, slots=True)
class BoundBalance:
    child_id: int
    remaining_seconds: float
    allowed_now: bool

    def __post_init__(self) -> None:
        if type(self.child_id) is not int or self.child_id <= 0:
            raise ValueError("Face-bound child ID must be positive")
        if (type(self.remaining_seconds) not in (float, int) or
                not math.isfinite(self.remaining_seconds) or
                self.remaining_seconds < 0):
            raise ValueError("Invalid service-owned quota balance")
        if type(self.allowed_now) is not bool:
            raise ValueError("Invalid service-owned allowed state")
        if self.remaining_seconds == 0 and self.allowed_now:
            raise ValueError("Zero remaining seconds cannot authorize usage")


def handle_bound_read(
    raw: bytes, *,
    verified_client_sid: str,
    read_bound: Callable[[str], BoundBalance | None],
) -> dict[str, object]:
    """No side effects: read face-lease snapshot only after OS token checks.

    `verified_client_sid` is supplied by the pipe server while impersonating
    its peer, never from a JSON request. Any other action fails closed.
    """
    try:
        if (type(raw) is not bytes or
                not 0 < len(raw) <= MAX_BOUND_REQUEST_BYTES or
                type(verified_client_sid) is not str or
                re.fullmatch(r"S-1-[0-9]+(?:-[0-9]+){1,14}", verified_client_sid) is None):
            return {"status": "DENY"}
        request = parse_local_json(raw, max_bytes=MAX_BOUND_REQUEST_BYTES)
        if (type(request) is not dict or
                set(request) != {"version", "action"} or
                request.get("version") != BOUND_PROTOCOL or
                request.get("action") != BOUND_ACTION):
            return {"status": "DENY"}
        result = read_bound(verified_client_sid)
        if type(result) is not BoundBalance:
            return {"status": "DENY"}
        return {
            "status": "OK",
            "version": BOUND_PROTOCOL,
            "child_id": result.child_id,
            "remaining_seconds": float(result.remaining_seconds),
            "allowed_now": result.allowed_now,
        }
    except (ValueError, TypeError, OverflowError, KeyError, OSError):
        return {"status": "DENY"}


def validate_bound_reply(reply: object) -> BoundBalance:
    """Lab-only parser: never use returned data for Windows enforcement."""
    if (type(reply) is not dict or
            set(reply) != {
                "status", "version", "child_id", "remaining_seconds",
                "allowed_now",
            } or
            reply.get("status") != "OK" or
            reply.get("version") != BOUND_PROTOCOL):
        raise ValueError("Invalid bound quota reply")
    return BoundBalance(
        child_id=reply["child_id"],
        remaining_seconds=reply["remaining_seconds"],
        allowed_now=reply["allowed_now"],
    )

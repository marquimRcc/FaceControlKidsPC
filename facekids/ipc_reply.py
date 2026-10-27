"""Defensive parsing of the in-session client's IPC authorization metadata.

FACEKIDS_IPC_V1 is public and is NOT a signature. A malicious local process
could still impersonate an unprotected pipe server. This function only blocks
malformed or stale decisions; trust in the Windows peer remains unverified.
"""
from __future__ import annotations

import math
import time
from typing import Any

IPC_PROTOCOL_MARKER = "FACEKIDS_IPC_V1"
MAX_RESPONSE_AGE_SECONDS = 15.0


def validated_pipe_allow(payload: Any, *, now: float | None = None) -> tuple[int, str, float] | None:
    if not isinstance(payload, dict):
        return None
    if (payload.get("status") != "ALLOW" or payload.get("user") != "Filhos"
            or payload.get("protocol_marker") != IPC_PROTOCOL_MARKER):
        return None
    cid = payload.get("child_id")
    remaining = payload.get("remaining")
    ts = payload.get("timestamp")
    name = payload.get("child_name")
    if (type(cid) is not int or cid <= 0
            or type(remaining) not in (int, float)
            or type(ts) not in (int, float)
            or not isinstance(name, str) or not name.strip() or len(name) > 80):
        return None
    try:
        balance = float(remaining)
        timestamp = float(ts)
        clock = time.time() if now is None else float(now)
    except (ValueError, TypeError, OverflowError):
        return None
    if (not math.isfinite(balance) or balance <= 0 or
            not math.isfinite(timestamp) or not math.isfinite(clock) or
            abs(clock - timestamp) > MAX_RESPONSE_AGE_SECONDS):
        return None
    return cid, name, timestamp

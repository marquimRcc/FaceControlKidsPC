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

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatedFaceObservation:
    status: str
    child_id: int
    child_name: str
    detected_ids: tuple[int, ...]
    face_count: int
    timestamp: float
    remaining: float


def validated_face_observation(payload: Any, *, now: float | None = None
                               ) -> ValidatedFaceObservation | None:
    """Validate ALL decisions affecting a profile or lock.

    This establishes well-formedness/freshness, NOT the pipe server identity.
    Only process an independently trusted reply from the local face service.
    """
    if type(payload) is not dict:
        return None
    status = payload.get("status")
    if status not in ("ALLOW", "DENY_QUOTA", "DENY_CURFEW"):
        return None
    if payload.get("protocol_marker") != IPC_PROTOCOL_MARKER:
        return None
    data = payload.get("data")
    if type(data) is not dict:
        return None
    cid, name = payload.get("child_id"), payload.get("child_name")
    if (type(cid) is not int or cid <= 0 or
            type(name) is not str or not name.strip() or len(name) > 80 or
            data.get("child_id") != cid or data.get("child_name") != name):
        return None
    ts, remaining = payload.get("timestamp"), payload.get("remaining")
    if type(ts) not in (int, float) or type(remaining) not in (int, float):
        return None
    ts, remaining = float(ts), float(remaining)
    clock = time.time() if now is None else float(now)
    if (not all(map(math.isfinite, (ts, remaining, clock))) or
            abs(clock - ts) > MAX_RESPONSE_AGE_SECONDS or remaining < 0 or
            (status == "ALLOW" and
             (payload.get("user") != "Filhos" or remaining <= 0)) or
            (status != "ALLOW" and remaining != 0)):
        return None
    detected = data.get("detected_ids")
    count = data.get("face_count")
    if (type(count) is not int or not 1 <= count <= 64 or
            type(detected) is not list or not 1 <= len(detected) <= count or
            any(type(n) is not int or n <= 0 for n in detected) or
            len(detected) != len(set(detected)) or cid not in detected):
        return None
    return ValidatedFaceObservation(
        status, cid, name, tuple(detected), count, ts, remaining)

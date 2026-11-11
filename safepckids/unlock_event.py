"""Validation of recent local face-unlock notification metadata.

This file is NOT a trusted authentication assertion. An unprivileged process
that can edit last_unlock.json may forge events. Validation here only prevents
invalid or stale metadata from changing quota attribution accidentally.
"""
from __future__ import annotations

from datetime import date
import math
import time
from typing import Any

MAX_EVENT_AGE_SECONDS = 600.0
MAX_FUTURE_SKEW_SECONDS = 2.0


def validated_unlock_event(payload: Any, *, now: float | None = None) -> tuple[int, str, float] | None:
    """Return (child ID, display name, timestamp) only for fresh metadata."""
    if not isinstance(payload, dict):
        return None
    timestamp = payload.get("timestamp")
    child_id = payload.get("child_id")
    if type(timestamp) not in (int, float) or type(child_id) is not int or child_id <= 0:
        return None
    ts = float(timestamp)
    clock = time.time() if now is None else float(now)
    if (not math.isfinite(ts) or not math.isfinite(clock) or ts <= 0
            or ts > clock + MAX_FUTURE_SKEW_SECONDS
            or clock - ts >= MAX_EVENT_AGE_SECONDS):
        return None
    try:
        if date.fromtimestamp(ts) != date.fromtimestamp(clock):
            return None
    except (ValueError, OverflowError, OSError):
        return None
    name = payload.get("child_name", f"Crianca {child_id}")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        return None
    return child_id, name, ts


def enrolled_display_name(store: Any, child_id: int) -> str | None:
    """Resolve the display name from SQLite, never from writable event JSON.

    This verifies only that the profile exists. It does NOT authenticate the
    face event's origin or prevent a forged event selecting another valid ID.
    """
    if type(child_id) is not int or child_id <= 0:
        return None
    for person_id, name, _ in store.people():
        if person_id == child_id:
            return str(name)
    return None

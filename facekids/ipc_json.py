"""Strict bounded decoding for local FaceKids IPC and unlock metadata.

Not an authentication primitive. File/pipe ownership is still enforced by
the OS and must be independently checked when accepting trusted decisions.
"""
from __future__ import annotations

import json
from typing import Any


def parse_local_json(data: str | bytes, *, max_bytes: int = 2047) -> Any:
    if not isinstance(data, (str, bytes)):
        raise ValueError("Local JSON payload must be UTF-8 text or bytes")
    if isinstance(data, bytes):
        text = data.decode("utf-8", errors="strict")
        raw_size = len(data)
    else:
        text = data
        raw_size = len(data.encode("utf-8"))
    if not text or raw_size > max_bytes:
        raise ValueError("Local JSON payload empty or oversized")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(number: str) -> Any:
        raise ValueError(f"Nonfinite JSON value: {number}")

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite,
    )

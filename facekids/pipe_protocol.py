"""Bounded command decoder for the FaceKids local named-pipe server.

This protects protocol framing, not the identity of connected clients.
"""
from __future__ import annotations


def decode_pipe_command(payload: bytes) -> tuple[str | None, str | None]:
    """Returns (command, error): errors are INVALID_REQUEST or INVALID_COMMAND."""
    if not isinstance(payload, bytes) or not payload or len(payload) > 512:
        return None, "INVALID_REQUEST"
    if b"\x00" in payload:
        return None, "INVALID_REQUEST"
    try:
        text = payload.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None, "INVALID_REQUEST"

    # Compatible with the current C++ and Python clients, which send a
    # single optional CRLF or LF terminator, never arbitrary whitespace.
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    if not text or any(c in text for c in "\r\n\t "):
        return None, "INVALID_REQUEST"
    if text not in ("AUTH_QUERY", "QUERY", "PING"):
        return None, "INVALID_COMMAND"
    return text, None

"""Isolated VM writer's read-only Named Pipe for the CURRENT FACE LEASE.

The request has no child ID, session, charge duration or unlock operation.
Only the server's Windows impersonation token determines the caller SID.
No SQLite object is given to this transport; it obtains a short-lived,
immutable service-loop snapshot. Remote pipes and duplicate first instances
are rejected. No service installation takes place here.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import threading
import time
from typing import Callable

from .quota_broker_bound_protocol import BoundBalance, handle_bound_read
from .quota_broker_scm_win import _sid_is_valid
from .quota_broker_transport_win import (
    SECURITY_ATTRIBUTES, LAB_PIPE_PREFIX, _configure_windows_api, _pipe_io,
    _impersonated_client_sid, PIPE_ACCESS_DUPLEX, FILE_FLAG_FIRST_PIPE_INSTANCE,
    FILE_FLAG_OVERLAPPED, PIPE_TYPE_MESSAGE, PIPE_READMODE_MESSAGE, PIPE_WAIT,
    PIPE_REJECT_REMOTE_CLIENTS,
)

BOUND_VM_PIPE = r"\\.\pipe\FaceKidsQuotaWriterBoundVmOnly"


def _process_bound_connection(
    *, kernel, advapi, pipe, expected_child_sid: str,
    bound_reader: Callable[[str], BoundBalance | None],
    stop_event: threading.Event, deadline: float,
) -> bool:
    """Consume at most one read-only request on an already connected pipe."""
    raw = ctypes.create_string_buffer(257)
    received_ok, length = _pipe_io(
        kernel, pipe, "read", buffer=raw, count=257,
        stop_event=stop_event, deadline=deadline,
    )
    if not received_ok or not 0 < length <= 256:
        return False
    sid = _impersonated_client_sid(pipe, kernel, advapi)
    if sid != expected_child_sid:
        response: dict[str, object] = {"status": "DENY"}
    else:
        response = handle_bound_read(
            raw.raw[:length], verified_client_sid=sid,
            read_bound=bound_reader,
        )
    payload = (json.dumps(
        response, separators=(",", ":"), allow_nan=False
    ) + "\n").encode("ascii")
    out = ctypes.create_string_buffer(payload)
    ok, sent = _pipe_io(
        kernel, pipe, "write", buffer=out, count=len(payload),
        stop_event=stop_event, deadline=deadline,
    )
    return bool(ok and sent == len(payload))


def _serve_bound_vm_pipe(
    *, expected_child_sid: str,
    bound_reader: Callable[[str], BoundBalance | None],
    stop_event: threading.Event,
    timeout_seconds: float, max_exchanges: int | None,
) -> bool:
    if os.name != "nt":
        raise RuntimeError("Windows-only bound quota pipe")
    if (type(expected_child_sid) is not str or
            not _sid_is_valid(expected_child_sid) or
            expected_child_sid in ("S-1-5-18", "S-1-5-19", "S-1-5-20") or
            not callable(bound_reader) or
            not isinstance(stop_event, threading.Event) or
            type(timeout_seconds) not in (float, int) or
            not 0.2 <= timeout_seconds <= 5 or
            max_exchanges not in (None, 1)):
        raise ValueError("Invalid protected VM bound pipe configuration")
    if stop_event.is_set():
        return False
    kernel, advapi = _configure_windows_api()
    # Create a SINGLE instance for the service lifecycle. Repeatedly
    # closing and recreating a FIRST_PIPE_INSTANCE pipe exposes a race:
    # a previous client still holding its handle makes CreateNamedPipe fail.
    # Reusing the same server handle avoids that race and name takeover.
    sddl = (
        "D:P(A;;GA;;;SY)(A;;GA;;;BA)"
        f"(A;;GRGW;;;{expected_child_sid})"
    )
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise PermissionError("Cannot establish child-specific named-pipe ACL")
    attributes = SECURITY_ATTRIBUTES(
        ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False
    )
    try:
        pipe = kernel.CreateNamedPipeW(
            BOUND_VM_PIPE,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT |
            PIPE_REJECT_REMOTE_CLIENTS,
            1, 1024, 1024, 0, ctypes.byref(attributes),
        )
        invalid = ctypes.c_void_p(-1).value
        if not pipe or pipe == invalid:
            raise RuntimeError("Cannot claim first instance of VM bound pipe")
        try:
            while not stop_event.is_set():
                deadline = time.monotonic() + float(timeout_seconds)
                connected = False
                try:
                    connected, _ = _pipe_io(
                        kernel, pipe, "connect",
                        stop_event=stop_event, deadline=deadline,
                    )
                    if not connected:
                        if max_exchanges == 1:
                            return False
                        continue
                    success = _process_bound_connection(
                        kernel=kernel, advapi=advapi, pipe=pipe,
                        expected_child_sid=expected_child_sid,
                        bound_reader=bound_reader, stop_event=stop_event,
                        deadline=deadline,
                    )
                    if max_exchanges == 1:
                        return success
                finally:
                    # Disconnect the client but retain the server instance.
                    # _pipe_io reaps overlapped requests before this returns.
                    if connected:
                        kernel.DisconnectNamedPipe(pipe)
            return False
        finally:
            kernel.CloseHandle(pipe)
    finally:
        kernel.LocalFree(descriptor)


def serve_one_bound_vm_request(
    *, expected_child_sid: str,
    bound_reader: Callable[[str], BoundBalance | None],
    stop_event: threading.Event,
    timeout_seconds: float = 1.0,
) -> bool:
    """One bounded read-only exchange in a disposable unit test."""
    return _serve_bound_vm_pipe(
        expected_child_sid=expected_child_sid,
        bound_reader=bound_reader, stop_event=stop_event,
        timeout_seconds=timeout_seconds, max_exchanges=1,
    )


def serve_bound_vm_requests(
    *, expected_child_sid: str,
    bound_reader: Callable[[str], BoundBalance | None],
    stop_event: threading.Event,
    timeout_seconds: float = 1.0,
) -> None:
    """Service lifecycle: retain the first pipe instance across all clients."""
    _serve_bound_vm_pipe(
        expected_child_sid=expected_child_sid,
        bound_reader=bound_reader, stop_event=stop_event,
        timeout_seconds=timeout_seconds, max_exchanges=None,
    )

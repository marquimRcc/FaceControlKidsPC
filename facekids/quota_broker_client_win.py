"""READ-ONLY Windows quota broker client, for explicit VM lab use only.

The connected pipe server's real process token MUST be LocalSystem. This
is only a lab defense-in-depth check; a valid SYSTEM SID alone does not prove
a protected policy, active facial lease, or safe Windows lock decision. Never
use this client for Credential Provider logon or LockWorkStation decisions.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from typing import Any

from .ipc_json import parse_local_json
from .quota_broker_protocol import BROKER_PROTOCOL
from .quota_broker_peer_win import require_system_pipe_server
from .quota_broker_transport_win import LAB_PIPE_PREFIX


def query_lab_balance(pipe_name: str, *, action: str = "GET_BALANCE") -> dict[str, Any]:
    """One synchronous request in the disposable lab; never call on the UI thread."""
    if (type(pipe_name) is not str or not pipe_name.startswith(LAB_PIPE_PREFIX)
            or action not in ("PING", "GET_BALANCE")):
        raise ValueError("Only read-only lab pipe operations are supported")
    if os.name != "nt":
        raise RuntimeError("Windows broker lab client requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.WaitNamedPipeW.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel.WriteFile.restype = wintypes.BOOL
    kernel.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    if not kernel.WaitNamedPipeW(pipe_name, 1000):
        raise TimeoutError("Lab broker pipe unavailable")
    handle = kernel.CreateFileW(pipe_name, 0xC0000000, 0, None, 3, 0, None)
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise OSError("Could not connect to lab broker")
    try:
        # Verify the actual connected process token. Untrusted JSON can never
        # attest the peer. A SYSTEM SID is still LAB defense-in-depth only.
        require_system_pipe_server(int(handle))
        data = json.dumps({"version": BROKER_PROTOCOL, "action": action},
                          separators=(",", ":")).encode("ascii")
        out = ctypes.create_string_buffer(data)
        sent = wintypes.DWORD()
        if not kernel.WriteFile(handle, out, len(data), ctypes.byref(sent), None):
            raise OSError("Could not write lab request")
        if sent.value != len(data):
            raise OSError("Incomplete lab request")
        buf = ctypes.create_string_buffer(2048)
        read = wintypes.DWORD()
        if not kernel.ReadFile(handle, buf, 2047, ctypes.byref(read), None):
            raise OSError("Could not read lab response")
        reply = parse_local_json(buf.raw[:read.value])
        if type(reply) is not dict or reply.get("status") not in ("OK", "DENY"):
            raise ValueError("Invalid broker reply")
        if reply["status"] == "DENY":
            if set(reply) != {"status"}:
                raise ValueError("Unexpected denied reply")
            return reply
        if reply.get("version") != BROKER_PROTOCOL:
            raise ValueError("Mismatched broker version")
        if action == "PING" and set(reply) != {"status", "version"}:
            raise ValueError("Unexpected PING reply")
        if action == "GET_BALANCE":
            if set(reply) != {"status", "version", "remaining_seconds", "allowed_now"}:
                raise ValueError("Unexpected balance reply")
            balance = reply["remaining_seconds"]
            if (type(balance) not in (int, float) or not math.isfinite(balance)
                    or balance < 0 or type(reply["allowed_now"]) is not bool
                    or (balance == 0 and reply["allowed_now"])):
                raise ValueError("Malformed broker balance")
        return reply
    finally:
        kernel.CloseHandle(handle)

"""VM-only read client for the currently recognized, service-bound child.

This client has no caller-provided child ID, elapsed time, unlock state,
database path or mutation operation. Query is bounded and pins the connected
pipe PID to the precise LocalSystem SCM writer; the result is observational,
NOT permission to block Windows or unlock a Credential Provider.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import time

from .ipc_json import parse_local_json
from .quota_broker_bound_protocol import (
    BOUND_ACTION, BOUND_PROTOCOL, BoundBalance, validate_bound_reply,
)
from .quota_broker_bound_transport_win import BOUND_VM_PIPE
from .quota_broker_peer_win import require_registered_system_service_pipe
from .quota_broker_transport_win import _pipe_io, FILE_FLAG_OVERLAPPED
from .quota_broker_writer_scm_win import VM_WRITER_SERVICE_NAME


def query_current_bound_vm_balance() -> BoundBalance | None:
    """Return service-authored snapshot, or None when no valid face lease."""
    if os.name != "nt":
        raise RuntimeError("Windows VM-only bound balance query")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.WaitNamedPipeW.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
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
    kernel.CreateEventW.argtypes = [
        ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR
    ]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL
    ]
    kernel.GetOverlappedResult.restype = wintypes.BOOL
    kernel.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.CancelIoEx.restype = wintypes.BOOL

    if not kernel.WaitNamedPipeW(BOUND_VM_PIPE, 1000):
        raise TimeoutError("SCM VM bound quota pipe unavailable")
    handle = kernel.CreateFileW(
        BOUND_VM_PIPE, 0xC0000000, 0, None, 3, FILE_FLAG_OVERLAPPED, None
    )
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise PermissionError("Cannot access child-specific VM bound pipe")
    try:
        require_registered_system_service_pipe(
            int(handle), VM_WRITER_SERVICE_NAME
        )
        request = json.dumps({
            "version": BOUND_PROTOCOL,
            "action": BOUND_ACTION,
        }, separators=(",", ":")).encode("ascii")
        deadline = time.monotonic() + 2.0
        out = ctypes.create_string_buffer(request)
        success, n = _pipe_io(
            kernel, handle, "write", buffer=out, count=len(request),
            deadline=deadline,
        )
        if not success or n != len(request):
            raise TimeoutError("Cannot submit bound quota read")
        data = ctypes.create_string_buffer(513)
        success, n = _pipe_io(
            kernel, handle, "read", buffer=data, count=513,
            deadline=deadline,
        )
        if not success or not 0 < n <= 512:
            raise TimeoutError("Bound quota service response unavailable")
        response = parse_local_json(data.raw[:n], max_bytes=512)
        if type(response) is dict and response == {"status": "DENY"}:
            return None
        return validate_bound_reply(response)
    finally:
        kernel.CloseHandle(handle)

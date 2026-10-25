"""Experimental Windows named-pipe host for READ-ONLY quota requests.

NOT installed or started by FaceKids; no Winlogon integration. This serves
ONE synthetic request at a time in an explicitly chosen lab pipe. A future
privileged service must supply a protected SID->enrolled-child map and own
the SQLite directory. It MUST NOT accept caller-supplied SID or child ID.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import threading
import time
from pathlib import Path
from typing import Mapping

from .quota_broker_protocol import VerifiedClient, handle_broker_read
from .quota_broker_read_store import ReadOnlyQuotaView

LAB_PIPE_PREFIX = r"\\.\pipe\FaceKidsQuotaBrokerLab-"
PIPE_ACCESS_DUPLEX = 0x00000003
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
ERROR_OPERATION_ABORTED = 995
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
ERROR_PIPE_CONNECTED = 535
TOKEN_QUERY = 0x0008
TOKEN_USER_CLASS = 1
SDDL_LAB = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)"


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", SID_AND_ATTRIBUTES)]


def _configure_windows_api():
    if os.name != "nt":
        raise RuntimeError("Windows Named Pipe diagnostic requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(SECURITY_ATTRIBUTES),
    ]
    kernel.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.ConnectNamedPipe.restype = wintypes.BOOL
    kernel.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    kernel.DisconnectNamedPipe.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel.WriteFile.restype = wintypes.BOOL
    kernel.GetCurrentThread.argtypes = []
    kernel.GetCurrentThread.restype = wintypes.HANDLE
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
        ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    ]
    kernel.GetOverlappedResult.restype = wintypes.BOOL
    kernel.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
    kernel.CancelIoEx.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.ImpersonateNamedPipeClient.argtypes = [wintypes.HANDLE]
    advapi.ImpersonateNamedPipeClient.restype = wintypes.BOOL
    advapi.RevertToSelf.argtypes = []
    advapi.RevertToSelf.restype = wintypes.BOOL
    advapi.OpenThreadToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenThreadToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    return kernel, advapi


def _impersonated_client_sid(pipe, kernel, advapi) -> str | None:
    """Capture actual client token SID and always revert impersonation."""
    if not advapi.ImpersonateNamedPipeClient(pipe):
        return None
    try:
        token = wintypes.HANDLE()
        if not advapi.OpenThreadToken(
            kernel.GetCurrentThread(), TOKEN_QUERY, True, ctypes.byref(token)
        ):
            return None
        try:
            size = wintypes.DWORD()
            advapi.GetTokenInformation(token, TOKEN_USER_CLASS, None, 0, ctypes.byref(size))
            if size.value < ctypes.sizeof(TOKEN_USER) or size.value > 65536:
                return None
            buf = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(
                token, TOKEN_USER_CLASS, buf, size.value, ctypes.byref(size)
            ):
                return None
            user = ctypes.cast(buf, ctypes.POINTER(TOKEN_USER)).contents
            p_text = ctypes.c_void_p()
            if not advapi.ConvertSidToStringSidW(user.User.Sid, ctypes.byref(p_text)):
                return None
            try:
                return ctypes.wstring_at(p_text)
            finally:
                kernel.LocalFree(p_text)
        finally:
            kernel.CloseHandle(token)
    finally:
        if not advapi.RevertToSelf():
            raise RuntimeError("Critical: failed to revert client impersonation")


def _pipe_io(kernel, pipe, operation, *, buffer=None, count: int = 0,
             stop_event: threading.Event | None = None,
             deadline: float) -> tuple[bool, int]:
    """Bounded overlapped connect/read/write with synchronous cancel cleanup.

    Returns (success, bytes). A timeout/stop fails closed. OVERLAPPED and event
    remain allocated until cancellation has been reaped by Windows.
    """
    event = kernel.CreateEventW(None, True, False, None)
    if not event:
        raise RuntimeError("Cannot create pipe IO completion event")
    ov = OVERLAPPED()
    ov.hEvent = event
    transferred = wintypes.DWORD()
    try:
        if operation == "connect":
            ok = kernel.ConnectNamedPipe(pipe, ctypes.byref(ov))
            if not ok and ctypes.get_last_error() == ERROR_PIPE_CONNECTED:
                return True, 0
        elif operation == "read":
            ok = kernel.ReadFile(pipe, buffer, count,
                                 ctypes.byref(transferred), ctypes.byref(ov))
        elif operation == "write":
            ok = kernel.WriteFile(pipe, buffer, count,
                                  ctypes.byref(transferred), ctypes.byref(ov))
        else:
            raise ValueError("Unknown pipe IO operation")
        if ok:
            return True, transferred.value
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            return False, 0

        while True:
            if stop_event is not None and stop_event.is_set():
                break
            left = deadline - time.monotonic()
            if left <= 0:
                break
            waited = kernel.WaitForSingleObject(event, min(100, max(1, int(left * 1000))))
            if waited == WAIT_OBJECT_0:
                if kernel.GetOverlappedResult(pipe, ctypes.byref(ov),
                                              ctypes.byref(transferred), False):
                    return True, transferred.value
                return False, 0
            if waited != WAIT_TIMEOUT:
                break

        kernel.CancelIoEx(pipe, ctypes.byref(ov))
        # Must reap I/O before returning: overlapped and event stay live.
        kernel.GetOverlappedResult(pipe, ctypes.byref(ov),
                                   ctypes.byref(transferred), True)
        return False, 0
    finally:
        kernel.CloseHandle(event)


def serve_one_lab_request(
    *, pipe_name: str, data_path: Path, enrolled_child_by_sid: Mapping[str, int],
    stop_event: threading.Event | None = None, timeout_seconds: float = 8.0,
) -> bool:
    """Serve one read-only request under test credentials, without installing.

    Lab name is mandatory and CreateNamedPipe uses FIRST_PIPE_INSTANCE to
    fail closed if another process already owns the name.
    """
    if (type(pipe_name) is not str or not pipe_name.startswith(LAB_PIPE_PREFIX)
            or len(pipe_name) > 240 or not enrolled_child_by_sid):
        raise ValueError("Explicit isolated lab pipe and trusted SID map required")
    for sid, child_id in enrolled_child_by_sid.items():
        if (type(sid) is not str or not sid.startswith("S-1-")
                or type(child_id) is not int or child_id <= 0):
            raise ValueError("Invalid protected SID-to-enrollment map")
    if (type(timeout_seconds) not in (float, int) or
            not 0.2 <= timeout_seconds <= 30.0 or
            stop_event is not None and not isinstance(stop_event, threading.Event)):
        raise ValueError("Invalid bounded pipe timeout or stop signal")
    if stop_event is not None and stop_event.is_set():
        return False
    deadline = time.monotonic() + float(timeout_seconds)
    # Prevent accidental wiring to the installed family database.
    # A VM host must run with a separate fixture database located in a
    # named lab directory; creation/permission changes are NOT performed.
    database_path = Path(data_path).resolve(strict=True)
    if "facekids-quota-lab" not in [part.casefold() for part in database_path.parts]:
        raise ValueError("Quota lab host refuses database outside facekids-quota-lab")
    kernel, advapi = _configure_windows_api()

    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        SDDL_LAB, 1, ctypes.byref(descriptor), None
    ):
        raise RuntimeError("Cannot establish explicit named-pipe DACL")
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
    try:
        pipe = kernel.CreateNamedPipeW(
            pipe_name,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT |
            PIPE_REJECT_REMOTE_CLIENTS,
            1, 2048, 2048, 0, ctypes.byref(sa),
        )
        invalid = ctypes.c_void_p(-1).value
        if not pipe or pipe == invalid:
            raise RuntimeError("Cannot claim first instance of lab pipe")
        try:
            connected, _ = _pipe_io(
                kernel, pipe, "connect", stop_event=stop_event, deadline=deadline
            )
            if not connected:
                return False
            raw = ctypes.create_string_buffer(513)
            ok, received = _pipe_io(
                kernel, pipe, "read", buffer=raw, count=513,
                stop_event=stop_event, deadline=deadline,
            )
            # ERROR_MORE_DATA / oversized request / canceled read -> reject.
            if not ok or received == 0 or received > 512:
                return False
            sid = _impersonated_client_sid(pipe, kernel, advapi)
            child = enrolled_child_by_sid.get(sid, 0) if sid else 0
            identity = VerifiedClient(sid or "", sid if child else "", child)
            if sid and child:
                with ReadOnlyQuotaView(Path(data_path)) as view:
                    result = handle_broker_read(raw.raw[:received], identity, view)
            else:
                result = {"status": "DENY"}
            encoded = (json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
            out = ctypes.create_string_buffer(encoded)
            sent_ok, written = _pipe_io(
                kernel, pipe, "write", buffer=out, count=len(encoded),
                stop_event=stop_event, deadline=deadline,
            )
            return bool(sent_ok and written == len(encoded))
        finally:
            kernel.DisconnectNamedPipe(pipe)
            kernel.CloseHandle(pipe)
    finally:
        kernel.LocalFree(descriptor)

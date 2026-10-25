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
from pathlib import Path
from typing import Mapping

from .quota_broker_protocol import VerifiedClient, handle_broker_read
from .storage import Storage

LAB_PIPE_PREFIX = r"\\.\pipe\FaceKidsQuotaBrokerLab-"
PIPE_ACCESS_DUPLEX = 0x00000003
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
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


def serve_one_lab_request(
    *, pipe_name: str, data_path: Path, enrolled_child_by_sid: Mapping[str, int]
) -> None:
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
            PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT |
            PIPE_REJECT_REMOTE_CLIENTS,
            1, 2048, 2048, 0, ctypes.byref(sa),
        )
        invalid = ctypes.c_void_p(-1).value
        if not pipe or pipe == invalid:
            raise RuntimeError("Cannot claim first instance of lab pipe")
        try:
            connected = kernel.ConnectNamedPipe(pipe, None)
            if not connected and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
                raise RuntimeError("Named-pipe client connection failed")
            raw = ctypes.create_string_buffer(513)
            read = wintypes.DWORD()
            ok = kernel.ReadFile(pipe, raw, 513, ctypes.byref(read), None)
            # ReadFile returns false for ERROR_MORE_DATA; fail closed.
            sid = _impersonated_client_sid(pipe, kernel, advapi) if ok else None
            child = enrolled_child_by_sid.get(sid, 0) if sid else 0
            identity = VerifiedClient(sid or "", sid if child else "", child)
            result = handle_broker_read(raw.raw[:read.value], identity,
                                        Storage(Path(data_path))) if ok and sid else {"status": "DENY"}
            encoded = (json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
            sent = wintypes.DWORD()
            out = ctypes.create_string_buffer(encoded)
            if not kernel.WriteFile(pipe, out, len(encoded), ctypes.byref(sent), None):
                raise RuntimeError("Failed to write lab response")
        finally:
            kernel.DisconnectNamedPipe(pipe)
            kernel.CloseHandle(pipe)
    finally:
        kernel.LocalFree(descriptor)

"""Read-only Windows WTS/token observation for the privileged quota worker.

WTSActive is NOT equivalent to an unlocked desktop. Callers must combine the
snapshot with trusted SCM session LOCK/UNLOCK events from WtsLockTracker.
WTSQueryUserToken generally requires LocalSystem + SeTcbPrivilege; an
unprivileged caller fails closed, never falling back to usernames.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os

from .quota_broker_wts import WtsSnapshot

_WTS_CONNECT_STATE = 8
_WTS_ACTIVE = 0
_WTS_INVALID_SESSION = 0xFFFFFFFF
_TOKEN_USER = 1


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TokenUser(ctypes.Structure):
    _fields_ = [("User", _SidAndAttributes)]


def observe_console_from_system() -> WtsSnapshot | None:
    """Return console session and verified token SID or None (never guess)."""
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)

    kernel.WTSGetActiveConsoleSessionId.argtypes = []
    kernel.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    wts.WTSQuerySessionInformationW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
    ]
    wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
    wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    wts.WTSFreeMemory.restype = None
    wts.WTSQueryUserToken.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    wts.WTSQueryUserToken.restype = wintypes.BOOL

    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    ]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL

    session = int(kernel.WTSGetActiveConsoleSessionId())
    if session in (0, _WTS_INVALID_SESSION):
        return None

    ptr = ctypes.c_void_p()
    nbytes = wintypes.DWORD()
    if not wts.WTSQuerySessionInformationW(
        None, session, _WTS_CONNECT_STATE, ctypes.byref(ptr), ctypes.byref(nbytes)
    ):
        return None
    try:
        if not ptr.value or nbytes.value < ctypes.sizeof(wintypes.DWORD):
            return None
        state = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD))[0]
        connected = int(state) == _WTS_ACTIVE
    finally:
        if ptr.value:
            wts.WTSFreeMemory(ptr)

    # A connected console with no authenticated user must not be considered
    # a child session. A process running as a normal child cannot query this.
    user_token = wintypes.HANDLE()
    if not wts.WTSQueryUserToken(session, ctypes.byref(user_token)):
        return None
    try:
        required = wintypes.DWORD()
        advapi.GetTokenInformation(user_token, _TOKEN_USER, None, 0, ctypes.byref(required))
        if required.value < ctypes.sizeof(_TokenUser) or required.value > 65536:
            return None
        buf = ctypes.create_string_buffer(required.value)
        if not advapi.GetTokenInformation(
            user_token, _TOKEN_USER, buf, required.value, ctypes.byref(required)
        ):
            return None
        user = ctypes.cast(buf, ctypes.POINTER(_TokenUser)).contents
        if not user.User.Sid:
            return None
        sid_string = ctypes.c_void_p()
        if not advapi.ConvertSidToStringSidW(user.User.Sid, ctypes.byref(sid_string)):
            return None
        try:
            if not sid_string.value:
                return None
            sid = ctypes.wstring_at(sid_string.value)
        finally:
            if sid_string.value:
                kernel.LocalFree(sid_string)
        return WtsSnapshot(session, sid, connected)
    finally:
        if user_token:
            kernel.CloseHandle(user_token)

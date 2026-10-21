"""Observação de sessão do SO; no Windows usa WTSInfoEx (sem pywin32).

Não debita tempo com sessão bloqueada, desconectada ou de estado desconhecido.
"""
from __future__ import annotations

import os
from enum import Enum


class SessionState(str, Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    UNKNOWN = "unknown"


def state_from_wts_flags(connect_state: int, session_flags: int) -> SessionState:
    """WTSActive=0, SessionFlags locked=0/unlocked=1 (Windows 10/11)."""
    if connect_state != 0:
        return SessionState.LOCKED
    if session_flags == 0:
        return SessionState.LOCKED
    if session_flags == 1:
        return SessionState.ACTIVE
    return SessionState.UNKNOWN


def current_session_state(session_id: int | None = None) -> SessionState:
    """Windows: consulta WTS; Linux: ACTIVE apenas em simulação experimental."""
    if os.name != "nt":
        return SessionState.ACTIVE  # Linux: CLI impede --lock até validar KDE
    import ctypes
    from ctypes import wintypes

    class WTSINFOEX_LEVEL1_W(ctypes.Structure):
        _fields_ = [
            ("SessionId", wintypes.DWORD),
            ("SessionState", ctypes.c_int),
            ("SessionFlags", wintypes.LONG),
            ("WinStationName", wintypes.WCHAR * 33),
            ("UserName", wintypes.WCHAR * 21),
            ("DomainName", wintypes.WCHAR * 18),
            ("LogonTime", ctypes.c_int64),
            ("ConnectTime", ctypes.c_int64),
            ("DisconnectTime", ctypes.c_int64),
            ("LastInputTime", ctypes.c_int64),
            ("CurrentTime", ctypes.c_int64),
            ("IncomingBytes", wintypes.DWORD),
            ("OutgoingBytes", wintypes.DWORD),
            ("IncomingFrames", wintypes.DWORD),
            ("OutgoingFrames", wintypes.DWORD),
            ("IncomingCompressedBytes", wintypes.DWORD),
            ("OutgoingCompressedBytes", wintypes.DWORD),
        ]

    class DATA(ctypes.Union):
        _fields_ = [("Level1", WTSINFOEX_LEVEL1_W)]

    class WTSINFOEX(ctypes.Structure):
        _fields_ = [("Level", wintypes.DWORD), ("Data", DATA)]

    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    query = wts.WTSQuerySessionInformationW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                      ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    release = wts.WTSFreeMemory
    release.argtypes = [ctypes.c_void_p]
    release.restype = None
    buffer = ctypes.c_void_p()
    num_bytes = wintypes.DWORD()
    try:
        # WTSSessionInfoEx=25; WTS_CURRENT_SESSION=0xffffffff.
        target_sid = 0xffffffff if session_id is None else session_id
        ok = query(None, target_sid, 25, ctypes.byref(buffer), ctypes.byref(num_bytes))
        if not ok or not buffer.value or num_bytes.value < ctypes.sizeof(WTSINFOEX):
            return SessionState.UNKNOWN
        info = ctypes.cast(buffer, ctypes.POINTER(WTSINFOEX)).contents
        if info.Level != 1:
            return SessionState.UNKNOWN
        return state_from_wts_flags(info.Data.Level1.SessionState,
                                    info.Data.Level1.SessionFlags)
    except (OSError, ValueError):
        return SessionState.UNKNOWN
    finally:
        if buffer.value:
            release(buffer)

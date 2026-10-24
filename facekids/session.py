"""Observação de sessão do SO; no Windows usa WTSInfoEx (sem pywin32).

Não debita tempo com sessão bloqueada, desconectada ou de estado desconhecido.
"""
from __future__ import annotations

import os
import subprocess
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
    """Consulta o bloqueio da sessão atual; falhas são sempre ``UNKNOWN``."""
    if os.name != "nt":
        return current_linux_session_state(
            None if session_id is None else str(session_id)
        )
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


def parse_loginctl_properties(output: str) -> SessionState:
    """Converte ``loginctl show-session`` sem presumir que a sessão está ativa.

    ``LockedHint`` é a indicação publicada pelo gerenciador gráfico. A ausência
    da propriedade ou qualquer valor desconhecido falha de forma fechada.
    """
    properties = {}
    for raw_line in output.splitlines():
        key, separator, value = raw_line.partition("=")
        if separator:
            properties[key.strip().casefold()] = value.strip().casefold()
    if properties.get("active") != "yes":
        return SessionState.LOCKED if properties.get("active") == "no" else SessionState.UNKNOWN
    if properties.get("state") not in {"active", "online"}:
        return SessionState.UNKNOWN
    locked = properties.get("lockedhint")
    if locked == "yes":
        return SessionState.LOCKED
    if locked == "no":
        return SessionState.ACTIVE
    return SessionState.UNKNOWN


def linux_display_session(user: str | int | None = None) -> str | None:
    """Retorna a sessão gráfica principal publicada pelo logind."""
    explicit = os.environ.get("XDG_SESSION_ID", "").strip()
    if user is None and explicit and all(ch.isalnum() or ch in "_-" for ch in explicit):
        return explicit
    target_user = str(os.getuid()) if user is None else str(user).strip()
    if not target_user or not all(ch.isalnum() or ch in "_-" for ch in target_user):
        return None
    try:
        result = subprocess.run(
            ["loginctl", "show-user", target_user, "--property=Display", "--value"],
            check=True, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    candidate = result.stdout.strip()
    if candidate and all(ch.isalnum() or ch in "_-" for ch in candidate):
        return candidate
    return None


def current_linux_session_state(session_id: str | None = None) -> SessionState:
    """Obtém Active/State/LockedHint do logind para KDE/SDDM."""
    target = session_id or linux_display_session()
    if not target:
        return SessionState.UNKNOWN
    try:
        result = subprocess.run(
            ["loginctl", "show-session", target,
             "--property=Active", "--property=State", "--property=LockedHint"],
            check=True, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return SessionState.UNKNOWN
    return parse_loginctl_properties(result.stdout)

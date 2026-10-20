"""Read-only Windows WTS session inventory for the parent's PC.

No Windows credentials, COM registrations, biometrics, service installation,
session locking or registry modifications. Display names obtained via WTS are
ONLY diagnostic and MUST NOT be trusted as authorization identities.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum


class LockView(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SessionObservation:
    session_id: int
    username: str
    state: LockView


def classify(connect_state: int, flags: int | None) -> LockView:
    """Windows 10/11 WTSInfoEx semantics; disconnected is NEVER auth-eligible."""
    if type(connect_state) is not int:
        return LockView.UNKNOWN
    if connect_state != 0:
        return LockView.INACTIVE
    if flags == 0:
        return LockView.LOCKED
    if flags == 1:
        return LockView.UNLOCKED
    return LockView.UNKNOWN


def summarize(observations: list[SessionObservation], target: str = "Filhos") -> dict:
    """Summarize evidence only; matching a username is not a trusted SID check."""
    matching = [row for row in observations if row.username.casefold() == target.casefold()]
    return {
        "sessions": len(observations),
        "target_present": bool(matching),
        "target_locked": sum(row.state is LockView.LOCKED for row in matching),
        "target_inactive": sum(row.state is LockView.INACTIVE for row in matching),
        "target_unknown": sum(row.state is LockView.UNKNOWN for row in matching),
    }


class _WTS_SESSION_INFOW(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("pWinStationName", wintypes.LPWSTR),
        ("State", ctypes.c_int),
    ]


class _WTSINFOEX_LEVEL1W(ctypes.Structure):
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


class _WTSINFOEX_DATA(ctypes.Union):
    _fields_ = [("Level1", _WTSINFOEX_LEVEL1W)]


class _WTSINFOEX(ctypes.Structure):
    _fields_ = [("Level", wintypes.DWORD), ("Data", _WTSINFOEX_DATA)]


def enumerate_local_sessions() -> list[SessionObservation]:
    """Run only on an actual Windows machine. Unknown WTS state fails closed."""
    if os.name != "nt":
        raise RuntimeError("Windows WTS diagnostic requires Windows 10/11")
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    enum = wts.WTSEnumerateSessionsW
    enum.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_WTS_SESSION_INFOW)),
        ctypes.POINTER(wintypes.DWORD),
    ]
    enum.restype = wintypes.BOOL
    query = wts.WTSQuerySessionInformationW
    query.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
    ]
    query.restype = wintypes.BOOL
    free = wts.WTSFreeMemory
    free.argtypes = [ctypes.c_void_p]
    free.restype = None

    table = ctypes.POINTER(_WTS_SESSION_INFOW)()
    count = wintypes.DWORD()
    if not enum(None, 0, 1, ctypes.byref(table), ctypes.byref(count)):
        raise OSError(ctypes.get_last_error(), "WTSEnumerateSessionsW failed")

    result: list[SessionObservation] = []
    try:
        for index in range(count.value):
            entry = table[index]
            session_id = int(entry.SessionId)
            username = ""
            user_buffer = ctypes.c_void_p()
            user_bytes = wintypes.DWORD()
            try:
                if query(None, session_id, 5, ctypes.byref(user_buffer), ctypes.byref(user_bytes)):
                    if user_buffer.value and user_bytes.value >= ctypes.sizeof(wintypes.WCHAR):
                        username = ctypes.wstring_at(
                            user_buffer.value, max(0, user_bytes.value // ctypes.sizeof(wintypes.WCHAR) - 1)
                        ).split("\x00", 1)[0]
            finally:
                if user_buffer.value:
                    free(user_buffer)

            lock = LockView.UNKNOWN
            extra_buffer = ctypes.c_void_p()
            extra_bytes = wintypes.DWORD()
            try:
                if query(None, session_id, 25, ctypes.byref(extra_buffer), ctypes.byref(extra_bytes)):
                    if extra_buffer.value and extra_bytes.value >= ctypes.sizeof(_WTSINFOEX):
                        ex = ctypes.cast(extra_buffer, ctypes.POINTER(_WTSINFOEX)).contents
                        l1 = ex.Data.Level1
                        if ex.Level == 1 and l1.SessionId == session_id:
                            lock = classify(int(l1.SessionState), int(l1.SessionFlags))
            finally:
                if extra_buffer.value:
                    free(extra_buffer)

            result.append(SessionObservation(session_id, username, lock))
    finally:
        if table:
            free(ctypes.cast(table, ctypes.c_void_p))
    return result


def main() -> int:
    print("FaceKids - diagnostico WTS do Windows (somente leitura)")
    print("Observacao: nomes de conta nao validam SIDs para autorizacao.")
    observations = enumerate_local_sessions()
    for item in observations:
        print(f"Sessao {item.session_id}: usuario={item.username or '(nenhum)'} | {item.state.value}")
    summary = summarize(observations)
    if not summary["target_present"]:
        print("Filhos: nenhuma sessao aberta neste momento (normal apos sair da conta).")
    else:
        print(
            "Filhos: sessoes presentes, bloqueadas={target_locked}, "
            "inativas={target_inactive}, desconhecidas={target_unknown}".format(**summary)
        )
    print("PASS: leitura de sessoes concluida; nenhuma alteracao de login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

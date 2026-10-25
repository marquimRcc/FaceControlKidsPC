"""Windows-only server process provenance for a named-pipe handle.

Check the actual *server end* of the connected Named Pipe, not a PID sent
in its JSON reply. LocalSystem SID alone is a necessary, not sufficient,
condition for future enforcement. This lab peer check does not approve
domestic installation or remove the need for a protected pipe name/ACL.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_SYSTEM_SID = "S-1-5-18"


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER_STRUCT(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


def require_system_pipe_server(handle: int) -> int:
    """Validate the connected server process TOKEN_USER or fail closed.

    A SYSTEM SID check is insufficient by itself to trust a future billing
    response. The caller must also validate protected configuration and
    enforce bounded IPC; this is only a defense-in-depth LAB gate.
    """
    if os.name != "nt":
        raise RuntimeError("Windows-only Named Pipe peer authentication")
    if type(handle) is not int or handle in (0, -1, ctypes.c_void_p(-1).value):
        raise ValueError("Invalid named-pipe handle")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)
    ]
    kernel.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    ]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL

    server_pid = wintypes.ULONG()
    if not kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(server_pid)):
        raise PermissionError("Cannot identify quota lab pipe server process")
    if not server_pid.value:
        raise PermissionError("Quota lab pipe server has no valid PID")
    process = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, server_pid.value)
    if not process:
        raise PermissionError("Cannot inspect connected quota lab pipe server")
    try:
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
            raise PermissionError("Cannot verify quota lab pipe server token")
        try:
            size = wintypes.DWORD()
            advapi.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
            if not ctypes.sizeof(_TOKEN_USER_STRUCT) <= size.value <= 65536:
                raise PermissionError("Invalid quota lab server token length")
            raw = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(
                token, _TOKEN_USER, raw, size.value, ctypes.byref(size)
            ):
                raise PermissionError("Quota lab server token query failed")
            user = ctypes.cast(raw, ctypes.POINTER(_TOKEN_USER_STRUCT)).contents
            if not user.User.Sid:
                raise PermissionError("Quota lab server has no SID")
            sid_ptr = ctypes.c_void_p()
            if not advapi.ConvertSidToStringSidW(user.User.Sid, ctypes.byref(sid_ptr)):
                raise PermissionError("Cannot convert quota lab server SID")
            try:
                sid = ctypes.wstring_at(sid_ptr.value) if sid_ptr.value else ""
            finally:
                if sid_ptr.value:
                    kernel.LocalFree(sid_ptr)
            if sid != _SYSTEM_SID:
                raise PermissionError("Quota lab pipe not hosted by LocalSystem")
            return int(server_pid.value)
        finally:
            if token:
                kernel.CloseHandle(token)
    finally:
        kernel.CloseHandle(process)


# Restrict the lab client to one registered SCM service. Its running PID
# must equal the PID of the connected pipe server. A random user process
# cannot satisfy this, even if it clones the pipe name and JSON responses.
_SC_MANAGER_CONNECT = 0x0001
_SERVICE_QUERY_CONFIG = 0x0001
_SERVICE_QUERY_STATUS = 0x0004
_SERVICE_RUNNING = 4


class _SERVICE_STATUS_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwServiceFlags", wintypes.DWORD),
    ]


class _QUERY_SERVICE_CONFIG(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwStartType", wintypes.DWORD),
        ("dwErrorControl", wintypes.DWORD),
        ("lpBinaryPathName", wintypes.LPWSTR),
        ("lpLoadOrderGroup", wintypes.LPWSTR),
        ("dwTagId", wintypes.DWORD),
        ("lpDependencies", wintypes.LPWSTR),
        ("lpServiceStartName", wintypes.LPWSTR),
        ("lpDisplayName", wintypes.LPWSTR),
    ]


def require_registered_system_service_pipe(handle: int, service_name: str) -> int:
    """Pin connected pipe server PID to the running LocalSystem SCM service.

    Works under a standard user token with SERVICE_QUERY_STATUS and
    SERVICE_QUERY_CONFIG, without requiring access to SYSTEM process tokens.
    The service name is supplied by trusted application code, not IPC/JSON.
    """
    from .quota_broker_scm_win import SERVICE_NAME
    from .quota_vm_policy_constants import VM_WRITER_SERVICE_NAME
    if os.name != "nt":
        raise RuntimeError("Windows SCM service provenance required")
    if type(handle) is not int or not handle or handle == ctypes.c_void_p(-1).value:
        raise ValueError("Invalid pipe handle")
    if type(service_name) is not str or service_name not in (
        SERVICE_NAME, VM_WRITER_SERVICE_NAME
    ):
        raise ValueError("Unexpected broker service name")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)
    ]
    kernel.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    advapi.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.OpenSCManagerW.restype = wintypes.HANDLE
    advapi.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.OpenServiceW.restype = wintypes.HANDLE
    advapi.QueryServiceStatusEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.QueryServiceStatusEx.restype = wintypes.BOOL
    advapi.QueryServiceConfigW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.QueryServiceConfigW.restype = wintypes.BOOL
    advapi.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    advapi.CloseServiceHandle.restype = wintypes.BOOL
    pipe_pid = wintypes.ULONG()
    if not kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(pipe_pid)):
        raise PermissionError("Cannot identify connected named-pipe server")
    if not pipe_pid.value:
        raise PermissionError("Missing named-pipe server PID")

    manager = advapi.OpenSCManagerW(None, None, _SC_MANAGER_CONNECT)
    if not manager:
        raise PermissionError("SCM cannot be queried by quota client")
    try:
        service = advapi.OpenServiceW(
            manager, service_name, _SERVICE_QUERY_STATUS | _SERVICE_QUERY_CONFIG
        )
        if not service:
            raise PermissionError("Expected quota lab service unavailable")
        try:
            status = _SERVICE_STATUS_PROCESS()
            required = wintypes.DWORD()
            if not advapi.QueryServiceStatusEx(
                service, 0, ctypes.byref(status), ctypes.sizeof(status),
                ctypes.byref(required),
            ):
                raise PermissionError("Cannot verify SCM process status")
            if (status.dwCurrentState != _SERVICE_RUNNING or
                    not status.dwProcessId or status.dwProcessId != pipe_pid.value):
                raise PermissionError("Named-pipe PID differs from registered running service")

            required = wintypes.DWORD()
            # Standard two-call QueryServiceConfig pattern. Never trust
            # an account name provided in the Named Pipe response.
            advapi.QueryServiceConfigW(service, None, 0, ctypes.byref(required))
            if required.value < ctypes.sizeof(_QUERY_SERVICE_CONFIG) or required.value > 65536:
                raise PermissionError("Invalid SCM service configuration size")
            raw = ctypes.create_string_buffer(required.value)
            if not advapi.QueryServiceConfigW(
                service, raw, required.value, ctypes.byref(required)
            ):
                raise PermissionError("Cannot read registered SCM service account")
            settings = ctypes.cast(raw, ctypes.POINTER(_QUERY_SERVICE_CONFIG)).contents
            principal = (settings.lpServiceStartName or "").casefold()
            if principal not in ("localsystem", "nt authority\\system", ".\\localsystem"):
                raise PermissionError("Registered quota lab service is not LocalSystem")
            return int(pipe_pid.value)
        finally:
            advapi.CloseServiceHandle(service)
    finally:
        advapi.CloseServiceHandle(manager)

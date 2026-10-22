"""Explicit Win32 signatures: HANDLE is pointer-sized, including input values."""
import ctypes
from ctypes import wintypes as w


def configure_kernel32(kernel32):
    signatures = {
        "CreateMutexW": ([w.LPVOID, w.BOOL, w.LPCWSTR], w.HANDLE),
        "CreateNamedPipeW": ([w.LPCWSTR] + [w.DWORD] * 6 + [w.LPVOID], w.HANDLE),
        "ConnectNamedPipe": ([w.HANDLE, w.LPVOID], w.BOOL),
        "DisconnectNamedPipe": ([w.HANDLE], w.BOOL),
        "FlushFileBuffers": ([w.HANDLE], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "LocalFree": ([w.LPVOID], w.LPVOID),
        "WaitNamedPipeW": ([w.LPCWSTR, w.DWORD], w.BOOL),
        "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID,
                         w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
        "CreateEventW": ([w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
        "ReadFile": ([w.HANDLE, w.LPVOID, w.DWORD, w.LPDWORD, w.LPVOID], w.BOOL),
        "WriteFile": ([w.HANDLE, w.LPVOID, w.DWORD, w.LPDWORD, w.LPVOID], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetOverlappedResult": ([w.HANDLE, w.LPVOID, w.LPDWORD, w.BOOL], w.BOOL),
        "CancelIoEx": ([w.HANDLE, w.LPVOID], w.BOOL),
        "CancelIo": ([w.HANDLE], w.BOOL),
        "GetLastError": ([], w.DWORD),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel32, name, None)
        if isinstance(function, ctypes._CFuncPtr):
            function.argtypes, function.restype = args, result
    return kernel32

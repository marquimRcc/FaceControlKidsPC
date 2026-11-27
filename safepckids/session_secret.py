"""Helpers for generated credentials and Windows process execution."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import string
import subprocess
import sys
from typing import List, Sequence, Union

PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SafePCKids"
SECURITY_DIR = PROGRAMDATA_DIR / "security"
TOKEN_FILE = SECURITY_DIR / "filhos_session.token"


def _run_win_cmd(
    cmd: Union[List[str], Sequence[str]],
    timeout: float = 15.0,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Executa comando do Windows com seguranca: sem heranca de handles e sem travar em pipes."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    if not capture:
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                startupinfo=startupinfo,
                creationflags=creation_flags,
            )
            p.wait(timeout=timeout)
            return subprocess.CompletedProcess(cmd, p.returncode or 0, "", "")
        except subprocess.TimeoutExpired:
            p.kill()
            return subprocess.CompletedProcess(cmd, -1, "", "timeout")
        except Exception as e:
            return subprocess.CompletedProcess(cmd, -1, "", str(e))

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            startupinfo=startupinfo,
            creationflags=creation_flags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, -1, "", f"Timeout after {timeout}s: {exc}")
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, -1, "", str(exc))


def generate_secure_secret(length: int = 32) -> str:
    """Gera uma credencial de alta entropia para a conta Windows Filhos."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in candidate)
        has_lower = any(c.islower() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        has_symbol = any(c in "!@#$%^&*" for c in candidate)
        if has_upper and has_lower and has_digit and has_symbol:
            return candidate

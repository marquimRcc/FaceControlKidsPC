"""Dedicated VM-only child agent: broker observations without SQLite or lock.

This is NOT launched by the family installer or filhos_agent.run_agent().
Unlike the legacy agent, its dependency graph contains no Storage and there
is no charge, face recognition, token unlock or LockWorkStation operation.
A protected HKLM policy (not a child-writable env var) gates the diagnostic.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from typing import Callable

from .quota_broker_bound_protocol import BoundBalance
from .quota_broker_writer_scm_win import VM_WRITER_REGISTRY_PATH


@dataclass(frozen=True, slots=True)
class VmBoundStatus:
    state: str
    child_id: int | None = None
    remaining_seconds: float | None = None
    charged_locally: bool = False
    may_enforce_lock: bool = False


class VmBoundChildObserver:
    """No Storage reference, no write and no lock operation."""

    def __init__(self, read_current: Callable[[], BoundBalance | None]):
        if not callable(read_current):
            raise ValueError("VM-only read callback required")
        self._read = read_current

    def observe(self) -> VmBoundStatus:
        try:
            balance = self._read()
        except (OSError, ValueError, RuntimeError, TimeoutError, PermissionError):
            return VmBoundStatus("unavailable")
        if balance is None:
            return VmBoundStatus("unverified")
        if type(balance) is not BoundBalance:
            return VmBoundStatus("invalid")
        return VmBoundStatus(
            state="observed",
            child_id=balance.child_id,
            remaining_seconds=balance.remaining_seconds,
        )


def require_vm_bound_policy(*, actual_windows_sid: str) -> None:
    """Require the exact child SID from protected HKLM, without reading SQLite."""
    if os.name != "nt":
        raise RuntimeError("VM bound agent supports Windows only")
    import winreg
    from .quota_broker_scm_win import _sid_is_valid

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VM_WRITER_REGISTRY_PATH,
                        0, winreg.KEY_READ) as key:
        expected_values = {
            "VmLabOnly": winreg.REG_DWORD,
            "WriterEnabled": winreg.REG_DWORD,
            "ChildSid": winreg.REG_SZ,
            "ServiceSid": winreg.REG_SZ,
        }
        values = {}
        for name, expected_type in expected_values.items():
            value, kind = winreg.QueryValueEx(key, name)
            if kind != expected_type:
                raise PermissionError("Protected VM policy type is invalid")
            values[name] = value
    if (type(actual_windows_sid) is not str or
            not _sid_is_valid(actual_windows_sid) or
            values["VmLabOnly"] != 1 or
            values["WriterEnabled"] != 1 or
            values["ServiceSid"] != "S-1-5-18" or
            values["ChildSid"] != actual_windows_sid):
        raise PermissionError("VM read-only observer not authorized")


def observe_vm_bound_once() -> VmBoundStatus:
    """Reads only HKLM and the SCM Named Pipe as this real Windows user."""
    if os.name != "nt":
        raise RuntimeError("Windows-only quota VM")
    from .filhos_quota_vm_readonly import effective_windows_sid
    from .quota_broker_bound_client_win import query_current_bound_vm_balance
    require_vm_bound_policy(actual_windows_sid=effective_windows_sid())
    return VmBoundChildObserver(query_current_bound_vm_balance).observe()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="VM-only observed facial quota; no debits, windows locks or DB reads"
    )
    parser.add_argument("--vm-lab-only", action="store_true",
                        help="Explicit consent for a disposable isolated VM")
    options = parser.parse_args(argv)
    if not options.vm_lab_only:
        parser.error("Use --vm-lab-only on a disposable VM, never on the family PC")
    try:
        observation = observe_vm_bound_once()
    except (OSError, ValueError, RuntimeError, PermissionError):
        print("VM READ ONLY: unavailable; no charge, no lock")
        return 2
    if observation.state != "observed":
        print(f"VM READ ONLY: {observation.state}; no charge, no lock")
        return 2
    print(f"VM READ ONLY: child={observation.child_id}, "
          f"remaining={observation.remaining_seconds:.0f}s; no charge, no lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

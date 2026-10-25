"""VM-only read-only Filhos quota probe — never an installed parental agent.

No SQLite opens, debit API, unlock event or LockWorkStation call. Uses a
protected HKLM lab policy and the calling Windows TOKEN_USER to determine
whether the process may request a balance. The server is additionally pinned
by its actual pipe PID to the registered LocalSystem SCM service.

Status is deliberately NON-AUTHORITATIVE: this probe must never drive a
family quota, screen lock or Credential Provider.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import sys
from typing import Any, Callable, Mapping

from .quota_agent_accounting import BrokerLabReadOnlyQuota, UntrustedBrokerObservation


@dataclass(frozen=True)
class VmLabSnapshot:
    status: str
    balance_seconds: float | None
    may_enforce_lock: bool = False
    charged_locally: bool = False


def observe_vm_lab_once(
    *, trusted_mapping: Mapping[str, int],
    actual_token_sid: str,
    pipe_name: str,
    query_lab: Callable[[str], Any],
) -> VmLabSnapshot:
    """Pure boundary; no filesystem or Windows session mutations."""
    if (type(actual_token_sid) is not str or
            type(trusted_mapping) is not dict or len(trusted_mapping) != 1 or
            actual_token_sid not in trusted_mapping or
            type(trusted_mapping[actual_token_sid]) is not int or
            trusted_mapping[actual_token_sid] <= 0):
        return VmLabSnapshot("unauthorized", None)
    from .quota_broker_transport_win import LAB_PIPE_PREFIX
    import re
    if (type(pipe_name) is not str or not pipe_name.startswith(LAB_PIPE_PREFIX)
            or re.fullmatch(r"[0-9a-f]{32}", pipe_name[len(LAB_PIPE_PREFIX):]) is None):
        return VmLabSnapshot("invalid-policy", None)
    state = BrokerLabReadOnlyQuota(lambda: query_lab(pipe_name)).observe()
    return VmLabSnapshot(state.status, state.remaining_seconds)


def effective_windows_sid() -> str:
    """Read actual thread token when impersonating; else process token."""
    if os.name != "nt":
        raise RuntimeError("VM child quota probe requires Windows")
    import win32api
    import win32con
    import win32security
    import pywintypes

    try:
        token = win32security.OpenThreadToken(
            win32api.GetCurrentThread(), win32con.TOKEN_QUERY, True
        )
    except pywintypes.error as exc:
        # ERROR_NO_TOKEN is the only acceptable reason to fall back.
        if exc.winerror != 1008:
            raise PermissionError("Cannot determine current Windows thread token") from exc
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
    try:
        principal = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return win32security.ConvertSidToStringSid(principal)
    finally:
        token.Close()


def run_vm_lab_probe() -> VmLabSnapshot:
    """Fetch only explicitly opted-in, protected SCM LAB policy."""
    if os.name != "nt":
        raise RuntimeError("Windows-only VM quota lab")
    from .quota_broker_client_win import query_lab_balance
    from .quota_broker_scm_win import read_hklm_lab_configuration
    pipe_name, _synthetic_database_path, mapping = read_hklm_lab_configuration()
    return observe_vm_lab_once(
        trusted_mapping=mapping,
        actual_token_sid=effective_windows_sid(),
        pipe_name=pipe_name,
        query_lab=query_lab_balance,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only LAB quota diagnostic; never a family enforcement agent"
    )
    parser.add_argument("--vm-lab-only", action="store_true",
                        help="Explicit acknowledgement of disposable VM lab")
    options = parser.parse_args(argv)
    if not options.vm_lab_only:
        parser.error("Explicit --vm-lab-only opt-in required")
    try:
        report = run_vm_lab_probe()
    except (OSError, RuntimeError, PermissionError, ValueError):
        print("FAIL-CLOSED: protected VM quota lab unavailable; no write or lock")
        return 2
    if report.status != "observed":
        print(f"READ-ONLY VM LAB: {report.status}; no write or lock")
        return 2
    print(f"READ-ONLY VM LAB: balance={report.balance_seconds:.0f}s; "
          "NOT AUTHORITATIVE; no write or lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

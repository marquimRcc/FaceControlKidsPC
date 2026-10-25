"""Extra recovery gate for the DISPOSABLE Windows quota writer VM.

This validates protected HKLM, VM fixture/NTFS and the actual SCM state
instead of trusting an application-supplied boolean. It does NOT guarantee
that unrelated processes have closed all file handles; the SQLite WAL and
exclusive access checks in quota_vm_cutover remain necessary. There is no
installer, service registration, restart or family state mutation here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .quota_vm_policy_constants import VM_WRITER_SERVICE_NAME
from .quota_broker_writer_scm_win import (
    read_hklm_writer_vm_config, assert_protected_vm_ledger_acl,
)

# Exact Windows SCM SERVICE_STOPPED value. Never accept STOP_PENDING/PAUSED.
SCM_STOPPED = 1


def require_recovery_preconditions(
    *, expected_database: Path, configured_database: Path,
    registered_service_state: int, acl_is_protected: bool,
) -> bool:
    """Pure policy evaluation for testing. No caller-submitted 'ready' bool."""
    if (type(expected_database) is not Path or
            type(configured_database) is not Path or
            expected_database != configured_database):
        raise PermissionError("Recovery DB differs from protected VM configuration")
    if type(registered_service_state) is not int or registered_service_state != SCM_STOPPED:
        raise PermissionError("VM writer has not reached SERVICE_STOPPED")
    if acl_is_protected is not True:
        raise PermissionError("Protected VM files ACL is not verified")
    return True


def query_registered_writer_state() -> int:
    """Read only the exact VM quota writer's state from Windows SCM."""
    if os.name != "nt":
        raise RuntimeError("Windows SCM-only recovery gate")
    import win32service
    import pywintypes

    scm = win32service.OpenSCManager(
        None, None, win32service.SC_MANAGER_CONNECT,
    )
    try:
        try:
            service = win32service.OpenService(
                scm, VM_WRITER_SERVICE_NAME,
                win32service.SERVICE_QUERY_STATUS,
            )
        except pywintypes.error as exc:
            # A service that has disappeared is NOT a reliable offline
            # attestation. Force operator diagnosis instead of guessing.
            raise PermissionError("Registered VM writer service missing") from exc
        try:
            result = win32service.QueryServiceStatus(service)
            if not isinstance(result, tuple) or len(result) < 2:
                raise PermissionError("Unknown SCM quota writer state")
            return result[1]
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(scm)


def verify_offline_vm_recovery(*, expected_database: Path) -> bool:
    """Fail closed unless policy, NTFS ACL and actual SCM state all agree.

    Only use in a disposable VM with a previously installed LAB service.
    Never pass a user-controlled database path, registry name or service
    name. Windows admin/operator is responsible for stopping legacy agents
    and ensuring no third-party writer; this check is not a substitute.
    """
    if os.name != "nt":
        raise RuntimeError("Windows VM-only recovery")
    database, child_sid, models = read_hklm_writer_vm_config()
    if database != Path(expected_database).resolve(strict=True):
        raise PermissionError("Unexpected VM fixture during recovery")
    assert_protected_vm_ledger_acl(database, models, child_sid)
    state = query_registered_writer_state()
    return require_recovery_preconditions(
        expected_database=database,
        configured_database=database,
        registered_service_state=state,
        acl_is_protected=True,
    )

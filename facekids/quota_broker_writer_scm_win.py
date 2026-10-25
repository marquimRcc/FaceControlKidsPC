"""VM-ONLY, explicitly registered SCM quota writer, NEVER a family installer.

Protected machine registry -> SYSTEM process SID -> lab-marked SQLite ->
ACL verification -> OS WTS token -> SCM lock notifications -> in-process
FaceAuthenticator -> self-timed quota receipts.

The current Filhos agent still charges the old database and MUST NOT coexist
with a live writer on that database. This VM service refuses family paths,
requires a synthetic fixture marker and offers NO mutating child IPC.
Registration, camera/Winlogon activation and physical deployment are deliberately
not exposed by the app or installer.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Mapping

from .auth_service import FaceAuthenticator
from .quota_broker_scm_host import ServiceOwnedScmHost
from .quota_broker_scm_win import (
    _ServiceBase, _require_expected_service_sid, _sid_is_valid,
)
from .quota_broker_runtime import ServiceOwnedQuotaRuntime
from .quota_broker_wts_win import observe_console_from_system
from .storage import Storage

VM_WRITER_REGISTRY_PATH = r"SOFTWARE\FaceControlKidsPC\QuotaWriterVmLab"
VM_WRITER_SERVICE_NAME = "FaceKidsQuotaWriterVmOnly"
LAB_MARKER_KEY = "quota_writer_vm_fixture"
LAB_MARKER_VALUE = "synthetic-acceptance-v1"

try:
    if os.name != "nt":
        raise ImportError("SCM only")
    import servicemanager
    import win32service
except ImportError:
    servicemanager = None
    win32service = None


def validate_vm_writer_config(data: Mapping[str, object]) -> tuple[Path, str, Path]:
    """Pure config checks; no defaults, family paths, or child-controlled flags."""
    required = {"VmLabOnly", "WriterEnabled", "Database", "ChildSid", "Models", "ServiceSid"}
    if not isinstance(data, Mapping) or set(data) != required:
        raise ValueError("Exact protected SCM VM writer configuration required")
    if (type(data["VmLabOnly"]) is not int or data["VmLabOnly"] != 1 or
            type(data["WriterEnabled"]) is not int or data["WriterEnabled"] != 1):
        raise PermissionError("VM writer requires two explicit HKLM opt-ins")
    if data["ServiceSid"] != "S-1-5-18" or type(data["ServiceSid"]) is not str:
        raise PermissionError("VM writer requires LocalSystem process token")
    sid = data["ChildSid"]
    if not _sid_is_valid(sid) or sid in (
        "S-1-5-18", "S-1-5-19", "S-1-5-20", "S-1-1-0", "S-1-5-32-544"
    ):
        raise PermissionError("An independently obtained non-system child token SID is required")
    if type(data["Database"]) is not str or type(data["Models"]) is not str:
        raise ValueError("Invalid VM fixture paths")
    database = Path(data["Database"]).resolve(strict=True)
    models = Path(data["Models"]).resolve(strict=True)
    if not database.is_file() or not models.is_dir():
        raise ValueError("VM SQLite and model directory must exist")
    if database.name.casefold() != "writer-fixture.sqlite3":
        raise ValueError("Only the uniquely named VM writer fixture is accepted")
    lab_paths = [p for p in database.parents if p.name.casefold() == "facekids-quota-lab"]
    if len(lab_paths) != 1:
        raise ValueError("VM writer SQLite must live under facekids-quota-lab")
    root = lab_paths[0]
    if root not in models.parents:
        raise ValueError("Recognizer models must be inside the same VM lab")
    installed = (Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) /
                 "FaceKids").resolve(strict=False)
    if installed == database or installed in database.parents or installed in models.parents:
        raise PermissionError("Installed family paths are forbidden")
    if "facekids-quota-lab" not in [x.casefold() for x in database.parts]:
        raise ValueError("Missing isolated VM lab root")
    # Strictly synthetic data: an unrelated or copied family database has no
    # opt-in marker. This is checked read-only before any Storage is opened.
    try:
        # Connection context manager does NOT close its handle on exit.
        # Windows requires an explicit close for safe rollback and teardown.
        with closing(sqlite3.connect("file:" + database.as_posix() + "?mode=ro",
                                     uri=True)) as db:
            row = db.execute("SELECT value FROM settings WHERE key=?",
                             (LAB_MARKER_KEY,)).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Missing valid synthetic VM marker") from exc
    if row != (LAB_MARKER_VALUE,):
        raise PermissionError("Writer refused non-synthetic or unmarked SQLite")
    return database, sid, models


def read_hklm_writer_vm_config() -> tuple[Path, str, Path]:
    if os.name != "nt":
        raise RuntimeError("Windows SCM required")
    import winreg
    required_types = {
        "VmLabOnly": winreg.REG_DWORD,
        "WriterEnabled": winreg.REG_DWORD,
        "Database": winreg.REG_SZ,
        "ChildSid": winreg.REG_SZ,
        "Models": winreg.REG_SZ,
        "ServiceSid": winreg.REG_SZ,
    }
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VM_WRITER_REGISTRY_PATH,
                        0, winreg.KEY_READ) as key:
        values = {}
        for name, wanted_type in required_types.items():
            val, found_type = winreg.QueryValueEx(key, name)
            if found_type != wanted_type:
                raise ValueError("Unexpected VM HKLM writer registry value type")
            values[name] = val
    return validate_vm_writer_config(values)


def assert_protected_vm_ledger_acl(database: Path, models: Path, child_sid: str) -> None:
    """Reject broad writable NTFS ACLs on all authoritative lab files/dirs.

    Windows directory replacement is blocked by checking every level from
    the VM fixture root through the ledger/model files. This is conservative:
    a custom writer account/ACE requires a separate security review.
    """
    if os.name != "nt":
        raise RuntimeError("Windows ACL check required")
    import win32security

    protected_sids = {"S-1-5-18", "S-1-5-32-544"}
    write_mask = (
        0x00000002 | 0x00000004 | 0x00000010 | 0x00000040 |
        0x00000100 | 0x00010000 | 0x00040000 | 0x00080000 |
        0x10000000 | 0x40000000 | 0x80000000
    )
    lab_roots = [p for p in database.parents if p.name.casefold() == "facekids-quota-lab"]
    if len(lab_roots) != 1:
        raise PermissionError("Missing protected VM directory")
    lab = lab_roots[0]
    targets = {database, models, lab, database.parent, models.parent}
    # The model files themselves cannot be writable by children either:
    # replacing them would silently change the service's face provenance.
    targets.update(path for path in models.rglob("*") if path.is_file())
    # All parents up to lab's immediate parent must also refuse broad writes,
    # or an unprivileged account could replace the directory itself.
    targets.add(lab.parent)
    targets.update(p for p in database.parents if lab in p.parents)
    targets.update(p for p in models.parents if lab in p.parents)

    for path in targets:
        if not path.exists() or path.is_symlink():
            raise PermissionError("VM protected file/dir missing or symlink")
        descriptor = win32security.GetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION |
            win32security.OWNER_SECURITY_INFORMATION,
        )
        owner = win32security.ConvertSidToStringSid(descriptor.GetSecurityDescriptorOwner())
        if owner == child_sid:
            raise PermissionError("Child-owned writer data directory is forbidden")
        dacl = descriptor.GetSecurityDescriptorDacl()
        if dacl is None:
            raise PermissionError("NULL DACL permits unprivileged modification")
        for i in range(dacl.GetAceCount()):
            ace = dacl.GetAce(i)
            if ace[0][0] not in (
                win32security.ACCESS_ALLOWED_ACE_TYPE,
                getattr(win32security, "ACCESS_ALLOWED_OBJECT_ACE_TYPE", 5),
            ):
                continue
            mask = int(ace[1])
            account = win32security.ConvertSidToStringSid(ace[2])
            if account not in protected_sids and mask & write_mask:
                raise PermissionError("VM ledger has a writable ACE for non-service principals")


class FaceKidsQuotaWriterVmService(_ServiceBase):
    """SCM service entrypoint with actual service-generated SQLite ticks.

    Use ONLY after external VM snapshot and conventional Windows login recovery
    were verified. No program entrypoint in this module registers the service.
    """

    _svc_name_ = VM_WRITER_SERVICE_NAME
    _svc_display_name_ = "FaceKids Quota Writer (Disposable VM Lab Only)"
    _svc_description_ = "VM fixture ledger only; never attach to installed Filhos"

    def __init__(self, args):
        if _ServiceBase is object:
            raise RuntimeError("Install pywin32 in a disposable Windows VM first")
        super().__init__(args)
        self._stop_signal = threading.Event()
        self._host: ServiceOwnedScmHost | None = None

    def GetAcceptedControls(self):
        return super().GetAcceptedControls() | win32service.SERVICE_ACCEPT_SESSIONCHANGE

    def SvcOtherEx(self, control, event_type, data):
        if control != win32service.SERVICE_CONTROL_SESSIONCHANGE:
            return super().SvcOtherEx(control, event_type, data)
        host = getattr(self, "_host", None)
        if host is None:
            return  # Fail closed until runtime is initialized.
        try:
            host.on_scm_session_change(event_type, data)
        except (ValueError, TypeError):
            servicemanager.LogErrorMsg("FaceKids VM writer rejected invalid SCM session change")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_signal.set()
        host = getattr(self, "_host", None)
        if host is not None:
            host.request_stop()

    def SvcDoRun(self):
        store: Storage | None = None
        try:
            # No fixture paths or SQLite contents read before verifying SYSTEM.
            _require_expected_service_sid(registry_path=VM_WRITER_REGISTRY_PATH)
            db_path, child_sid, models = read_hklm_writer_vm_config()
            assert_protected_vm_ledger_acl(db_path, models, child_sid)
            if self._stop_signal.is_set():
                return
            store = Storage(db_path)
            auth = FaceAuthenticator(models, db_path)
            runtime = ServiceOwnedQuotaRuntime.from_service_authenticator(
                store, expected_windows_sid=child_sid,
                authenticator=auth,
                observe_wts=observe_console_from_system,
            )
            self._host = ServiceOwnedScmHost(runtime, stop_event=self._stop_signal)
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self._host.run()
        except Exception as exc:
            # No file names, SIDs or child identity in event log.
            if servicemanager is not None:
                servicemanager.LogErrorMsg(
                    "FaceKids VM quota writer stopped: " + type(exc).__name__
                )
            raise
        finally:
            if self._host is not None:
                self._host.request_stop()
            if store is not None:
                store.close()


if __name__ == "__main__":
    raise SystemExit(
        "VM-only quota writer is NOT an installer or family service. "
        "Registration is out-of-band after documented snapshot/recovery."
    )

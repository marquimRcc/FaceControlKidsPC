"""Optional pywin32 SCM wrapper for the disposable quota-broker LAB.

Importing this module does NOT install or start a service. The production
Filhos service, biometric login, tasks, and registry are not modified.

Manual SCM registration is intentionally excluded: an administrator must
first validate this in a disposable Windows VM and configure the protected
HKLM lab-only policy before creating a service with pywin32 tooling.
"""
from __future__ import annotations

from argparse import Namespace
import os
from pathlib import Path
import threading
from typing import Mapping

from .quota_broker_lab import validate_lab_options
from .quota_broker_supervisor import QuotaLabSupervisor

REGISTRY_PATH = r"SOFTWARE\FaceControlKidsPC\QuotaBrokerLabService"
SERVICE_NAME = "FaceKidsQuotaLabOnly"


def validate_service_registry_config(data: Mapping[str, object]) -> tuple[str, Path, dict[str, int]]:
    """Validate values read from a protected HKLM policy (never client IPC).

    No unsafe defaults and no side effects; suitable for offline testing.
    """
    if not isinstance(data, Mapping) or data.get("LabOnly") != 1 or data.get("LabOnly") is True:
        raise ValueError("Explicit LabOnly=1 registry opt-in required")
    if set(data) != {"LabOnly", "Database", "ClientSid", "ChildId", "PipeSuffix"}:
        raise ValueError("Unknown or missing SCM lab settings")
    if type(data["Database"]) is not str or type(data["ClientSid"]) is not str or type(data["PipeSuffix"]) is not str:
        raise ValueError("Invalid service lab setting type")
    if type(data["ChildId"]) is not int or data["ChildId"] <= 0:
        raise ValueError("Invalid enrolled child setting")
    args = Namespace(
        vm_lab_only=True,
        database=Path(data["Database"]),
        client_sid=data["ClientSid"],
        child_id=data["ChildId"],
        pipe_suffix=data["PipeSuffix"],
    )
    pipe_name, db, mapping = validate_lab_options(args)
    # The lab's SQLite file must not be nested under the installed FaceKids
    # ProgramData tree, including an attacker-created "facekids-quota-lab".
    programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")).resolve(strict=False)
    existing_install = (programdata / "FaceKids").resolve(strict=False)
    if existing_install == db or existing_install in db.parents:
        raise ValueError("Production FaceKids ProgramData directory is forbidden")
    return pipe_name, db, mapping


def read_hklm_lab_configuration() -> tuple[str, Path, dict[str, int]]:
    """Read machine-controlled lab config only; no env/CLI trust overrides."""
    if os.name != "nt":
        raise RuntimeError("Windows SCM only")
    import winreg

    expected_types = {
        "LabOnly": winreg.REG_DWORD,
        "Database": winreg.REG_SZ,
        "ClientSid": winreg.REG_SZ,
        "ChildId": winreg.REG_DWORD,
        "PipeSuffix": winreg.REG_SZ,
    }
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
        vals = {}
        for name, required_type in expected_types.items():
            value, actual_type = winreg.QueryValueEx(key, name)
            if actual_type != required_type:
                raise ValueError("Invalid HKLM lab registry value type")
            vals[name] = value
    return validate_service_registry_config(vals)


try:
    if os.name != "nt":
        raise ImportError("Windows-only SCM wrapper")
    import servicemanager
    import win32service
    import win32serviceutil
    _ServiceBase = win32serviceutil.ServiceFramework
except ImportError:
    _ServiceBase = object


class FaceKidsQuotaLabService(_ServiceBase):
    """Pywin32 service entrypoint, registration explicitly out-of-band."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "FaceKids Quota Read-Only Lab (VM Only)"
    _svc_description_ = "Disposable VM test host. Never enable on family PC."

    def __init__(self, args):
        if _ServiceBase is object:
            raise RuntimeError("Install optional pywin32 only in isolated Windows VM")
        super().__init__(args)
        self._stop_signal = threading.Event()
        self._supervisor: QuotaLabSupervisor | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_signal.set()
        if self._supervisor is not None:
            self._supervisor.request_stop()

    def SvcDoRun(self):
        try:
            pipe_name, data_path, mapping = read_hklm_lab_configuration()
            self._supervisor = QuotaLabSupervisor(
                pipe_name=pipe_name, data_path=data_path,
                enrolled_child_by_sid=mapping, stop_event=self._stop_signal,
            )
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self._supervisor.run()
        except Exception as exc:
            # Do not dump user-SID or data paths in event logs.
            servicemanager.LogErrorMsg(
                f"FaceKids quota lab stopped: {type(exc).__name__}"
            )
            raise


if __name__ == "__main__":
    raise SystemExit(
        "This module does not register Windows services. "
        "Use a disposable VM, protected HKLM lab config and explicit "
        "administrator-reviewed registration only."
    )

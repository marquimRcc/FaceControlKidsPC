"""CI-only REAL Windows SCM lifecycle probe on a disposable hosted runner.

This intentionally refuses desktops, family PCs, and self-hosted runners.
It registers a uniquely scoped LAB-ONLY, read-only Python service; creates
synthetic SQLite data; queries one balance; stops and removes the service.
Every created resource is rolled back in finally.
"""
from __future__ import annotations

from contextlib import closing
import ctypes
import os
from pathlib import Path
import shutil
import site
import sqlite3
import sys
import time
import uuid
import winreg

from facekids.quota_broker_client_win import query_lab_balance
from facekids.quota_broker_scm_win import (
    REGISTRY_PATH, SERVICE_NAME, FaceKidsQuotaLabService,
)
from facekids.storage import Storage


def _require_ephemeral_host() -> None:
    expected = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "GITHUB_REPOSITORY": "marquimRcc/FaceControlKidsPC",
    }
    if os.name != "nt" or any(os.environ.get(k) != v for k, v in expected.items()):
        raise RuntimeError("SCM lifecycle test is restricted to GitHub-hosted Windows runners")
    if not os.environ.get("RUNNER_TEMP") or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Disposable admin runner required")


def _query_state(service_name: str):
    import win32serviceutil
    try:
        return win32serviceutil.QueryServiceStatus(service_name)[1]
    except Exception:
        return None


def _await_state(service_name: str, expected: int, *, seconds: float = 25.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        observed = _query_state(service_name)
        if observed == expected:
            return
        time.sleep(0.25)
    raise TimeoutError(f"Synthetic SCM test did not reach state {expected}")


def _current_user_sid() -> str:
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return win32security.ConvertSidToStringSid(sid)
    finally:
        token.Close()


def _registry_exists(path: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ):
            return True
    except FileNotFoundError:
        return False


def main() -> int:
    _require_ephemeral_host()
    import pywintypes
    import win32service
    import win32serviceutil
    import winerror

    if _registry_exists(REGISTRY_PATH):
        raise RuntimeError("Refusing to overwrite pre-existing SCM lab HKLM policy")
    if _query_state(SERVICE_NAME) is not None:
        raise RuntimeError("Refusing to touch pre-existing service")

    root = Path(os.environ["RUNNER_TEMP"]) / "facekids-quota-lab"
    if root.exists():
        raise RuntimeError("Refusing to reuse an existing lab data directory")
    parent_key = r"SOFTWARE\FaceControlKidsPC"
    original_parent_exists = _registry_exists(parent_key)
    pth = None
    policy_created = False
    service_creation_attempted = False
    try:
        root.mkdir()
        db = root / "fixture.sqlite3"
        store = Storage(db)
        try:
            child_id = store.add_person("SCM synthetic child", 1)
        finally:
            store.close()
        suffix = uuid.uuid4().hex
        with winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH, 0, winreg.KEY_WRITE
        ) as key:
            policy_created = True
            winreg.SetValueEx(key, "LabOnly", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "Database", 0, winreg.REG_SZ, str(db))
            winreg.SetValueEx(key, "ClientSid", 0, winreg.REG_SZ, _current_user_sid())
            winreg.SetValueEx(key, "ChildId", 0, winreg.REG_DWORD, child_id)
            winreg.SetValueEx(key, "PipeSuffix", 0, winreg.REG_SZ, suffix)
            winreg.SetValueEx(key, "ServiceSid", 0, winreg.REG_SZ, "S-1-5-18")

        # PythonService.exe launches in a different directory. A temporary
        # .pth makes this checkout importable ONLY on the disposable runner.
        candidates = [Path(x) for x in site.getsitepackages() if Path(x).is_dir()]
        if not candidates:
            raise RuntimeError("No site-packages for SCM import fixture")
        pth = candidates[0] / ("_facekids_scm_ci_" + suffix + ".pth")
        pth.write_text(str(Path(__file__).resolve().parents[1]) + "\n", encoding="utf-8")

        # This process is GitHub-hosted and disposable. There is deliberately
        # no user-accessible service registration action in the FaceKids app.
        service_creation_attempted = True
        win32serviceutil.InstallService(
            "facekids.quota_broker_scm_win.FaceKidsQuotaLabService",
            SERVICE_NAME,
            FaceKidsQuotaLabService._svc_display_name_,
            startType=win32service.SERVICE_DEMAND_START,
            description=FaceKidsQuotaLabService._svc_description_,
        )
        win32serviceutil.StartService(SERVICE_NAME)
        _await_state(SERVICE_NAME, win32service.SERVICE_RUNNING)

        pipe = r"\\.\pipe\FaceKidsQuotaBrokerLab-" + suffix
        balance = query_lab_balance(pipe)
        if balance.get("status") != "OK" or balance.get("remaining_seconds") != 60:
            raise AssertionError("Real SCM lab service failed synthetic read-only query")
        with closing(sqlite3.connect(db)) as verify:
            if verify.execute("SELECT count(*) FROM daily_usage").fetchone()[0] != 0:
                raise AssertionError("SCM lab service must never debit a quota")

        win32serviceutil.StopService(SERVICE_NAME)
        _await_state(SERVICE_NAME, win32service.SERVICE_STOPPED)
        print("PASS: disposable SCM install/start/pipe/stop; quota remains unchanged")
        return 0
    finally:
        # Cleanup is mandatory even when install/start/pipe checks fail.
        cleanup_errors = []
        if service_creation_attempted and _query_state(SERVICE_NAME) is not None:
            try:
                import win32serviceutil
                import win32service
                if _query_state(SERVICE_NAME) != win32service.SERVICE_STOPPED:
                    win32serviceutil.StopService(SERVICE_NAME)
                    _await_state(SERVICE_NAME, win32service.SERVICE_STOPPED, seconds=15)
                win32serviceutil.RemoveService(SERVICE_NAME)
            except Exception as exc:
                cleanup_errors.append(f"Service: {type(exc).__name__}")
        if policy_created:
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH)
                if not original_parent_exists:
                    winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, parent_key)
            except Exception as exc:
                cleanup_errors.append(f"HKLM: {type(exc).__name__}")
        if pth is not None:
            try:
                pth.unlink(missing_ok=True)
            except Exception as exc:
                cleanup_errors.append(f"PythonPath: {type(exc).__name__}")
        if root.exists():
            try:
                shutil.rmtree(root)
            except Exception as exc:
                cleanup_errors.append(f"Fixture: {type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError("CI SCM cleanup failed: " + ", ".join(cleanup_errors))


if __name__ == "__main__":
    raise SystemExit(main())

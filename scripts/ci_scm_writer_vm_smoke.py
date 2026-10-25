"""Disposable GitHub-hosted Windows SCM test of the VM-only writer.

Registers a TEMPORARY SYSTEM service backed by three entirely fictional kids.
Verifies protected HKLM policy, NTFS ACL and real standard-user token; the
service MUST start without any WTS unlock event or camera, then MUST NOT debit.
Does not register Credential Provider, modify family account or reuse paths.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import secrets
import shutil
import site
import sqlite3
import subprocess
import uuid
import winreg

from facekids.quota_broker_writer_scm_win import (
    VM_WRITER_REGISTRY_PATH, VM_WRITER_SERVICE_NAME,
    LAB_MARKER_KEY, LAB_MARKER_VALUE, FaceKidsQuotaWriterVmService,
    assert_protected_vm_ledger_acl,
)
from facekids.storage import Storage
from facekids.quota_broker_bound_client_win import query_current_bound_vm_balance
from scripts.ci_scm_lab_smoke import (
    _await_state, _query_state, _registry_exists, _require_ephemeral_host,
)


def _protect(path: Path, *, directory: bool = False) -> None:
    inherit = "(OI)(CI)" if directory else ""
    subprocess.run(
        ["icacls.exe", str(path), "/inheritance:r", "/grant:r",
         "*S-1-5-18:" + inherit + "F",
         "*S-1-5-32-544:" + inherit + "F"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )


def main() -> int:
    _require_ephemeral_host()
    import win32con
    import win32net
    import win32netcon
    import win32security
    import win32service
    import win32serviceutil

    if _registry_exists(VM_WRITER_REGISTRY_PATH):
        raise RuntimeError("Refusing pre-existing VM writer HKLM configuration")
    if _query_state(VM_WRITER_SERVICE_NAME) is not None:
        raise RuntimeError("Refusing pre-existing VM writer service")

    root_parent = Path(os.environ["RUNNER_TEMP"]) / ("fk-vm-writer-" + uuid.uuid4().hex)
    if root_parent.exists():
        raise RuntimeError("Refusing to reuse a VM writer fixture")
    lab_root = root_parent / "facekids-quota-lab"
    username = "FKWR" + uuid.uuid4().hex[:11]
    password = "A9!" + secrets.token_urlsafe(25)
    user_created = False
    policy_created = False
    service_attempted = False
    impersonating = False
    token = None
    pth = None
    parent_registry = r"SOFTWARE\FaceControlKidsPC"
    parent_registry_existed = _registry_exists(parent_registry)
    try:
        win32net.NetUserAdd(None, 1, {
            "name": username, "password": password,
            "priv": win32netcon.USER_PRIV_USER,
            "flags": win32netcon.UF_SCRIPT | win32netcon.UF_NORMAL_ACCOUNT,
        })
        user_created = True
        child_sid = win32security.ConvertSidToStringSid(
            win32security.LookupAccountName(None, username)[0]
        )

        lab_root.mkdir(parents=True)
        models = lab_root / "protected-models"
        models.mkdir()
        # No actual face vector/model or family photo. These test fixtures
        # MUST NOT cause a facial ALLOW in Session 0.
        sample_model = models / "dummy-not-an-onnx-model.bin"
        sample_model.write_bytes(b"synthetic-only")
        database = lab_root / "writer-fixture.sqlite3"
        store = Storage(database)
        try:
            for i in range(1, 4):
                store.add_person("Synthetic SCM " + str(i), 2)
            store.set_setting(LAB_MARKER_KEY, LAB_MARKER_VALUE)
        finally:
            store.close()

        for path in (root_parent, lab_root, models):
            _protect(path, directory=True)
        for path in (database, sample_model):
            _protect(path)
        assert_protected_vm_ledger_acl(database, models, child_sid)

        # Negative security audit before service installation: an accidental
        # child-WRITE ACE on either the ledger or a model MUST block startup.
        for asset in (database, sample_model):
            subprocess.run(
                ["icacls.exe", str(asset), "/grant", "*" + child_sid + ":W"],
                check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
            )
            try:
                try:
                    assert_protected_vm_ledger_acl(database, models, child_sid)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Writer ACL gate accepted child-write ACE")
            finally:
                subprocess.run(
                    ["icacls.exe", str(asset), "/remove:g", "*" + child_sid],
                    check=True, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, text=True,
                )
            assert_protected_vm_ledger_acl(database, models, child_sid)

        with winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE, VM_WRITER_REGISTRY_PATH,
            0, winreg.KEY_WRITE,
        ) as key:
            policy_created = True
            for name, value, kind in (
                ("VmLabOnly", 1, winreg.REG_DWORD),
                ("WriterEnabled", 1, winreg.REG_DWORD),
                ("Database", str(database), winreg.REG_SZ),
                ("Models", str(models), winreg.REG_SZ),
                ("ChildSid", child_sid, winreg.REG_SZ),
                ("ServiceSid", "S-1-5-18", winreg.REG_SZ),
            ):
                winreg.SetValueEx(key, name, 0, kind, value)

        candidates = [Path(p) for p in site.getsitepackages() if Path(p).is_dir()]
        if not candidates:
            raise RuntimeError("SCM import path unavailable")
        pth = candidates[0] / ("_facekids_writer_ci_" + uuid.uuid4().hex + ".pth")
        pth.write_text(str(Path(__file__).resolve().parents[1]) + "\n", encoding="utf-8")

        service_attempted = True
        win32serviceutil.InstallService(
            "facekids.quota_broker_writer_scm_win.FaceKidsQuotaWriterVmService",
            VM_WRITER_SERVICE_NAME,
            FaceKidsQuotaWriterVmService._svc_display_name_,
            startType=win32service.SERVICE_DEMAND_START,
            description=FaceKidsQuotaWriterVmService._svc_description_,
        )
        win32serviceutil.StartService(VM_WRITER_SERVICE_NAME)
        _await_state(VM_WRITER_SERVICE_NAME, win32service.SERVICE_RUNNING)

        # A real child token cannot read/replace the VM-owned ledger or
        # models, or mutate SCM policy. There is no write IPC to attack.
        token = win32security.LogonUser(
            username, ".", password, win32con.LOGON32_LOGON_INTERACTIVE,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
        win32security.ImpersonateLoggedOnUser(token)
        impersonating = True
        try:
            for path in (database, sample_model):
                for mode in ("rb", "ab"):
                    try:
                        with path.open(mode) as handle:
                            if mode == "rb":
                                handle.read(1)
                            else:
                                handle.write(b"spoof")
                    except (OSError, PermissionError):
                        pass
                    else:
                        raise AssertionError("Child token read/modified protected VM writer assets")
            try:
                (models / "spoofed.onnx").write_bytes(b"spoof")
            except (OSError, PermissionError):
                pass
            else:
                raise AssertionError("Child token replaced protected face models")
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, VM_WRITER_REGISTRY_PATH,
                    0, winreg.KEY_SET_VALUE,
                ):
                    raise AssertionError("Child token may update trusted SCM policy")
            except PermissionError:
                pass

            # The child Windows token may query the real SCM writer's bound
            # pipe but cannot choose a child or fabricate a valid face lease.
            # This distinguishes a real DENY from an unavailable pipe.
            observed = query_current_bound_vm_balance()
            if observed is not None:
                raise AssertionError("SCM published quota without face binding")
        finally:
            win32security.RevertToSelf()
            impersonating = False

        # The administrative token must also be refused by the bound
        # endpoint even though it can inspect services for diagnosis.
        admin_observation = query_current_bound_vm_balance()
        if admin_observation is not None:
            raise AssertionError("SCM bound quota leaked to admin principal")

        # No WTS_SESSION_UNLOCK was dispatched and no face embeddings
        # exist. An actual SCM worker must not invent such evidence.
        with closing(sqlite3.connect(database)) as audit:
            receipts_exist = audit.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quota_tick_receipts'"
            ).fetchone() is not None
            count = (audit.execute(
                "SELECT COUNT(*) FROM quota_tick_receipts").fetchone()[0]
                if receipts_exist else 0)
            charges = audit.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
            children = audit.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        if (count, charges, children) != (0, 0, 3):
            raise AssertionError("VM writer charged without a trusted face/unlock event")

        win32serviceutil.StopService(VM_WRITER_SERVICE_NAME)
        _await_state(VM_WRITER_SERVICE_NAME, win32service.SERVICE_STOPPED)
        print("PASS: real SCM SYSTEM quota writer started/stopped in ephemeral VM, "
              "child ACL+HKLM denied, bound Named Pipe denies unknown faces, "
              "3 profiles and 0 unauthorized debits")
        return 0
    finally:
        problems = []
        if impersonating:
            try:
                win32security.RevertToSelf()
            except Exception as exc:
                problems.append("Revert:" + type(exc).__name__)
        if token is not None:
            try:
                token.Close()
            except Exception as exc:
                problems.append("Token:" + type(exc).__name__)
        if service_attempted and _query_state(VM_WRITER_SERVICE_NAME) is not None:
            try:
                if _query_state(VM_WRITER_SERVICE_NAME) != win32service.SERVICE_STOPPED:
                    win32serviceutil.StopService(VM_WRITER_SERVICE_NAME)
                    _await_state(VM_WRITER_SERVICE_NAME, win32service.SERVICE_STOPPED,
                                 seconds=15)
                win32serviceutil.RemoveService(VM_WRITER_SERVICE_NAME)
            except Exception as exc:
                problems.append("SCM:" + type(exc).__name__)
        if policy_created:
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, VM_WRITER_REGISTRY_PATH)
                if not parent_registry_existed:
                    winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, parent_registry)
            except Exception as exc:
                problems.append("HKLM:" + type(exc).__name__)
        if pth is not None:
            try:
                pth.unlink(missing_ok=True)
            except Exception as exc:
                problems.append("ImportPath:" + type(exc).__name__)
        if root_parent.exists():
            try:
                shutil.rmtree(root_parent)
            except Exception as exc:
                problems.append("Fixture:" + type(exc).__name__)
        if user_created:
            try:
                win32net.NetUserDel(None, username)
            except Exception as exc:
                problems.append("TestUser:" + type(exc).__name__)
        if problems:
            raise RuntimeError("Disposable writer cleanup failed: " + ", ".join(problems))


if __name__ == "__main__":
    raise SystemExit(main())

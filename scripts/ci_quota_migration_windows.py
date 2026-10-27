"""Windows-hosted CI: REAL child-token ACL + staged SQLite migration + rollback.

This is intentionally restricted to GitHub-hosted disposable Windows and
uses a RANDOM local synthetic standard account. It never touches Filhos,
Windows logon, Credential Provider, family files or production registry.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import subprocess
import uuid

from facekids.quota_migration_lab import prepare_lab_cutover, restore_lab_snapshot
from facekids.storage import Storage
from scripts.ci_scm_lab_smoke import _require_ephemeral_host
from scripts.ci_acl_child_token_smoke import _restrict


def _service_owned_acl(path: Path, *, directory: bool) -> None:
    inheritance = "(OI)(CI)" if directory else ""
    subprocess.run([
        "icacls.exe", str(path), "/inheritance:r", "/grant:r",
        "*S-1-5-18:" + inheritance + "F",
        "*S-1-5-32-544:" + inheritance + "F",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def main() -> int:
    _require_ephemeral_host()
    import win32con
    import win32net
    import win32netcon
    import win32security

    username = "FKCUT" + uuid.uuid4().hex[:11]
    password = "A9!" + secrets.token_urlsafe(24)
    root = Path(os.environ["RUNNER_TEMP"]) / uuid.uuid4().hex / "facekids-quota-lab"
    if root.exists():
        raise RuntimeError("Existing lab root refused")
    user_created = False
    impersonating = False
    token = None
    try:
        win32net.NetUserAdd(None, 1, {
            "name": username, "password": password,
            "priv": win32netcon.USER_PRIV_USER,
            "flags": win32netcon.UF_SCRIPT | win32netcon.UF_NORMAL_ACCOUNT,
        })
        user_created = True
        old = root / "legacy"
        protected = root / "protected-ledger"
        snapshots = root / "admin-backups"
        cache = root / "child-cache"
        for p in (old, protected, snapshots, cache):
            p.mkdir(parents=True)
        old_db = old / "criancas.sqlite3"
        new_db = protected / "criancas.sqlite3"
        backup = snapshots / "before-cutover.sqlite3"
        store = Storage(old_db)
        try:
            child_ids = [store.add_person(f"Synthetic child {i}", 2) for i in range(3)]
            for i, child in enumerate(child_ids):
                store.charge(child, (i + 1) * 5, "2026-10-24")
        finally:
            store.close()

        # A child can modify the OLD legacy data path; the new service-owned
        # directory refuses all accesses (including reading facial data).
        _restrict(root, username, "RX", directory=True)
        _restrict(old, username, "M", directory=True)
        _restrict(cache, username, "M", directory=True)
        _service_owned_acl(protected, directory=True)
        _service_owned_acl(snapshots, directory=True)

        prepare_lab_cutover(root, old_db, new_db, backup)
        if not new_db.exists() or not backup.exists():
            raise AssertionError("Synthetic quota cutover not materialized")

        token = win32security.LogonUser(
            username, ".", password,
            win32con.LOGON32_LOGON_INTERACTIVE,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
        win32security.ImpersonateLoggedOnUser(token)
        impersonating = True
        try:
            for target in (new_db, backup):
                for mode in ("rb", "ab"):
                    try:
                        with target.open(mode) as fh:
                            if mode == "rb":
                                fh.read(1)
                            else:
                                fh.write(b"malicious")
                    except (PermissionError, OSError):
                        pass
                    else:
                        raise AssertionError("Child token accessed service-owned ledger/snapshot")
            try:
                (protected / "child-replacement.sqlite3").write_bytes(b"fake")
            except (PermissionError, OSError):
                pass
            else:
                raise AssertionError("Child token replaced service-owned ledger")
            (cache / "non-authoritative.txt").write_text("child cache permitted", encoding="utf-8")
            if not old_db.exists():
                raise AssertionError("Source fixture vanished unexpectedly")
        finally:
            win32security.RevertToSelf()
            impersonating = False

        # Simulate an authorized service debit, then restore exact original
        # ledger balances through the admin-only snapshot.
        store = Storage(new_db)
        try:
            store.charge(child_ids[0], 11, "2026-10-24")
            if store.used(child_ids[0], "2026-10-24") != 16:
                raise AssertionError("Service-owned debit failed")
        finally:
            store.close()
        restore_lab_snapshot(root, new_db, backup)
        store = Storage(new_db)
        try:
            amounts = [store.used(pid, "2026-10-24") for pid in child_ids]
        finally:
            store.close()
        if amounts != [5, 10, 15]:
            raise AssertionError("Rollback did not restore three independent balances")
        print("PASS: disposable Windows child token denied protected SQLite read/write; WAL-safe rollback preserved 3 profiles")
        return 0
    finally:
        if impersonating:
            try:
                win32security.RevertToSelf()
            except Exception:
                pass
        if token is not None:
            token.Close()
        issues = []
        if root.parent.exists():
            try:
                shutil.rmtree(root.parent)
            except Exception as exc:
                issues.append("lab-files:" + type(exc).__name__)
        if user_created:
            try:
                win32net.NetUserDel(None, username)
            except Exception as exc:
                issues.append("lab-account:" + type(exc).__name__)
        if issues:
            raise RuntimeError("Disposable migration cleanup failed: " + ", ".join(issues))


if __name__ == "__main__":
    raise SystemExit(main())

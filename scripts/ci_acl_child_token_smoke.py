"""Verify ACTUAL unprivileged Windows token ACLs in a hosted disposable VM.

Creates a random synthetic LOCAL standard user and lab fixture under its
own ProgramData directory. Never uses the household Filhos account, photos,
real SQLite, or Credential Provider, and removes the test user and files.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import subprocess
import uuid

from scripts.ci_scm_lab_smoke import _require_ephemeral_host


def _restrict(path: Path, username: str, rights: str, *, directory: bool):
    inherit = "(OI)(CI)" if directory else ""
    ace = [
        "*S-1-5-18:" + inherit + "F",       # LocalSystem
        "*S-1-5-32-544:" + inherit + "F",  # Administrators
        username + ":" + inherit + rights,
    ]
    subprocess.run(
        ["icacls.exe", str(path), "/inheritance:r", "/grant:r", *ace],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    _require_ephemeral_host()
    import win32con
    import win32net
    import win32netcon
    import win32security

    name = "FKCI" + uuid.uuid4().hex[:12]
    password = "A9!" + secrets.token_urlsafe(25)
    root = Path(os.environ["PROGRAMDATA"]) / ("FaceKidsAclCi" + uuid.uuid4().hex)
    if root.exists():
        raise RuntimeError("Never reuse a lab ACL fixture")
    created_user = False
    token = None
    impersonating = False
    try:
        win32net.NetUserAdd(None, 1, {
            "name": name, "password": password,
            "priv": win32netcon.USER_PRIV_USER,
            "flags": win32netcon.UF_SCRIPT | win32netcon.UF_NORMAL_ACCOUNT,
        })
        created_user = True
        root.mkdir()
        protected = root / "protected"
        mutable = root / "child-cache"
        protected.mkdir()
        mutable.mkdir()
        fake_dll = protected / "FaceKidsCredentialProvider.synthetic"
        fake_sqlite = protected / "quota-ledger.synthetic"
        cache = mutable / "cache.synthetic"
        fake_dll.write_bytes(b"fake binary - not registered")
        fake_sqlite.write_bytes(b"synthetic ledger")
        cache.write_bytes(b"cache")

        # Explicit DACLs on ALL tested objects, not merely textual ACL checks.
        _restrict(root, name, "RX", directory=True)
        _restrict(protected, name, "RX", directory=True)
        _restrict(mutable, name, "M", directory=True)
        _restrict(fake_dll, name, "R", directory=False)
        _restrict(fake_sqlite, name, "R", directory=False)
        _restrict(cache, name, "M", directory=False)

        token = win32security.LogonUser(
            name, ".", password,
            win32con.LOGON32_LOGON_INTERACTIVE,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
        win32security.ImpersonateLoggedOnUser(token)
        impersonating = True
        try:
            for target in (fake_dll, fake_sqlite):
                if not target.read_bytes():
                    raise AssertionError("Child could not read lab protected fixture")
                try:
                    with target.open("ab") as file:
                        file.write(b"UNAUTHORIZED")
                except (PermissionError, OSError):
                    pass
                else:
                    raise AssertionError("Unprivileged child modified protected fixture")

            with cache.open("ab") as file:
                file.write(b"-child-write-ok")
            if not cache.read_bytes().endswith(b"-child-write-ok"):
                raise AssertionError("Child could not write isolated cache")
        finally:
            win32security.RevertToSelf()
            impersonating = False

        if (fake_dll.read_bytes() != b"fake binary - not registered" or
                fake_sqlite.read_bytes() != b"synthetic ledger"):
            raise AssertionError("Protected lab data changed")
        print("PASS: real child token denied protected writes and permitted isolated cache")
        return 0
    finally:
        if impersonating:
            try:
                win32security.RevertToSelf()
            except Exception:
                pass
        if token is not None:
            token.Close()
        cleanup_errors = []
        if root.exists():
            try:
                shutil.rmtree(root)
            except Exception as exc:
                cleanup_errors.append("fixture:" + type(exc).__name__)
        if created_user:
            try:
                win32net.NetUserDel(None, name)
            except Exception as exc:
                cleanup_errors.append("temporary-user:" + type(exc).__name__)
        if cleanup_errors:
            raise RuntimeError("Ephemeral child-token cleanup failed: " +
                               ", ".join(cleanup_errors))


if __name__ == "__main__":
    raise SystemExit(main())

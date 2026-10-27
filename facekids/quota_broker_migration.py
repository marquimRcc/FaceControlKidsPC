"""Consistent SQLite snapshot for an OFFLINE VM migration rehearsal.

Does not grant/revoke Windows ACLs or move the live ledger. The caller must
stop legacy writers before any eventual cutover and separately validate NTFS
permissions and restoration in a disposable VM.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import sqlite3


@dataclass(frozen=True)
class SnapshotResult:
    output: Path
    sha256: str
    children: int
    ledger_rows: int


def create_vm_snapshot(source: Path, target: Path, *, lab_root: Path) -> SnapshotResult:
    """Make a consistent WAL-aware SQLite backup, restricted to lab_root.

    Requires a source DB and a NEW destination file inside the lab directory.
    The source is read-only; target is not a Windows access-control boundary.
    """
    root = Path(lab_root).resolve(strict=True)
    src = Path(source).resolve(strict=True)
    dst = Path(target).resolve(strict=False)
    if (not root.is_dir() or not src.is_file() or not dst.parent.is_dir() or
            src == dst or not src.is_relative_to(root) or
            not dst.is_relative_to(root) or dst.exists()):
        raise ValueError("Snapshot permitted only for new files inside the lab root")

    # Refuse symlink destinations and verified source paths outside the lab.
    # sqlite URI mode=ro prevents accidental mutation of source.
    conn_src = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        if conn_src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Source database failed integrity_check")
        children = int(conn_src.execute("SELECT count(*) FROM people").fetchone()[0])
        usage_rows = int(conn_src.execute("SELECT count(*) FROM daily_usage").fetchone()[0])
        # Temporary file on the same filesystem, then an atomic publish. Never
        # silently overwrite an existing target or an existing temp file.
        temp = dst.with_name(dst.name + ".facekids-incomplete")
        if temp.exists():
            raise ValueError("Previous incomplete snapshot must be investigated")
        try:
            conn_dst = sqlite3.connect(str(temp), timeout=10)
            try:
                conn_src.backup(conn_dst)
                if conn_dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Snapshot integrity failed")
                if int(conn_dst.execute("SELECT count(*) FROM people").fetchone()[0]) != children:
                    raise ValueError("Snapshot people count mismatch")
                if int(conn_dst.execute("SELECT count(*) FROM daily_usage").fetchone()[0]) != usage_rows:
                    raise ValueError("Snapshot usage count mismatch")
            finally:
                conn_dst.close()
            if os.name != "nt":
                temp.chmod(0o600)
            # Only a single rehearsal process may publish into this directory.
            # Do not use this as a race-safe installer on production files.
            if dst.exists():
                raise ValueError("Destination appeared while snapshot was running")
            temp.rename(dst)
        finally:
            temp.unlink(missing_ok=True)
    finally:
        conn_src.close()
    return SnapshotResult(
        output=dst,
        sha256=hashlib.sha256(dst.read_bytes()).hexdigest(),
        children=children,
        ledger_rows=usage_rows,
    )

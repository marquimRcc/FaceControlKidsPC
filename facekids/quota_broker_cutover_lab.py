"""OFFLINE cutover and rollback rehearsal for synthetic SQLite VM fixtures.

Never use with active writers, family biometrics, COM, Winlogon or the
real ProgramData ledger. No privileged Windows changes are performed.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import uuid

from .quota_broker_migration import create_vm_snapshot


@dataclass(frozen=True)
class LabCutoverReceipt:
    original_sha256: str
    restored_sha256: str
    backup: Path
    profiles: int
    quota_rows: int
    preview_verified: bool


def rehearse_offline_cutover(
    source: Path, *, lab_root: Path, inject_failure: bool = False,
) -> LabCutoverReceipt:
    """Preview replacement then restore the ORIGINAL bytes in a lab root.

    Source must be a CLOSED SQLite fixture directly inside a directory
    literally named 'facekids-quota-lab'. WAL/SHM presence is a hard failure.
    Backup is retained; preview and staging files are deleted.
    """
    requested_root = Path(lab_root)
    if requested_root.is_symlink():
        raise ValueError("Symlink lab roots are not permitted")
    root = requested_root.resolve(strict=True)
    candidate = Path(source)
    src = candidate.resolve(strict=True)
    if (root.name.casefold() != "facekids-quota-lab"
            or not root.is_dir()
            or candidate.is_symlink() or src.parent != root or not src.is_file()):
        raise ValueError("Cutover rehearsal requires a direct lab-only SQLite fixture")
    production = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")).resolve(strict=False) / "FaceKids"
    if root == production or production in root.parents:
        raise ValueError("Production FaceKids directory is forbidden")
    if (Path(str(src) + "-wal").exists() or Path(str(src) + "-shm").exists()):
        raise ValueError("Offline cutover requires closed, checkpointed SQLite")
    if type(inject_failure) is not bool:
        raise ValueError("Invalid simulated fault flag")

    original_digest = hashlib.sha256(src.read_bytes()).hexdigest()
    tag = uuid.uuid4().hex
    backup = root / (".facekids-backup-" + tag + ".sqlite3")
    stage = root / (".facekids-stage-" + tag + ".sqlite3")
    held = root / (".facekids-held-" + tag + ".sqlite3")
    retired = root / (".facekids-retired-" + tag + ".sqlite3")

    snapshot = create_vm_snapshot(src, backup, lab_root=root)
    preview = create_vm_snapshot(snapshot.output, stage, lab_root=root)
    if not preview.sha256 or preview.children != snapshot.children:
        raise ValueError("Offline preview verification failed")

    moved_original = False
    moved_preview = False
    verified = False
    try:
        src.rename(held)
        moved_original = True
        stage.rename(src)
        moved_preview = True
        with closing(sqlite3.connect(src.as_uri() + "?mode=ro", uri=True)) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Lab preview corruption")
            if check.execute("SELECT count(*) FROM people").fetchone()[0] != snapshot.children:
                raise RuntimeError("Lab preview person count mismatch")
            if check.execute("SELECT count(*) FROM daily_usage").fetchone()[0] != snapshot.ledger_rows:
                raise RuntimeError("Lab preview usage mismatch")
        verified = True
        if inject_failure:
            raise RuntimeError("Synthetic failure after preview cutover")
    finally:
        if moved_original:
            if moved_preview and src.exists():
                src.rename(retired)
            held.rename(src)
        stage.unlink(missing_ok=True)
        retired.unlink(missing_ok=True)

    restored_digest = hashlib.sha256(src.read_bytes()).hexdigest()
    if restored_digest != original_digest:
        raise RuntimeError("Original SQLite bytes were not restored")
    return LabCutoverReceipt(
        original_sha256=original_digest,
        restored_sha256=restored_digest,
        backup=backup,
        profiles=snapshot.children,
        quota_rows=snapshot.ledger_rows,
        preview_verified=verified,
    )

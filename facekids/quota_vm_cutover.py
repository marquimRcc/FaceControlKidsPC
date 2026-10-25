"""Disposable VM-only quota ownership cutover with WAL-safe undo.

Never install this on family Windows. Call only in an isolated fixture named
facekids-quota-lab/writer-fixture.sqlite3, with a synthetic DB marker and an
explicit offline service gate. SQL ownership mode complements NTFS; a writable
SQLite file cannot authenticate its caller.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Callable, Mapping

from .quota_broker_migration import SnapshotResult, create_vm_snapshot
from .quota_broker_writer_scm_win import validate_vm_writer_config

OWNER_KEY = "quota_writer_owner"
SERVICE_ONLY = "vm-service-only"


@dataclass(frozen=True)
class VmCutover:
    original: Path
    original_snapshot: SnapshotResult
    owner: str


def _require_offline(offlined: Callable[[], bool]) -> None:
    if not callable(offlined) or offlined() is not True:
        raise PermissionError("SCM writer and legacy writer must both be stopped")


def _validate_paths(
    config: Mapping[str, object], path: Path, *, must_exist: bool = True
) -> tuple[Path, Path]:
    database, _sid, _models = validate_vm_writer_config(config)
    root = next(p for p in database.parents if p.name.casefold() == "facekids-quota-lab")
    item = Path(path).resolve(strict=must_exist)
    if (item == database or not item.is_relative_to(root) or
            item.parent != root or item.is_symlink()):
        raise ValueError("VM recovery file must be distinct and inside lab root")
    return database, item


def promote_vm_lab_writer(
    config: Mapping[str, object], *, backup_path: Path,
    offline_gate: Callable[[], bool],
) -> VmCutover:
    """Snapshot BEFORE switching to service-only billing, no family paths."""
    _require_offline(offline_gate)
    database, backup = _validate_paths(config, backup_path, must_exist=False)
    root = backup.parent
    # Existing backup would make rollback identity ambiguous.
    if backup.exists():
        raise FileExistsError("Refusing to overwrite a previous cutover backup")
    with closing(sqlite3.connect(database)) as db:
        current = db.execute(
            "SELECT value FROM settings WHERE key=?", (OWNER_KEY,)
        ).fetchone()
        if current is not None:
            raise PermissionError("Cutover is not repeatable without verified restore")
    snapshot = create_vm_snapshot(database, backup, lab_root=root)
    try:
        _require_offline(offline_gate)
        with closing(sqlite3.connect(database, timeout=3)) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT value FROM settings WHERE key=?", (OWNER_KEY,)
                ).fetchone()
                if row is not None:
                    raise PermissionError("A writer changed ownership during cutover")
                # Recheck the ledger after WAL snapshot to avoid promoting a
                # database that changed since the rollback image was created.
                with closing(sqlite3.connect(
                    backup.as_uri() + "?mode=ro", uri=True
                )) as copy:
                    for table in ("people", "daily_usage", "daily_bonus", "embeddings"):
                        live = db.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        snap = copy.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        if live != snap:
                            raise RuntimeError("Fixture changed after backup")
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Cutover ledger not intact")
                db.execute(
                    "INSERT INTO settings(key,value) VALUES (?,?)",
                    (OWNER_KEY, SERVICE_ONLY),
                )
    except Exception:
        # Leave the backup available for forensic recovery. No implicit
        # rollback because a running writer may still own the path.
        raise
    return VmCutover(database, snapshot, SERVICE_ONLY)


def restore_vm_lab_offline(
    config: Mapping[str, object], *, backup_path: Path,
    preserved_current_path: Path, offline_gate: Callable[[], bool],
) -> Path:
    """Restore a verified cutover snapshot with a separate pre-restore image.

    Requires both writers stopped and snapshot validated. No family path,
    no service registration, no forced deletion of active WAL files. Returns
    the immutable pre-restore image for roll-forward inspection.
    """
    _require_offline(offline_gate)
    database, backup = _validate_paths(config, backup_path)
    original, preserved = _validate_paths(config, preserved_current_path, must_exist=False)
    if original != database or backup == preserved or preserved.exists():
        raise ValueError("Recovery targets overlap or were already used")
    with closing(sqlite3.connect(
        backup.as_uri() + "?mode=ro", uri=True
    )) as original_snapshot:
        if original_snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid rollback snapshot")
        if original_snapshot.execute(
            "SELECT value FROM settings WHERE key=?", (OWNER_KEY,)
        ).fetchone() is not None:
            raise ValueError("Rollback snapshot was already service-owned")

    root = database.parent
    recovery = create_vm_snapshot(
        database, preserved, lab_root=root
    )
    prepared = database.with_name("writer-restore-prepared.sqlite3")
    if prepared.exists():
        raise FileExistsError("Incomplete restore; operator inspection required")
    try:
        create_vm_snapshot(backup, prepared, lab_root=root)
        _require_offline(offline_gate)
        with closing(sqlite3.connect(database, timeout=1)) as live:
            # Begin exclusive transaction and checkpoint all WAL frames; do
            # not restore while a writer owns the old database.
            live.execute("PRAGMA busy_timeout=1000")
            checkpoint = live.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or checkpoint[0] != 0:
                raise RuntimeError("Active WAL readers prevent offline restore")
        if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm")):
            raise RuntimeError("Active WAL/SHM files prevent safe replacement")
        # Same-volume single-file replace, preserving pre-restore backup.
        os.replace(prepared, database)
        with closing(sqlite3.connect(
            database.as_uri() + "?mode=ro", uri=True
        )) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Restored SQLite failed integrity check")
        return recovery.output
    finally:
        # Never touch the protected source or the forensic pre-restore image.
        prepared.unlink(missing_ok=True)

"""Reversible SQLite copy-and-cutover for a SYNTHETIC broker laboratory.

Never used by the family installer. Root and every source/target path must
reside inside a dedicated facekids-quota-lab directory (symlink-free).
The legacy writer must be stopped before any real migration. Protect target
directory with NTFS DACLs before calling these helpers in a VM.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile


def _ensure_lab(root: Path, *paths: Path) -> Path:
    root = Path(os.path.abspath(root))
    if "facekids-quota-lab" not in [p.casefold() for p in root.parts]:
        raise ValueError("Refusing database migration outside named lab root")
    for path in (root, *paths):
        path = Path(os.path.abspath(path))
        if path != root and root not in path.parents:
            raise ValueError("Migration path escapes lab directory")
        node = path
        while node != node.parent:
            if node.is_symlink():
                raise ValueError("Symlink migration path refused")
            if node == root:
                break
            node = node.parent
    return root


def _snapshot(src: Path, dst: Path) -> None:
    """Backup API captures committed WAL pages; close both handles on Windows."""
    with closing(sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)) as old:
        with closing(sqlite3.connect(dst)) as new:
            old.backup(new)
            check = new.execute("PRAGMA quick_check").fetchone()
            if check != ("ok",):
                raise RuntimeError("Corrupt SQLite snapshot")


def prepare_lab_cutover(
    root: Path, source: Path, destination: Path, snapshot: Path,
    *, inject_failure: bool = False,
) -> None:
    root = _ensure_lab(root, source, destination, snapshot)
    source, destination, snapshot = map(
        lambda p: Path(os.path.abspath(p)), (source, destination, snapshot)
    )
    if len({source, destination, snapshot}) != 3:
        raise ValueError("Source, cutover and snapshot must be separate paths")
    if not source.is_file() or destination.exists() or snapshot.exists():
        raise ValueError("Refusing absent source or existing cutover target")
    if not destination.parent.is_dir() or not snapshot.parent.is_dir():
        raise ValueError("Cutover directories must already exist")
    fd, staging = tempfile.mkstemp(prefix="fk-staged-", suffix=".sqlite3",
                                    dir=destination.parent)
    os.close(fd)
    staged = Path(staging)
    try:
        # Never remove or modify the legacy source. The snapshot survives a
        # deliberately injected cutover failure for manual recovery.
        _snapshot(source, snapshot)
        _snapshot(snapshot, staged)
        if inject_failure:
            raise RuntimeError("Injected cutover failure before atomic promotion")
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


def restore_lab_snapshot(root: Path, destination: Path, snapshot: Path) -> None:
    _ensure_lab(root, destination, snapshot)
    destination, snapshot = map(
        lambda p: Path(os.path.abspath(p)), (destination, snapshot)
    )
    if not snapshot.is_file() or not destination.parent.is_dir():
        raise ValueError("Missing rollback snapshot or protected directory")
    fd, staging = tempfile.mkstemp(prefix="fk-rollback-", suffix=".sqlite3",
                                    dir=destination.parent)
    os.close(fd)
    staged = Path(staging)
    try:
        _snapshot(snapshot, staged)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)

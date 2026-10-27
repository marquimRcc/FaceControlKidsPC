"""Explicit opt-in path isolation for the disposable Windows VM launcher.

Not an authentication boundary. It prevents the parent GUI/legacy pilot from
silently selecting installed ProgramData data when running in VM mode.
"""
from __future__ import annotations

import os
from pathlib import Path


def vm_lab_root() -> Path | None:
    selected = os.environ.get("FACEKIDS_VM_LAB_DIR")
    ack = os.environ.get("FACEKIDS_VM_LAB_ACK")
    if not selected and not ack:
        return None
    if not selected or ack != "ISOLATED_VM_ONLY":
        raise RuntimeError("Incomplete VM-only data isolation opt-in")
    location = Path(selected).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if not location.is_absolute() or not local:
        raise RuntimeError("VM data directory must be absolute and inside LOCALAPPDATA")
    root = location.resolve(strict=False)
    base = Path(local).resolve(strict=False)
    if (root == base or base not in root.parents or
            "facekids-vm-lab" not in (p.casefold() for p in root.parts)):
        raise RuntimeError("VM data path must stay under LOCALAPPDATA/FaceKids-VM-Lab")
    return root

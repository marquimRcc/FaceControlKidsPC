"""Diretórios de runtime sem criar caminhos Windows acidentalmente no Linux."""
from __future__ import annotations

import os
from pathlib import Path
from .vm_lab_paths import vm_lab_root


def application_data_dir() -> Path:
    vm_root = vm_lab_root()
    if vm_root is not None:
        return vm_root / "appdata"
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "FaceKids"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "FaceKids"

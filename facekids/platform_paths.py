"""Diretórios de runtime sem criar caminhos Windows acidentalmente no Linux."""
from __future__ import annotations

import os
from pathlib import Path


def application_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "FaceKids"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "FaceKids"

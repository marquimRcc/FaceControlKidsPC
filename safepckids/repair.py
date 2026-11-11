"""Repara uma instalacao parcial sem remover perfis, fotos ou o PIN atual."""
from __future__ import annotations

import json
import sys

from .installer_engine import PROGRAMDATA_DIR, setup_system


def main() -> int:
    ok, message = setup_system(master_pin="")
    result = {"ok": ok, "message": message}
    PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
    (PROGRAMDATA_DIR / "repair_result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

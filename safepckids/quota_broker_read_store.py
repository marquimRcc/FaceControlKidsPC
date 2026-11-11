"""Read-only SQLite view for the isolated quota broker.

No schema creation, mutation methods, or direct child-selected query fields.
OS-protected directory access remains an installation prerequisite.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import math
import sqlite3


class ReadOnlyQuotaView:
    def __init__(self, path: Path):
        p = Path(path).resolve(strict=True)
        if not p.is_file():
            raise ValueError("Quota database is not a regular file")
        self._db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=5)
        self._db.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "ReadOnlyQuotaView":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def remaining(self, person_id: int, day: str | None = None) -> float:
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Invalid child identifier")
        day = date.today().isoformat() if day is None else day
        if (type(day) is not str or len(day) != 10 or
                date.fromisoformat(day).isoformat() != day):
            raise ValueError("Invalid quota day")
        row = self._db.execute(
            "SELECT daily_limit_seconds FROM people WHERE id=?", (person_id,)
        ).fetchone()
        if row is None:
            raise KeyError(person_id)
        used = self._db.execute(
            "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
            (person_id, day),
        ).fetchone()
        bonus = self._db.execute(
            "SELECT seconds FROM daily_bonus WHERE person_id=? AND day=?",
            (person_id, day),
        ).fetchone()
        result = max(0.0, float(row[0]) + (float(bonus[0]) if bonus else 0) -
                     (float(used[0]) if used else 0))
        if not math.isfinite(result):
            raise ValueError("Invalid quota balance")
        return result

    def is_curfew_active(self) -> tuple[bool, str]:
        settings = dict(self._db.execute(
            "SELECT key,value FROM settings "
            "WHERE key IN ('curfew_enabled','curfew_start','curfew_end')"
        ))
        if settings.get("curfew_enabled") != "true":
            return False, "Disabled"
        start = datetime.strptime(settings.get("curfew_start", "08:00"), "%H:%M").time()
        end = datetime.strptime(settings.get("curfew_end", "20:00"), "%H:%M").time()
        now = datetime.now().time()
        within = start <= now <= end if start <= end else (now >= start or now <= end)
        return not within, "Outside permitted hours" if not within else "Within permitted hours"

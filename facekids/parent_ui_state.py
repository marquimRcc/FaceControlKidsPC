"""View models for the parents' UI; no Tk widgets or mutation of account state.

The dashboard reads the same SQLite store as the existing parent application.
Values here describe UI state only; they are NOT security decisions for logon.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import unicodedata


@dataclass(frozen=True)
class ChildOverview:
    child_id: int
    name: str
    limit_minutes: int
    used_seconds: float
    bonus_minutes: int
    remaining_seconds: float
    samples: int

    @property
    def has_biometrics(self) -> bool:
        return self.samples > 0

    @property
    def total_seconds(self) -> float:
        return max(0.0, self.limit_minutes * 60 + self.bonus_minutes * 60)

    @property
    def remaining_fraction(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return min(1.0, max(0.0, self.remaining_seconds / self.total_seconds))

    @property
    def status_text(self) -> str:
        if not self.has_biometrics:
            return "Rosto pendente"
        if self.remaining_seconds <= 0:
            return "Tempo esgotado"
        return "Biometria cadastrada"


@dataclass(frozen=True)
class ParentsOverview:
    children: tuple[ChildOverview, ...]
    schedule_enabled: bool
    schedule_start: str
    schedule_end: str
    outside_schedule: bool

    @property
    def total_children(self) -> int:
        return len(self.children)

    @property
    def recognized_children(self) -> int:
        return sum(child.has_biometrics for child in self.children)

    @property
    def pending_children(self) -> int:
        return self.total_children - self.recognized_children

    @property
    def remaining_seconds(self) -> float:
        return sum(child.remaining_seconds for child in self.children)

    @property
    def schedule_text(self) -> str:
        if not self.schedule_enabled:
            return "Sem horário configurado"
        return f"{self.schedule_start}–{self.schedule_end}"


def load_overview(store, *, day: str | None = None, current_time: str | None = None) -> ParentsOverview:
    """Build one consistent refresh snapshot from local database reads."""
    day = day or date.today().isoformat()
    children = tuple(
        ChildOverview(
            child_id=pid,
            name=name,
            limit_minutes=limit_seconds // 60,
            used_seconds=float(store.used(pid, day)),
            bonus_minutes=store.bonus(pid, day) // 60,
            remaining_seconds=float(store.remaining(pid, day)),
            samples=store.enrollment_count(pid),
        )
        for pid, name, limit_seconds in store.people()
    )
    enabled, start, end = store.get_curfew_config()
    outside, _ = store.is_curfew_active(current_time_str=current_time) if enabled else (False, "")
    return ParentsOverview(children, enabled, start, end, outside)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def filter_children(children: tuple[ChildOverview, ...], search: str) -> tuple[ChildOverview, ...]:
    """Diacritic-insensitive filtering, without changing any data."""
    query = _fold(search.strip())
    if not query:
        return children
    return tuple(child for child in children
                 if query in _fold(child.name) or query in str(child.child_id))


def screen_time_label(seconds: float) -> str:
    minutes = max(0, int(seconds)) // 60
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}min" if hours else f"{rest} min"

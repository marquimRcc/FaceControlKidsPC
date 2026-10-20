"""Formatação de dados do painel separada da interface."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ChildCard:
    id: int
    name: str
    limit_minutes: int
    used_seconds: int
    bonus_minutes: int
    remaining_seconds: int
    samples: int

def cards_from_storage(db):
    return [ChildCard(pid,name,limit//60,int(db.used(pid)),db.bonus(pid)//60,
                      int(db.remaining(pid)),db.enrollment_count(pid))
            for pid,name,limit in db.people()]

def time_label(seconds):
    hours,minutes=divmod(max(0,int(seconds))//60,60)
    return f"{hours}h {minutes:02d}min"

"""Isolated child screen-time PILOT: no privileged service, no auto-start.

Biometrics and quotas in this module are per-Windows-user test data
modifiable by that user. This is NOT enforcement or a Windows logon
replacement. Use only with the responsible adult's permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import math

from .policy import Action, SessionAwarePolicy
from .session import SessionState

CHILD_LABELS = ("Crianca 1", "Crianca 2", "Crianca 3")
LIMIT_MINUTES = 120


class PilotEvent(str, Enum):
    PAUSED = "SESSAO_PAUSADA"
    NEW_DAY = "NOVO_DIA_REIDENTIFICAR"
    WAIT = "AGUARDANDO_IDENTIFICACAO"
    UNCERTAIN = "ROSTO_NAO_CONFIRMADO"
    COUNTING = "CONTANDO_TEMPO"
    QUOTA_EXHAUSTED = "TEMPO_ESGOTADO_BLOQUEIO_SIMULADO"


@dataclass(frozen=True)
class Reading:
    event: PilotEvent
    child_id: int | None
    charged_seconds: float = 0.0
    remaining_seconds: float | None = None
    # A demo lock *candidate*, not a permission to lock an OS session.
    lock_candidate: bool = False


def provision_three_children(store) -> dict[int, str]:
    """Only fixed pseudonyms, never children's names or actual faces in Git."""
    existing = store.people()
    if existing and {p[1] for p in existing} != set(CHILD_LABELS):
        raise ValueError("Banco piloto contem pessoas inesperadas; nao alterar.")
    for name in CHILD_LABELS:
        if store.get_person(name) is None:
            store.add_person(name, LIMIT_MINUTES)
    people = store.people()
    if len(people) != 3 or {p[1] for p in people} != set(CHILD_LABELS):
        raise ValueError("Banco piloto deve conter exatamente tres criancas.")
    # Never silently change an explicitly configured quota.
    return {pid: name for pid, name, _ in people}


class ChildQuotaEngine:
    """Charge only observed, confirmed, unlocked active use.

    A recognition candidate does not authenticate Windows. Unknown faces
    pause accounting; only confirmed quota exhaustion can nominate a lock.
    """
    def __init__(self, store):
        self.store = store
        self.people = provision_three_children(store)
        self.policy = SessionAwarePolicy(confirm_frames=3, uncertain_grace_sec=30)
        self.last_day: str | None = None

    def step(self, now: float, day: str, session: SessionState,
             recognized: int | None) -> Reading:
        if not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            raise ValueError("Relogio monotônico inválido")
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError("Dia invalido")
        if self.last_day is not None and day != self.last_day:
            self.policy.pause()
            self.last_day = day
            return Reading(PilotEvent.NEW_DAY, None)
        self.last_day = day
        if session is not SessionState.ACTIVE:
            self.policy.pause()
            return Reading(PilotEvent.PAUSED, None)
        if recognized not in self.people:
            recognized = None
        remain = {person_id: self.store.remaining(person_id, day)
                  for person_id in self.people}
        decision = self.policy.step(now, True, recognized, remain)
        charged = 0.0
        if decision.person_id in self.people and decision.seconds_to_charge > 0:
            charged = decision.seconds_to_charge
            # This is a local, user-modifiable MVP ledger, NOT trusted LocalSystem.
            self.store.charge(decision.person_id, charged, day)
        if decision.action is Action.LOCK_QUOTA and decision.person_id in self.people:
            self.policy.pause()
            return Reading(PilotEvent.QUOTA_EXHAUSTED, decision.person_id,
                           charged, self.store.remaining(decision.person_id, day),
                           lock_candidate=True)
        if decision.action is Action.ALLOW and decision.person_id in self.people:
            return Reading(PilotEvent.COUNTING, decision.person_id,
                           charged, self.store.remaining(decision.person_id, day))
        if decision.action is Action.LOCK_UNCERTAIN:
            # User chose to defer unknown-face locking and firewall policies.
            return Reading(PilotEvent.UNCERTAIN, None)
        return Reading(PilotEvent.WAIT, None)

"""Regras puras de decisão: não lê webcam nem chama APIs do sistema."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class Action(str, Enum):
    WAIT = "wait"
    ALLOW = "allow"
    LOCK_QUOTA = "lock_quota"
    LOCK_UNCERTAIN = "lock_uncertain"

@dataclass(frozen=True)
class Decision:
    action: Action
    person_id: int | None = None
    seconds_to_charge: float = 0.0

class Policy:
    def __init__(self, confirm_frames: int = 2, uncertain_grace_sec: float = 30):
        if confirm_frames < 1 or uncertain_grace_sec < 0:
            raise ValueError("Configurações de política inválidas")
        self.confirm_frames = confirm_frames
        self.uncertain_grace_sec = uncertain_grace_sec
        self._candidate = None
        self._streak = 0
        self._active = None
        self._last_at = None
        self._uncertain_since = None

    def step(self, now: float, recognized: int | None, remaining_by_id: dict[int,float]) -> Decision:
        """now: relógio monotônico; recognized: pessoa identificada com confiança ou None.

        Não atribui tempo a uma pessoa quando há dúvida, troca ou perda de rosto.
        Intervalos grandes (suspensão/hibernação) não são cobrados.
        """
        if self._last_at is not None and now < self._last_at:
            raise ValueError("Relógio monotônico retrocedeu")
        dt = 0 if self._last_at is None else now - self._last_at
        self._last_at = now
        if recognized not in remaining_by_id:
            recognized = None
        if recognized != self._candidate:
            self._candidate = recognized
            self._streak = 1
        else:
            self._streak += 1
        confirmed = recognized if recognized is not None and self._streak >= self.confirm_frames else None

        if confirmed is None:
            self._active = None
            if self._uncertain_since is None:
                self._uncertain_since = now
            if now - self._uncertain_since >= self.uncertain_grace_sec:
                return Decision(Action.LOCK_UNCERTAIN)
            return Decision(Action.WAIT)

        self._uncertain_since = None
        remaining = remaining_by_id[confirmed]
        if remaining <= 0:
            self._active = None
            return Decision(Action.LOCK_QUOTA,confirmed)
        charge = min(dt,remaining) if self._active == confirmed and dt <= 15 else 0.0
        self._active = confirmed
        if charge >= remaining and charge > 0:
            return Decision(Action.LOCK_QUOTA,confirmed,charge)
        return Decision(Action.ALLOW,confirmed,charge)

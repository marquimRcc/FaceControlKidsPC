"""P0-47: randomized *motion diagnostic*, NOT actual anti-spoof liveness.

A phone displaying a live/deepfake face or a moved photograph may pass.
No result is accepted by the native Windows broker or credential provider.
This is purposely an isolated pure-Python prototype for future hardware
tests; do NOT wire it to Windows authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import secrets


class Step(Enum):
    CENTER = "center"
    TURN = "turn"
    RECENTER = "recenter"
    OBSERVED_NOT_AUTHENTICATED = "motion_only"
    DENIED = "denied"


@dataclass
class HeadMotionDiagnostic:
    """Yaw offset is normalized to half the inter-eye distance (-1..1).

    The eventual camera adapter must compute it from trusted landmarks.
    Passing a spoofed numeric offset is trivial; it is not identity proof.
    """

    session_id: int
    start_ms: int
    direction: int  # -1 left, +1 right
    step: Step = Step.CENTER
    last_ms: int = 0

    @classmethod
    def begin(cls, session_id: int, start_ms: int) -> "HeadMotionDiagnostic":
        if type(session_id) is not int or session_id <= 0 or start_ms < 0:
            raise ValueError("Invalid diagnostic session")
        return cls(session_id, start_ms, secrets.choice((-1, 1)), last_ms=start_ms)

    def observe(self, *, session_id: int, now_ms: int,
                face_count: int, nose_offset: float) -> Step:
        if self.step in (Step.DENIED, Step.OBSERVED_NOT_AUTHENTICATED):
            return self.step
        if (session_id != self.session_id or face_count != 1 or
                not math.isfinite(nose_offset) or abs(nose_offset) > 1.0 or
                now_ms < self.last_ms or now_ms < self.start_ms or
                now_ms - self.start_ms > 8000):
            self.step = Step.DENIED
            return self.step
        self.last_ms = now_ms
        if self.step is Step.CENTER:
            if abs(nose_offset) <= 0.06:
                self.step = Step.TURN
        elif self.step is Step.TURN:
            if nose_offset * self.direction >= 0.18:
                self.step = Step.RECENTER
            elif nose_offset * self.direction <= -0.18:
                self.step = Step.DENIED
        elif self.step is Step.RECENTER and abs(nose_offset) <= 0.06:
            self.step = Step.OBSERVED_NOT_AUTHENTICATED
        return self.step

    def permits_windows_logon(self) -> bool:
        return False

    def authenticates_liveness(self) -> bool:
        return False

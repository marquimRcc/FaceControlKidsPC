"""Deterministic access-gate state machine for UI-only simulation.

No OS locking, webcam access, persistence or privileged operations are present.
Seconds are supplied by the caller's monotonic simulation clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GateState(str, Enum):
    WAITING = "waiting"
    VERIFYING = "verifying"
    OPEN = "open"
    DENIED = "denied"
    UNKNOWN = "unknown"
    MULTIPLE = "multiple"
    CAMERA_ERROR = "camera_error"
    SERVICE_ERROR = "service_error"


@dataclass
class GateModel:
    names: dict[int, str] = field(
        default_factory=lambda: {1: "Filho 1", 2: "Filho 2", 3: "Filho 3"}
    )
    daily_seconds: int = 7200
    confirmations: int = 2
    away_grace: float = 15.0
    remaining: dict[int, float] = field(init=False)
    state: GateState = field(default=GateState.WAITING, init=False)
    active_child: int | None = field(default=None, init=False)
    last_child: int | None = field(default=None, init=False)
    candidate: int | None = field(default=None, init=False)
    matches: int = field(default=0, init=False)
    absence_since: float | None = field(default=None, init=False)
    last_tick: float | None = field(default=None, init=False)

    def __post_init__(self):
        if not self.names or self.daily_seconds <= 0:
            raise ValueError("At least one child and positive quota are required")
        if self.confirmations < 1 or self.away_grace < 0:
            raise ValueError("Invalid gate timings")
        if len(set(self.names)) != len(self.names):
            raise ValueError("Repeated child IDs")
        self.remaining = {child_id: float(self.daily_seconds) for child_id in self.names}

    @property
    def gate_visible(self) -> bool:
        # A visual indicator only. This does not secure the Windows desktop.
        return self.state is not GateState.OPEN

    def advance(self, now: float) -> None:
        """Charge only a confirmed child with continuing face presence."""
        now = float(now)
        if self.last_tick is None:
            self.last_tick = now
            return
        if now < self.last_tick:
            raise ValueError("Clock moved backwards")
        elapsed = now - self.last_tick
        self.last_tick = now

        if self.state is GateState.OPEN and self.active_child is not None:
            if self.absence_since is None:
                previous = self.remaining[self.active_child]
                self.remaining[self.active_child] = max(0.0, previous - elapsed)
                if self.remaining[self.active_child] == 0:
                    self.last_child = self.active_child
                    self._restrict(GateState.DENIED)
                    return
            elif now - self.absence_since >= self.away_grace:
                self._restrict(GateState.WAITING)

    def _restrict(self, new_state: GateState) -> None:
        self.state = new_state
        self.active_child = None
        self.candidate = None
        self.matches = 0
        self.absence_since = None

    def observe(self, observation: int | str | None, now: float) -> GateState:
        """Submit a simulated facial observation.

        Child IDs are recognized faces; None is no face; strings represent
        error or ambiguous observations. A real camera adapter is NOT wired.
        """
        self.advance(now)

        if observation is None:
            self.candidate = None
            self.matches = 0
            if self.state is GateState.OPEN and self.active_child is not None:
                if self.absence_since is None:
                    self.absence_since = float(now)
                if self.away_grace == 0:
                    self._restrict(GateState.WAITING)
            elif self.state not in (GateState.CAMERA_ERROR, GateState.SERVICE_ERROR):
                self._restrict(GateState.WAITING)
            return self.state

        if type(observation) is not int or observation not in self.names:
            states = {"unknown": GateState.UNKNOWN,
                      "multiple": GateState.MULTIPLE,
                      "camera_error": GateState.CAMERA_ERROR,
                      "service_error": GateState.SERVICE_ERROR}
            if observation not in states:
                raise ValueError("Invalid simulated observation")
            self._restrict(states[observation])
            return self.state

        child = observation
        self.absence_since = None
        if self.state is GateState.OPEN and self.active_child == child:
            return self.state

        # If a different child is seen, restrict immediately while verifying.
        if self.active_child != child:
            self.active_child = None
        if self.candidate == child:
            self.matches += 1
        else:
            self.candidate = child
            self.matches = 1

        if self.matches < self.confirmations:
            self.state = GateState.VERIFYING
        elif self.remaining[child] <= 0:
            self.last_child = child
            self._restrict(GateState.DENIED)
        else:
            self.active_child = child
            self.last_child = child
            self.state = GateState.OPEN
        return self.state

    def fast_forward(self, seconds: float, now: float) -> None:
        """Advance demo time only; balances are in memory and never persisted."""
        if seconds < 0:
            raise ValueError("Cannot rewind simulation time")
        self.advance(now + seconds)

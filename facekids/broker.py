"""Server-side identity and screen-time accounting rules.

The Windows transport must supply authenticated SIDs; never read them from JSON.
This module is NOT itself a privileged Windows service.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict
import numpy as np

from .dashboard import cards_from_storage
from .policy import SessionAwarePolicy
from .recognition import Recognizer


class AccessDenied(PermissionError):
    pass


class Broker:
    def __init__(self, store, parent_sid, child_sid, clock=None):
        if not parent_sid or not child_sid or parent_sid == child_sid:
            raise ValueError("Parent and child SIDs must differ")
        self.store = store
        self.parent_sid = parent_sid
        self.child_sid = child_sid
        self.clock = clock or time.monotonic
        self.lock = threading.RLock()
        self.policy = SessionAwarePolicy(confirm_frames=2, uncertain_grace_sec=30)
        self.enroll_id = None
        self.enroll_until = 0.0
        self.enroll_count = 0
        self.last_enroll_at = float("-inf")
        self.last_observation_at = float("-inf")

    @staticmethod
    def vector(raw):
        if not isinstance(raw, list) or len(raw) != 128:
            raise ValueError("Expected 128 SFace features")
        if any(type(x) not in (int, float) for x in raw):
            raise ValueError("Invalid feature type")
        vector = np.asarray(raw, dtype=np.float32)
        if not np.all(np.isfinite(vector)) or float(np.linalg.norm(vector)) < 1e-8:
            raise ValueError("Invalid facial features")
        return vector

    def dispatch(self, caller_sid, request):
        if not isinstance(request, dict) or not isinstance(request.get("op"), str):
            raise ValueError("Invalid request")
        with self.lock:
            if caller_sid == self.parent_sid:
                return self._parent(request)
            if caller_sid == self.child_sid:
                return self._child(request)
            raise AccessDenied("Windows account not permitted")

    def _parent(self, req):
        op = req["op"]
        if op == "ping":
            return {"ok": True, "role": "parent"}
        if op == "status":
            return {"children": [asdict(c) for c in cards_from_storage(self.store)],
                    "enrollment_id": self.enroll_id if self.clock() < self.enroll_until else None}
        if op == "add":
            if type(req.get("minutes")) is not int or not isinstance(req.get("name"), str):
                raise ValueError("Expected name and integer minutes")
            return {"id": self.store.add_person(req["name"], req["minutes"])}
        if op in ("limit", "bonus"):
            pid, mins = req.get("id"), req.get("minutes")
            if type(pid) is not int or type(mins) is not int:
                raise ValueError("Expected child ID and integer minutes")
            if op == "limit":
                self.store.set_daily_limit(pid, mins)
            else:
                self.store.add_bonus(pid, mins)
            return {"ok": True}
        if op == "enroll":
            pid = req.get("id")
            if type(pid) is not int or pid not in {p[0] for p in self.store.people()}:
                raise ValueError("Unknown child")
            self.enroll_id = pid
            self.enroll_until = self.clock() + 180
            self.enroll_count = 0
            self.last_enroll_at = float("-inf")
            self.policy.pause()
            return {"ok": True, "enrollment_seconds": 180}
        if op == "cancel_enroll":
            self.enroll_id = None
            self.policy.pause()
            return {"ok": True}
        raise ValueError("Unsupported parent operation")

    def _child(self, req):
        op = req["op"]
        if op == "ping":
            return {"ok": True, "role": "child",
                    "enrollment_id": self.enroll_id if self.clock() < self.enroll_until else None}
        if op == "pause":
            # Safe for prototype only: service must verify WTS session state
            # before accepting child-requested pause for enforcement.
            self.policy.pause()
            return {"action": "paused"}
        if op != "observe":
            raise AccessDenied("Child account cannot modify quotas")

        now = self.clock()
        if now - self.last_observation_at < 0.2:
            raise ValueError("Observations too frequent")
        raw = req.get("features")
        vector = self.vector(raw) if raw is not None else None
        self.last_observation_at = now

        if self.enroll_id is not None and now < self.enroll_until:
            if vector is not None and now - self.last_enroll_at >= 0.5:
                self.store.add_embedding(self.enroll_id, vector)
                self.enroll_count += 1
                self.last_enroll_at = now
            if self.enroll_count >= 20:
                self.enroll_id = None
                self.policy.pause()
                return {"action": "enrollment_complete"}
            return {"action": "enrolling", "samples": self.enroll_count}
        self.enroll_id = None

        identified = None
        embeddings = self.store.embeddings()
        if vector is not None and embeddings:
            identified, _ = Recognizer.identify(vector, embeddings)
        balances = {row[0]: self.store.remaining(row[0]) for row in self.store.people()}
        decision = self.policy.step(now, True, identified, balances)
        if decision.person_id is not None and decision.seconds_to_charge > 0:
            self.store.charge(decision.person_id, decision.seconds_to_charge)
        return {"action": decision.action.value,
                "child_id": decision.person_id,
                "remaining_seconds": int(self.store.remaining(decision.person_id))
                if decision.person_id is not None else None}

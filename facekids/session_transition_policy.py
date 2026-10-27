"""Single, side-effect-free authority for changes of the active child profile.

The input describes a validated *facial observation*, not an unlock event.
It does not authenticate an IPC peer: that belongs to the caller.
"""
from __future__ import annotations

from enum import Enum
import math
from typing import Optional, Sequence


class TransitionDecision(str, Enum):
    KEEP_CURRENT = "keep-current"
    SUPPRESS_MULTIPLE_FACES = "suppress-multiple-faces"
    SWITCH_CHILD = "switch-child"
    INVALID_OBSERVATION = "invalid-observation"


def decide_child_transition(
    current_child_id: Optional[int], detected_ids: Sequence[int],
    face_count: int, effective_idle_seconds: float, candidate_id: Optional[int],
    *, observation_age_seconds: float, idle_threshold_seconds: float = 15.0,
    maximum_observation_age_seconds: float = 15.0,
) -> TransitionDecision:
    """Prioritize current operator, then input recency, then single-face switch.

    Unassigned sessions may adopt one recognized face immediately, including
    after PIN login. A background face cannot override an active operator.
    """
    if (current_child_id is not None and
            (type(current_child_id) is not int or current_child_id <= 0)):
        return TransitionDecision.INVALID_OBSERVATION
    if (type(candidate_id) is not int or candidate_id <= 0 or
            type(face_count) is not int or face_count <= 0 or
            not isinstance(detected_ids, (list, tuple)) or
            len(detected_ids) > face_count or
            any(type(pid) is not int or pid <= 0 for pid in detected_ids) or
            len(set(detected_ids)) != len(detected_ids) or
            candidate_id not in detected_ids):
        return TransitionDecision.INVALID_OBSERVATION
    scalars = (effective_idle_seconds, observation_age_seconds,
               idle_threshold_seconds, maximum_observation_age_seconds)
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in scalars)
            or effective_idle_seconds < 0 or observation_age_seconds < 0
            or idle_threshold_seconds <= 0 or maximum_observation_age_seconds <= 0
            or observation_age_seconds > maximum_observation_age_seconds):
        return TransitionDecision.INVALID_OBSERVATION
    if current_child_id is not None and current_child_id in detected_ids:
        return TransitionDecision.KEEP_CURRENT
    if current_child_id is not None and effective_idle_seconds < idle_threshold_seconds:
        return TransitionDecision.KEEP_CURRENT
    if face_count > 1:
        return TransitionDecision.SUPPRESS_MULTIPLE_FACES
    if candidate_id == current_child_id:
        return TransitionDecision.KEEP_CURRENT
    return TransitionDecision.SWITCH_CHILD

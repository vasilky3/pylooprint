"""User-facing settings for a loop build.

One frozen dataclass carries everything the pipeline needs, so that neither the
core nor the printer profiles ever reach for global state (the original tool
read every value straight off DOM elements).
"""

from __future__ import annotations

from dataclasses import dataclass

# Limits copied from the original tool so that CLI validation behaves the same.
MIN_LOOPS = 1
MAX_LOOPS = 1000
#: One copy by default - the eject sequence is useful on its own, and looping is
#: the exception rather than the rule.
DEFAULT_LOOPS = 1

MIN_TEMP = 15
MAX_TEMP = 90
DEFAULT_TEMP = 18
COOLDOWN_WARNING_THRESHOLD = 35

MIN_PUSH_LANE_OFFSET = 10
MAX_PUSH_LANE_OFFSET = 60
DEFAULT_PUSH_LANE_OFFSET = 30

MIN_PUSH_SPEED = 100
MAX_PUSH_SPEED = 1000
DEFAULT_PUSH_SPEED = 300

MIN_SWEEP_SPEED = 100
MAX_SWEEP_SPEED = 1000
DEFAULT_SWEEP_SPEED = 300

MIN_SWEEP_Z = 0.5
MAX_SWEEP_Z = 50.0
DEFAULT_SWEEP_Z = 1.0

DEFAULT_SPEED_MODE = 100


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class LoopSettings:
    """Everything the user can tune for one build."""

    loops: int = DEFAULT_LOOPS
    cooldown_temp: int = DEFAULT_TEMP
    speed_mode: int = DEFAULT_SPEED_MODE
    #: P1/X1 only - distance of the outer push lanes from the model centre.
    push_lane_offset: float = DEFAULT_PUSH_LANE_OFFSET
    #: P1/X1 only - feedrate of the push move.
    push_speed: float = DEFAULT_PUSH_SPEED
    #: P1/X1 only - the optional full-bed sweep after the push.
    sweep_enabled: bool = False
    sweep_speed: float = DEFAULT_SWEEP_SPEED
    sweep_z: float = DEFAULT_SWEEP_Z
    #: P1/X1 only - use the start template that keeps the filament flush.
    purge_enabled: bool = True
    #: A1 only - the (dangerous) negative-Z release sequence.
    negative_z_enabled: bool = False

    @property
    def validated_push_speed(self) -> float:
        return _clamp(self.push_speed, MIN_PUSH_SPEED, MAX_PUSH_SPEED)

    @property
    def validated_sweep_speed(self) -> float:
        return _clamp(self.sweep_speed, MIN_SWEEP_SPEED, MAX_SWEEP_SPEED)

    @property
    def validated_sweep_z(self) -> float:
        return _clamp(self.sweep_z, MIN_SWEEP_Z, MAX_SWEEP_Z)

    @property
    def validated_push_lane_offset(self) -> float:
        offset = self.push_lane_offset
        if offset < MIN_PUSH_LANE_OFFSET or offset > MAX_PUSH_LANE_OFFSET:
            return DEFAULT_PUSH_LANE_OFFSET
        return offset

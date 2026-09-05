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
DEFAULT_TEMP = 26
COOLDOWN_WARNING_THRESHOLD = 35

#: How long to sit at the park height once the bed has reached its target, before
#: the beep and the push-off.  Zero skips the wait; the beep always sounds.
MIN_HOLD_SECONDS = 0
MAX_HOLD_SECONDS = 3600
DEFAULT_HOLD_SECONDS = 300


@dataclass(frozen=True)
class LoopSettings:
    """Everything the user can tune for one build."""

    loops: int = DEFAULT_LOOPS
    cooldown_temp: int = DEFAULT_TEMP
    hold_seconds: int = DEFAULT_HOLD_SECONDS

"""The wait and bed shake that run between the cool-down and the push-off.

Two things have to hold no matter what:

* nothing in the block moves Z, because the toolhead has to stay at the park
  height - that is what keeps the limit-switch fan mod running; and
* the bed ends the shake exactly where it started, because the eject keep-out
  zone is measured for the bed's parked position.
"""

from __future__ import annotations

import re

import pytest

from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.bedslinger import (
    SHAKE_CYCLES,
    SHAKE_MAX_HZ,
    SHAKE_MIN_HZ,
    SHAKE_STEPS,
    SHAKE_STROKE_MM,
)
from pylooprint.settings import DEFAULT_HOLD_SECONDS, LoopSettings

HOLD_START = ";======= LOOPRINT RELEASE HOLD ======="
HOLD_END = ";======= END LOOPRINT RELEASE HOLD ======="

_SHAKE_MOVE_RE = re.compile(r"^G1 Y(-?[\d.]+) F(\d+)$", re.MULTILINE)

A1_MINI = get_profile("a1mini")


def _end_code(key: str = "a1mini", **overrides) -> str:
    settings = LoopSettings(loops=1, cooldown_temp=23, **overrides)
    return get_profile(key).end_code(EndCodeContext(settings=settings))


def _block(code: str) -> str:
    return code[code.index(HOLD_START) : code.index(HOLD_END) + len(HOLD_END)]


@pytest.mark.parametrize("key", ["a1", "a1mini"])
def test_the_block_sits_between_the_cool_down_and_the_push_off(key):
    code = _end_code(key)
    assert code.rindex("M190") < code.index(HOLD_START)
    assert code.index(HOLD_END) < code.index("@PUSH@" if "@PUSH@" in code else "Start Push Off")


def test_the_default_wait_is_five_minutes():
    assert DEFAULT_HOLD_SECONDS == 300
    assert f"G4 S{DEFAULT_HOLD_SECONDS} ; hold before the push-off" in _end_code()


def test_the_shake_runs_even_without_a_wait():
    """``--hold 0`` drops the wait only; the shake is not optional."""
    code = _end_code(hold_seconds=0)
    assert "G4 S" not in _block(code)
    assert HOLD_START in code
    assert len(_SHAKE_MOVE_RE.findall(_block(code))) == 2 * SHAKE_STEPS * SHAKE_CYCLES


def test_the_sweep_climbs_from_the_low_frequency_to_the_high_one():
    moves = _SHAKE_MOVE_RE.findall(_block(_end_code()))
    assert len(moves) == 2 * SHAKE_STEPS * SHAKE_CYCLES

    feeds = [int(feed) for _, feed in moves]
    assert feeds == sorted(feeds)
    # One cycle covers two strokes in 1/f seconds.
    assert feeds[0] == round(120 * SHAKE_STROKE_MM * SHAKE_MIN_HZ)
    assert feeds[-1] == round(120 * SHAKE_STROKE_MM * SHAKE_MAX_HZ)
    assert len(set(feeds)) == SHAKE_STEPS


def test_the_bed_returns_to_where_it_started():
    """Relative moves that sum to zero - the keep-out zone assumes the park Y."""
    block = _block(_end_code())
    assert "G91" in block and "G90" in block
    assert block.index("G91") < block.index("G90")
    assert sum(float(offset) for offset, _ in _SHAKE_MOVE_RE.findall(block)) == 0.0


def test_nothing_in_the_block_moves_z_or_x():
    """The toolhead must stay parked: on the A1 Mini that is the fan switch."""
    commands = [line for line in _block(_end_code()).split("\n") if line and not line.startswith(";")]
    assert commands, "the block emitted nothing but comments"
    for command in commands:
        assert "Z" not in command.split(";")[0]
        assert "X" not in command.split(";")[0]


def test_the_hold_is_still_at_the_park_height_in_the_inplace_end_code(golden_project):
    from pylooprint.core.project import ThreeMfProject
    from pylooprint.pipeline import build_loops, detect_printer

    project = ThreeMfProject.open(golden_project)
    gcode = build_loops(
        project, detect_printer(project), LoopSettings(loops=1, cooldown_temp=28), source_name="x.3mf"
    ).gcode
    # Z only comes back down after the block has finished.
    assert gcode.index(HOLD_END) < gcode.index("G1 Z1 F3600 ; return to base position")
    assert gcode.rindex("M190 S24") < gcode.index(HOLD_START)


@pytest.mark.parametrize("key", ["p1", "x1"])
def test_corexy_printers_never_get_the_block(key):
    """The CoreXY bed only moves in Z - there is nothing to shake."""
    assert HOLD_START not in _end_code(key)

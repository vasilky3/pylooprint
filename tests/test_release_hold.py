"""The wait and the beep that run between the cool-down and the push-off.

Two things have to hold no matter what:

* nothing in the hold block moves the machine, because the toolhead has to stay
  at the park height - that is what keeps the limit-switch fan mod running -
  and the bed has to stay where the eject keep-out zone was measured for; and
* every printer sounds the beep before it pushes, since that is the only
  warning that the machine is about to move again.
"""

from __future__ import annotations

import pytest

from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.base import BEEP_END, BEEP_START
from pylooprint.printers.p1 import _PUSH_OFF_HEADING
from pylooprint.settings import DEFAULT_HOLD_SECONDS, LoopSettings

HOLD_START = ";======= LOOPRINT RELEASE HOLD ======="
HOLD_END = ";======= END LOOPRINT RELEASE HOLD ======="

A1_MINI = get_profile("a1mini")


def _end_code(key: str = "a1mini", **overrides) -> str:
    settings = LoopSettings(loops=1, cooldown_temp=26, **overrides)
    return get_profile(key).end_code(EndCodeContext(settings=settings))


def _block(code: str) -> str:
    return code[code.index(HOLD_START) : code.index(HOLD_END) + len(HOLD_END)]


def _push_index(code: str) -> int:
    """Where the eject sequence starts, whichever template the profile assembled.

    On the CoreXY machines that is the bed drop under its own heading; on the
    bed slingers it is the push block the head template hands over to.
    """
    for marker in (_PUSH_OFF_HEADING, "@PUSH@", "Start Push Off"):
        if marker in code:
            return code.index(marker)
    raise AssertionError("no push-off found in the end code")


@pytest.mark.parametrize("key", ["a1", "a1mini"])
def test_the_block_sits_between_the_cool_down_and_the_push_off(key):
    code = _end_code(key)
    assert code.rindex("M190") < code.index(HOLD_START)
    assert code.index(HOLD_END) < _push_index(code)


def test_the_default_wait_is_five_minutes():
    assert DEFAULT_HOLD_SECONDS == 300
    assert f"G4 S{DEFAULT_HOLD_SECONDS} ; hold before the push-off" in _end_code()


def test_the_beep_sounds_even_without_a_wait():
    """``--hold 0`` drops the wait only; the beep is not optional."""
    code = _end_code(hold_seconds=0)
    assert "G4 S" not in _block(code)
    assert BEEP_START in _block(code)


@pytest.mark.parametrize("key", ["a1", "a1mini", "p1", "x1"])
def test_every_printer_beeps_before_the_push(key):
    code = _end_code(key)
    assert code.count(BEEP_START) == 1
    assert code.count("M1006 W") >= 1
    assert code.index(BEEP_START) < code.index(BEEP_END) < _push_index(code)


def test_nothing_in_the_block_moves_the_machine():
    """The toolhead must stay parked: on the A1 Mini that is the fan switch.

    The bed must stay put too - the eject keep-out zone assumes the park Y.
    """
    commands = [line for line in _block(_end_code()).split("\n") if line and not line.startswith(";")]
    assert commands, "the block emitted nothing but comments"
    for command in commands:
        # G4 (dwell) is the only G-code left in the block; everything else is
        # an M-code that talks to the firmware without moving an axis.
        assert not command.startswith("G") or command.startswith("G4 ")


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
def test_corexy_printers_never_get_the_hold(key):
    """The CoreXY bed cannot hold the toolhead at a park height; only the beep runs."""
    assert HOLD_START not in _end_code(key)

"""The wait and the beep that run between the cool-down and the push-off.

Nothing in the hold block may move the machine: the toolhead has to stay at the
park height - that is what keeps a limit-switch fan mod running - and the bed
has to stay where the eject keep-out zone was measured for.  And the beep
always sounds, since it is the only warning that the machine is about to move.
"""

from __future__ import annotations

from pylooprint.core.project import ThreeMfProject
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.printers import EndCodeContext
from pylooprint.printers.base import BEEP_END, BEEP_START
from pylooprint.printers.bedslinger import HOLD_END, HOLD_START, PUSH_PLAN_START
from pylooprint.settings import DEFAULT_HOLD_SECONDS, LoopSettings

from conftest import a1mini_end_code


def _end_code(**overrides) -> str:
    settings = LoopSettings(loops=1, cooldown_temp=26, **overrides)
    return a1mini_end_code(EndCodeContext(settings=settings))


def _block(code: str) -> str:
    return code[code.index(HOLD_START) : code.index(HOLD_END) + len(HOLD_END)]


def _push_index(code: str) -> int:
    """Where the eject sequence starts - the push block or its one-line form."""
    for marker in (PUSH_PLAN_START, "One-line push"):
        if marker in code:
            return code.index(marker)
    raise AssertionError("no push-off found in the end code")


def test_the_block_sits_between_the_cool_down_and_the_push_off():
    code = _end_code()
    assert code.rindex("M190") < code.index(HOLD_START)
    assert code.index(HOLD_END) < _push_index(code)


def test_the_default_wait_is_what_the_settings_say():
    assert DEFAULT_HOLD_SECONDS > 0
    assert f"G4 S{DEFAULT_HOLD_SECONDS} ; hold before the push-off" in _end_code()


def test_the_beep_sounds_even_without_a_wait():
    """``--hold 0`` drops the wait only; the beep is not optional."""
    code = _end_code(hold_seconds=0)
    assert "G4 S" not in _block(code)
    assert BEEP_START in _block(code)


def test_the_beep_comes_right_before_the_push():
    code = _end_code()
    assert code.count(BEEP_START) == 1
    assert code.count("M1006 W") >= 1
    assert code.index(BEEP_START) < code.index(BEEP_END) < _push_index(code)


def test_nothing_in_the_block_moves_the_machine():
    commands = [line for line in _block(_end_code()).split("\n") if line and not line.startswith(";")]
    assert commands, "the block emitted nothing but comments"
    for command in commands:
        # G4 (dwell) is the only G-code left in the block; everything else is
        # an M-code that talks to the firmware without moving an axis.
        assert not command.startswith("G") or command.startswith("G4 ")


def test_the_hold_is_at_the_park_height_in_a_built_file(cone_multi_project):
    project = ThreeMfProject.open(cone_multi_project)
    gcode = build_loops(
        project, detect_printer(project), LoopSettings(loops=1, cooldown_temp=28), source_name="x.3mf"
    ).gcode
    # Z only comes back down after the block has finished.
    assert gcode.index(HOLD_END) < gcode.index("G1 Z1 F3600 ; return to base position")
    assert gcode.rindex("M190 S24") < gcode.index(HOLD_START)

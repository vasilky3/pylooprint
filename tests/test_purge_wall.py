"""Shoving the purge wall off the front lip at the end of the sweep.

The looping profile prints a small wall on the strip in front of the plate at
every start; nothing in pylooprint knows or cares how, but the sweep has to end
by knocking it off, or the next loop prints on top of it.  The move rides the
return stroke: along the strip just swept to the wall's middle, then the bed
forward past the lip so the wall is hit broadside.
"""

from __future__ import annotations

from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.a1_mini import PURGE_SWEEP_Y, PURGE_WALL_X
from pylooprint.settings import LoopSettings

SHOVE_MARKER = ";----- purge wall: off the front lip on the way back -----"


def _sweep(key: str) -> list[str]:
    return [line for line in get_profile(key).wiggle_sweep().split("\n") if line]


def test_the_a1_mini_sweep_ends_by_shoving_the_wall_off():
    sweep = _sweep("a1mini")
    shove = sweep.index(SHOVE_MARKER)

    assert sweep[shove + 1].startswith(f"G1 X{PURGE_WALL_X:g} F2000")
    assert sweep[shove + 2].startswith(f"G1 Y{PURGE_SWEEP_Y:g} F800")
    assert sweep[shove + 3].startswith("G1 Y185 F2000")  # the sweep's own last line
    assert shove + 3 == len(sweep) - 1


def test_the_shove_comes_after_the_last_strip():
    """The plate is empty by then, so dragging along it hits nothing else."""
    sweep = _sweep("a1mini")

    last_strip = max(i for i, line in enumerate(sweep) if line.startswith("G1 Y0 F2000"))
    assert sweep.index(SHOVE_MARKER) > last_strip
    # The strips themselves are exactly what they were.
    assert [line for line in sweep[: sweep.index(SHOVE_MARKER)]] == _sweep("a1mini")[: sweep.index(SHOVE_MARKER)]


def test_the_shove_goes_past_the_wall_but_not_past_what_the_machine_reaches():
    """The stock purge line is drawn at Y-4, so Y-5 is known ground."""
    assert -5.0 <= PURGE_SWEEP_Y < -3.46


def test_a_profile_without_a_wall_keeps_its_sweep():
    """The A1's profile is not prepared; its sweep must not change."""
    sweep = _sweep("a1")

    assert SHOVE_MARKER not in sweep
    assert get_profile("a1").purge_wall_x is None
    assert sweep[-1].startswith("G1 Y262 F2000")


def test_the_shove_is_in_the_end_code_of_every_loop():
    context = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=23))
    code = get_profile("a1mini").end_code(context)

    assert code.count(SHOVE_MARKER) == 1
    assert code.index(SHOVE_MARKER) < code.rindex("G1 Y185 F2000 ;move bed forward one last time")

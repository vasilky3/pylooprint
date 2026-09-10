"""``--zpush``: work each part loose before pushing it off.

A straight shove asks the plate to let go all at once.  The z-push instead stops
just short of the part and then presses and swipes at it - forward and up
together, which scoops under the part - coming back and down again each time, so
the blade bites ``ZPUSH_PRESS_MM`` deeper per cycle.  The ordinary push then
carries the loosened part away.
"""

from __future__ import annotations

import pytest

from pylooprint.core.parts import PartBounds
from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.bedslinger import (
    PUSH_END_Y,
    PUSH_PLAN_START,
    ZPUSH_APPROACH_MM,
    ZPUSH_CYCLES,
    ZPUSH_PRESS_MM,
    ZPUSH_SWIPE_MM,
)
from pylooprint.settings import LoopSettings

A1_MINI = get_profile("a1mini")


def _part(centre_x: float, top: float, *, back_y: float = 100.0, depth: float = 40.0) -> PartBounds:
    return PartBounds(centre_x - 5, centre_x + 5, back_y - depth, back_y, 0.2, top)


def _push_block(*parts: PartBounds, zpush: bool = True) -> list[str]:
    """The moves of the push plan, comments and blank lines dropped."""
    settings = LoopSettings(loops=1, cooldown_temp=23, zpush=zpush)
    code = A1_MINI.end_code(EndCodeContext(settings=settings, parts=parts))
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]
    return [line for line in block.split("\n") if line.startswith(("G0 ", "G1 "))]


def _approach(moves: list[str]) -> str:
    return next(line for line in moves if "short of the part" in line)


def _cycles(moves: list[str]) -> list[list[str]]:
    """The press-and-swipe cycles: everything between the approach and the push."""
    start = moves.index(_approach(moves)) + 1
    end = next(index for index, line in enumerate(moves) if line.startswith("G1 Y-0.5"))
    body = moves[start:end]
    assert len(body) % 4 == 0, f"a cycle is four moves, got {len(body)}"
    return [body[index : index + 4] for index in range(0, len(body), 4)]


def test_the_approach_stops_short_of_the_part():
    moves = _push_block(_part(50, 30, back_y=103.83))

    # Up to the push height first, then in towards the part but not onto it.
    assert moves.index("G1 Z21.00 F600	; up to 0.7 of the shortest part on this line"
                       " - at a new X, Z only ever goes up") < moves.index(_approach(moves))
    assert _approach(moves).startswith(f"G1 Y{103.83 + ZPUSH_APPROACH_MM:.2f} F300")


def test_the_approach_never_reaches_behind_the_bed():
    """A part at the very back leaves no room for the 2 mm of approach."""
    moves = _push_block(_part(50, 30, back_y=179.5))

    assert _approach(moves).startswith(f"G1 Y{A1_MINI.y_forward:.2f} F300")


def test_each_cycle_presses_swipes_and_comes_back():
    moves = _push_block(_part(50, 30, back_y=100.0))
    z = 21.0  # 30 * 0.7
    start = 100.0 + ZPUSH_APPROACH_MM

    first, *_ = _cycles(moves)
    pressed = start - ZPUSH_PRESS_MM
    swiped = pressed - ZPUSH_SWIPE_MM
    assert first == [
        f"G1 Y{pressed:.2f} F300",
        f"G1 Y{swiped:.2f} Z{z + ZPUSH_SWIPE_MM:.2f} F300",
        f"G1 Y{pressed:.2f} F300",
        f"G1 Z{z:.2f} F600",
    ]


def test_every_cycle_advances_by_the_press_distance():
    moves = _push_block(_part(50, 30, back_y=100.0))
    cycles = _cycles(moves)

    assert len(cycles) == ZPUSH_CYCLES
    pressed = [float(cycle[0].split()[1][1:]) for cycle in cycles]
    steps = [before - after for before, after in zip(pressed, pressed[1:])]
    assert steps == [pytest.approx(ZPUSH_PRESS_MM)] * (ZPUSH_CYCLES - 1)


def test_every_cycle_ends_at_the_height_it_started():
    """Z is only ever *up* inside a cycle, and back down at the same Y."""
    moves = _push_block(_part(50, 30, back_y=100.0))

    for cycle in _cycles(moves):
        assert cycle[1].endswith("Z22.00 F300")  # 21 + 1 swipe
        assert cycle[3] == "G1 Z21.00 F600"


def test_a_part_near_the_front_edge_gets_fewer_cycles():
    """Better a short working-over than moves past the end of the push."""
    moves = _push_block(_part(50, 30, back_y=8.0, depth=6.0))
    cycles = _cycles(moves)

    assert 0 < len(cycles) < ZPUSH_CYCLES
    reached = [
        float(word[1:])
        for cycle in cycles
        for move in cycle
        for word in move.split()
        if word.startswith("Y")
    ]
    assert min(reached) > PUSH_END_Y


def test_the_push_still_finishes_at_the_plate_edge():
    moves = _push_block(_part(50, 30, back_y=100.0))

    pushes = [line for line in moves if line.startswith("G1 Y-0.5")]
    assert len(pushes) == 1
    # The push is the last thing the line does: then the bed comes back, the
    # blade drops to the travel height, and the plan tail readies the sweep.
    assert moves[-3:] == [
        "G1 Y180 F800	; bed back along the band just swept, at the same height",
        "G1 Z0.20 F600	; back to the travel height,"
        " at a point the nozzle has already been",
        "G1 Z1 F600		;move nozzle closer to the bed for the sweep",
    ]
    assert moves[-4] == pushes[0]


def test_without_the_flag_the_push_is_one_straight_shove():
    moves = _push_block(_part(50, 30, back_y=100.0), zpush=False)

    assert [line.split(";")[0].strip() for line in moves] == [
        "G1 Z0.20 F600",
        "G0 X50.00 F12000",
        "G1 Z21.00 F600",
        "G1 Y-0.5 F300",
        "G1 Y180 F800",
        "G1 Z0.20 F600",
        "G1 Z1 F600",
    ]


def test_every_line_of_a_multi_part_plate_is_worked_loose():
    moves = _push_block(_part(34, 50, back_y=90.0), _part(146, 10, back_y=60.0))

    assert len([line for line in moves if line.startswith("G1 Y92.00")]) == 1
    assert len([line for line in moves if line.startswith("G1 Y62.00")]) == 1
    assert len([line for line in moves if line.startswith("G1 Y-0.5")]) == 2


def test_the_plan_header_says_what_the_cycles_will_do():
    settings = LoopSettings(loops=1, cooldown_temp=23, zpush=True)
    code = A1_MINI.end_code(EndCodeContext(settings=settings, parts=(_part(50, 30),)))

    assert f"; {ZPUSH_CYCLES} press-and-swipe cycles" in code

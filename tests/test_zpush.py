"""``--zpush``: work each part loose before pushing it off.

A straight shove asks the plate to let go all at once.  The z-push instead stops
just short of the part and then presses and swipes at it - forward and up
together, which scoops under the part - coming back and down again each time, so
the blade bites ``ZPUSH_PRESS_MM`` deeper per cycle.  The ordinary push then
carries the loosened part away.

Where "just short of the part" is can only come from the G-code, so these tests
go through the real measurement rather than handing the profile a number.  The
machine's own figures - the blade, the cycle, the bumper's offset - are tuning,
so nothing here spells them out either.
"""

from __future__ import annotations

import pytest

from pylooprint.core.jsnum import to_fixed
from pylooprint.core.parts import PartBounds, find_parts
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.push_plan import PushLine
from pylooprint.core.structure import split_gcode
from pylooprint.pipeline import build_loops, detect_printer
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


def _body(parts) -> str:
    """G-code whose plastic stands along each part's own back edge, full height."""
    moves = []
    for part in parts:
        moves.append(f"G0 X{part.min_x} Y{part.max_y} Z{part.max_z}")
        moves.append(f"G1 X{part.max_x} Y{part.max_y} E1")
    return "\n".join(moves)


def _plan(*parts: PartBounds) -> list[PushLine]:
    """The push as the pipeline would hand it over: contacts measured."""
    return A1_MINI.push_plan(parts, _body(parts))


def _push_block(*parts: PartBounds, zpush: bool = True, lines=None) -> list[str]:
    """The moves of the push plan, comments and blank lines dropped."""
    settings = LoopSettings(loops=1, cooldown_temp=23, zpush=zpush)
    planned = _plan(*parts) if lines is None else lines
    code = A1_MINI.end_code(
        EndCodeContext(settings=settings, parts=parts, push_lines=tuple(planned))
    )
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]
    return [line for line in block.split("\n") if line.startswith(("G0 ", "G1 "))]


def _approach(moves: list[str]) -> str:
    return next(line for line in moves if "short of the part" in line)


def _approaches(moves: list[str]) -> list[str]:
    """The Y of each approach move, as the G-code spells it."""
    return [line.split()[1][1:] for line in moves if "short of the part" in line]


def _cycles(moves: list[str]) -> list[list[str]]:
    """The press-and-swipe cycles: everything between the approach and the push."""
    start = moves.index(_approach(moves)) + 1
    end = next(index for index, line in enumerate(moves) if line.startswith("G1 Y-0.5"))
    body = moves[start:end]
    assert len(body) % 4 == 0, f"a cycle is four moves, got {len(body)}"
    return [body[index : index + 4] for index in range(0, len(body), 4)]


def test_the_approach_stops_short_of_the_measured_contact():
    part = _part(50, 30, back_y=103.83)
    (line,) = _plan(part)
    moves = _push_block(part)

    # Up to the push height first, then in towards the part but not onto it.
    assert moves.index(next(move for move in moves if move.startswith("G1 Z"))) < moves.index(
        _approach(moves)
    )
    assert _approaches(moves) == [to_fixed(line.contact_y + ZPUSH_APPROACH_MM, 2)]


def test_the_approach_never_reaches_behind_the_bed():
    """A part at the back - or a long bumper offset - leaves no room to stop."""
    moves = _push_block(_part(50, 30, back_y=179.5))

    assert _approaches(moves) == [to_fixed(A1_MINI.y_forward, 2)]


def test_each_cycle_presses_swipes_and_comes_back():
    line = PushLine(x=50.0, z=21.0, contact_y=100.0, parts=(1,))
    moves = _push_block(_part(50, 30), lines=[line])

    first, *_ = _cycles(moves)
    start = line.contact_y + ZPUSH_APPROACH_MM
    pressed = start - ZPUSH_PRESS_MM
    swiped = pressed - ZPUSH_SWIPE_MM
    assert first == [
        f"G1 Y{pressed:.2f} F300",
        f"G1 Y{swiped:.2f} Z{line.z + ZPUSH_SWIPE_MM:.2f} F300",
        f"G1 Y{pressed:.2f} F300",
        f"G1 Z{line.z:.2f} F600",
    ]


def test_every_cycle_advances_by_the_press_distance():
    moves = _push_block(_part(50, 30))
    cycles = _cycles(moves)

    assert len(cycles) == ZPUSH_CYCLES
    pressed = [float(cycle[0].split()[1][1:]) for cycle in cycles]
    steps = [before - after for before, after in zip(pressed, pressed[1:])]
    assert steps == [pytest.approx(ZPUSH_PRESS_MM)] * (ZPUSH_CYCLES - 1)


def test_every_cycle_ends_at_the_height_it_started():
    """Z is only ever *up* inside a cycle, and back down at the same Y."""
    line = PushLine(x=50.0, z=21.0, contact_y=100.0, parts=(1,))
    moves = _push_block(_part(50, 30), lines=[line])

    for cycle in _cycles(moves):
        assert cycle[1].endswith(f"Z{line.z + ZPUSH_SWIPE_MM:.2f} F300")
        assert cycle[3] == f"G1 Z{line.z:.2f} F600"


def test_a_contact_near_the_front_edge_gets_fewer_cycles():
    """Better a short working-over than moves past the end of the push."""
    line = PushLine(x=50.0, z=21.0, contact_y=5.0, parts=(1,))
    moves = _push_block(_part(50, 30), lines=[line])
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


def test_a_line_with_no_contact_found_just_pushes():
    """Cycling needs somewhere to cycle; working the air is worse than a shove."""
    line = PushLine(x=50.0, z=21.0, contact_y=None, parts=(1,))
    moves = _push_block(_part(50, 30), lines=[line])

    assert not [move for move in moves if "short of the part" in move]
    assert len([move for move in moves if move.startswith("G1 Y-0.5")]) == 1


def test_a_plate_that_cannot_be_measured_says_so(trpaslik_project):
    """Its tall material misses the narrow band, so there is no contact to use."""
    project = ThreeMfProject.open(trpaslik_project)
    result = build_loops(
        project,
        detect_printer(project),
        LoopSettings(loops=1, cooldown_temp=26, zpush=True),
        source_name=trpaslik_project.name,
    )

    assert [line.contact_y for line in result.push_lines] == [None]
    assert any("nothing there to work loose" in warning for warning in result.warnings)
    assert "no plastic found under the bumper" in result.gcode


def test_the_push_still_finishes_at_the_plate_edge():
    moves = _push_block(_part(50, 30))

    pushes = [line for line in moves if line.startswith("G1 Y-0.5")]
    assert len(pushes) == 1
    # The push is the last thing the line does: then the bed comes back, the
    # blade drops to the travel height, and the plan tail readies the sweep.
    assert moves[-3:] == [
        "G1 Y180 F800\t; bed back along the band just swept, at the same height",
        "G1 Z0.20 F600\t; back to the travel height,"
        " at a point the nozzle has already been",
        "G1 Z1 F600\t\t;move nozzle closer to the bed for the sweep",
    ]
    assert moves[-4] == pushes[0]


def test_without_the_flag_the_push_is_one_straight_shove():
    moves = _push_block(_part(50, 30), zpush=False)

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
    parts = [_part(34, 50, back_y=90.0), _part(146, 10, back_y=60.0)]
    moves = _push_block(*parts)

    expected = [line.contact_y + ZPUSH_APPROACH_MM for line in _plan(*parts)]
    assert _approaches(moves) == [to_fixed(value, 2) for value in expected]
    assert len([line for line in moves if line.startswith("G1 Y-0.5")]) == len(parts)


def test_the_cone_plate_approaches_the_material_not_the_footprint(cone_multi_project):
    """Measured, a cone's contact sits well inside its own footprint."""
    body = split_gcode(ThreeMfProject.open(cone_multi_project).gcode).print_body
    parts = find_parts(body)
    measured = A1_MINI.push_plan(parts, body)
    moves = _push_block(*parts, lines=measured)

    assert _approaches(moves) == [
        to_fixed(line.contact_y + ZPUSH_APPROACH_MM, 2) for line in measured
    ]
    # Every cone is widest at its base, so each line ends up ahead of its box.
    bumper = A1_MINI.zpush_bumper_position
    for line in measured:
        back_edge = max(parts[number - 1].max_y for number in line.parts)
        assert line.contact_y < back_edge + bumper


def test_only_the_zpush_build_measures_the_contact(cone_multi_project):
    """The plain push works off the boxes, so it is not charged for the scan."""
    project = ThreeMfProject.open(cone_multi_project)
    profile = detect_printer(project)

    def contacts(zpush: bool) -> list[float | None]:
        result = build_loops(
            project,
            profile,
            LoopSettings(loops=1, cooldown_temp=26, zpush=zpush),
            source_name=cone_multi_project.name,
        )
        return [line.contact_y for line in result.push_lines]

    assert all(contact is None for contact in contacts(False))
    assert all(contact is not None for contact in contacts(True))


def test_the_plan_header_says_what_the_cycles_will_do():
    settings = LoopSettings(loops=1, cooldown_temp=23, zpush=True)
    code = A1_MINI.end_code(EndCodeContext(settings=settings, parts=(_part(50, 30),)))

    assert f"; {ZPUSH_CYCLES} press-and-swipe cycles" in code

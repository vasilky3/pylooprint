"""Planning the push: one line per part, or per group sharing an X band.

The blade sweeps a band of X when the bed drives forward, so a plate with
several parts needs several passes.  What has to hold:

* a part is only counted as pushed by a line within ``blade_width * overlap`` of
  its centre - 27.5 mm on the A1 Mini;
* a line comes down to the height of the *shortest* part it pushes, so the blade
  touches every one of them; and
* between lines the blade travels above everything still standing on the plate.
"""

from __future__ import annotations

import pytest

from pylooprint.core.parts import PartBounds, find_parts
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.push_plan import PUSH_CLEARANCE_MM, plan_push_lines
from pylooprint.core.structure import split_gcode
from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.a1_mini import BLADE_OVERLAP, BLADE_WIDTH, PUSH_MIN_Z
from pylooprint.printers.bedslinger import PUSH_PLAN_START
from pylooprint.settings import LoopSettings

A1_MINI = get_profile("a1mini")
REACH = BLADE_WIDTH * BLADE_OVERLAP


def _part(centre_x: float, top: float, *, width: float = 10.0) -> PartBounds:
    return PartBounds(centre_x - width / 2, centre_x + width / 2, 0.0, 10.0, 0.2, top)


def _plan(*parts: PartBounds, **overrides):
    settings = dict(
        blade_width=BLADE_WIDTH,
        overlap=BLADE_OVERLAP,
        height_factor=0.7,
        min_model_height=6.0,
        min_z=PUSH_MIN_Z,
    )
    settings.update(overrides)
    return plan_push_lines(parts, **settings)


def _end_code(parts=()) -> str:
    context = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=23), parts=tuple(parts))
    return A1_MINI.end_code(context)


def test_parts_within_reach_of_one_line_share_it():
    """Centres 34, 50, 90 and 146 with a 27.5 mm reach: three lines."""
    lines = _plan(_part(34, 20), _part(50, 20), _part(90, 20), _part(146, 20))

    assert [line.x for line in lines] == [42.0, 90.0, 146.0]
    assert [line.parts for line in lines] == [(1, 2), (3,), (4,)]


def test_the_reach_is_measured_from_the_line_to_each_centre():
    """Two reaches apart is the widest group one line can still cover."""
    assert len(_plan(_part(50, 20), _part(50 + 2 * REACH, 20))) == 1
    assert len(_plan(_part(50, 20), _part(50 + 2 * REACH + 0.01, 20))) == 2


def test_a_line_comes_down_to_the_shortest_part_it_pushes():
    """The blade has to touch every part of the group, so the low one decides."""
    (line,) = _plan(_part(50, 40), _part(60, 20))

    assert line.z == pytest.approx(14.0)  # 20 * 0.7, not 40 * 0.7
    assert line.parts == (1, 2)


def test_a_short_part_takes_the_nozzle_all_the_way_down():
    (line,) = _plan(_part(50, 4))

    assert line.z == PUSH_MIN_Z


def test_a_wide_part_still_gets_one_line_on_its_own_centre():
    """Wider than the blade is not a reason to push it twice."""
    (line,) = _plan(_part(90, 20, width=160))

    assert line.x == 90.0


def test_lines_run_left_to_right_whatever_order_the_parts_arrive_in():
    lines = _plan(_part(146, 20), _part(34, 20), _part(90, 20))

    assert [line.x for line in lines] == [34.0, 90.0, 146.0]
    # The numbering still points back at the parts as they were handed over.
    assert [line.parts for line in lines] == [(2,), (3,), (1,)]


def test_the_travel_height_clears_what_is_still_on_the_plate():
    """Parts leave left to right, so the lift needed drops as the plan runs."""
    lines = _plan(_part(34, 50), _part(90, 30), _part(146, 10))

    assert [line.safe_z for line in lines] == [
        50 + PUSH_CLEARANCE_MM,
        30 + PUSH_CLEARANCE_MM,
        10 + PUSH_CLEARANCE_MM,
    ]


def test_a_plate_with_nothing_on_it_has_no_plan():
    assert _plan() == []
    assert A1_MINI.push_plan([]) == []


def test_corexy_printers_plan_no_lines():
    """P1/X1 still push through the plate centre in three fixed lanes."""
    assert get_profile("p1").push_plan([_part(90, 20)]) == []


def test_the_cone_plate_is_pushed_in_two_passes(cone_multi_project):
    """Two of its four cones stand within one blade width of each other.

    Parts 1 and 2 are centred 36.75 mm apart, inside the 55 mm a single line
    spans, and part 1 is the shorter of them at 54.4 mm - so that line comes
    down to 38.08, not to 76.4 * 0.7.
    """
    body = split_gcode(ThreeMfProject.open(cone_multi_project).gcode).print_body
    lines = A1_MINI.push_plan(find_parts(body))

    assert len(lines) == 2
    assert (lines[0].x, lines[0].z) == pytest.approx((71.62, 38.08), abs=0.01)
    assert lines[0].parts == (1, 2)
    assert (lines[1].x, lines[1].z) == pytest.approx((145.99, 23.38), abs=0.01)
    assert lines[1].parts == (3,)


def test_the_end_code_runs_one_block_per_line():
    parts = [_part(34, 50), _part(146, 10)]
    code = _end_code(parts)

    assert code.count(PUSH_PLAN_START) == 1
    assert code.count("G1 Y-0.5 F300") == 2
    assert code.index("G0 X34.00") < code.index("G0 X146.00")
    assert "G1 Z35.00 F600" in code  # 50 * 0.7 for the first line
    assert "G1 Z7.00 F600" in code  # 10 * 0.7 for the second


def test_the_blade_lifts_before_the_bed_comes_back():
    """Otherwise it drags through whatever is still standing on the plate."""
    code = _end_code([_part(34, 50), _part(146, 10)])
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]

    moves = [line for line in block.split("\n") if line.startswith("G1 ")]
    returns = [index for index, line in enumerate(moves) if line.startswith("G1 Y180")]
    assert len(returns) == 2, "one bed return per push line"
    for index in returns:
        # 50 + 2 clears the tall part, 10 + 2 clears what is left after it.
        assert moves[index - 1].startswith(("G1 Z52.00", "G1 Z12.00"))


def test_without_parts_the_push_falls_back_to_one_line():
    """A body with nothing measurable in it still has to be ejected."""
    code = _end_code()

    assert PUSH_PLAN_START not in code
    assert "{first_layer_center_no_wipe_tower[0]}" in code
    assert code.count("G1 Y-0.5 F300") == 1

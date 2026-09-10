"""Planning the push: one line per part, or per group sharing an X band.

The blade sweeps a band of X when the bed drives forward, so a plate with
several parts needs several passes.  What has to hold:

* a part is only counted as pushed by a line within ``blade_width * overlap`` of
  its centre - 27.5 mm on the A1 Mini;
* a line pushes at the height of the *shortest* part it covers, so the blade
  touches every one of them; and
* the blade only ever descends at a point it has already been to, crossing the
  plate at the travel height instead - ``test_the_blade_never_descends_at_a_new_spot``
  is the one that pins that.
"""

from __future__ import annotations

import pytest

from pylooprint.core.jsnum import to_fixed
from pylooprint.core.parts import PartBounds, find_parts
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.push_plan import PushLine, measure_contact, plan_push_lines
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


def test_the_contact_y_is_the_back_edge_of_the_parts_on_the_line():
    """The bed carries a part towards the nozzle, so its far Y is met first."""
    near = PartBounds(30.0, 38.0, 10.0, 40.0, 0.2, 20.0)
    far = PartBounds(40.0, 48.0, 60.0, 95.0, 0.2, 20.0)

    (line,) = _plan(near, far)
    assert line.contact_y == 95.0


def _line(*, x: float = 50.0, z: float = 10.0, contact_y: float = 200.0) -> PushLine:
    return PushLine(x=x, z=z, contact_y=contact_y, parts=(1,))


def _wall(x: float, y: float, z: float, *, length: float = 4.0) -> str:
    """A short extruding move, laid along X at one spot on the plate."""
    return f"G0 X{x} Y{y} Z{z}\nG1 X{x + length} Y{y} E1"


def test_the_contact_is_measured_under_the_bumper():
    """A line at X50 reaches 27.5 mm either side of itself, and no further."""
    body = "\n".join([_wall(50, 120, 10), _wall(95, 160, 10)])

    (line,) = measure_contact(body, [_line()], reach=REACH)
    assert line.contact_y == 120.0


def test_a_narrower_overlap_narrows_the_band():
    """The same number the grouping uses, so the two cannot disagree."""
    body = _wall(65, 120, 10)

    assert measure_contact(body, [_line()], reach=REACH)[0].contact_y == 120.0
    assert measure_contact(body, [_line()], reach=REACH / 2)[0].contact_y == 200.0


def test_material_below_the_blade_passes_underneath_it():
    """Which is what the push height is for; at the height itself it counts."""
    assert measure_contact(_wall(50, 120, 9.9), [_line()], reach=REACH)[0].contact_y == 200.0
    assert measure_contact(_wall(50, 120, 10.0), [_line()], reach=REACH)[0].contact_y == 120.0


def test_a_diagonal_counts_only_where_it_crosses_the_band():
    """Its far end says nothing about what stands under the bumper."""
    body = "G0 X70 Y100 Z10\nG1 X120 Y160 E1"

    # The band ends at X77.5, a seventh of the way along: Y100 + 60 * 0.15.
    (line,) = measure_contact(body, [_line()], reach=REACH)
    assert line.contact_y == pytest.approx(109.0)


def test_a_neighbour_standing_in_the_band_is_what_the_blade_meets():
    """It is in the way whether or not this line is aimed at it."""
    body = "\n".join([_wall(50, 100, 10), _wall(75, 140, 10)])

    (line,) = measure_contact(body, [_line(contact_y=100.0)], reach=REACH)
    assert line.contact_y == 140.0


def test_an_empty_band_keeps_the_planned_contact():
    body = _wall(150, 170, 10)

    (line,) = measure_contact(body, [_line(contact_y=88.0)], reach=REACH)
    assert line.contact_y == 88.0
    assert measure_contact(body, [], reach=REACH) == []


def test_the_body_is_only_measured_when_it_is_handed_over(cone_multi_project):
    """The boxes answer well enough for the plain push, and cost nothing."""
    body = split_gcode(ThreeMfProject.open(cone_multi_project).gcode).print_body
    parts = find_parts(body)

    planned = A1_MINI.push_plan(parts)
    measured = A1_MINI.push_plan(parts, body)

    assert [to_fixed(line.contact_y, 2) for line in planned] == ["103.83", "60.42"]
    # A cone is widest at its base, so at 70% of its height its material stands
    # well short of the footprint's back edge.
    assert [to_fixed(line.contact_y, 2) for line in measured] == ["96.95", "42.73"]


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


def _walk(block: str) -> list[tuple[str, float, float, float]]:
    """Every move of a push block as ``(line, x, y, z)`` once it has run.

    The head arrives from the cool-down park: off the plate at X-13, bed forward,
    and down at Z1 where the in-place head template leaves it.
    """
    x, y, z = -13.0, 180.0, 1.0
    walked = []
    for line in block.split("\n"):
        if not (line.startswith("G0 ") or line.startswith("G1 ")):
            continue
        for word in line.split(";")[0].split():
            if word[0] in "XYZ":
                value = float(word[1:])
                x, y, z = (
                    value if word[0] == "X" else x,
                    value if word[0] == "Y" else y,
                    value if word[0] == "Z" else z,
                )
        walked.append((line, x, y, z))
    return walked


def test_the_blade_never_descends_at_a_new_spot():
    """Every drop happens where the nozzle has already been: the corner, or Y180.

    Coming down anywhere else means coming down blind onto whatever is under the
    blade, which on a plate of several parts is a part's top edge.
    """
    code = _end_code([_part(34, 50), _part(146, 10)])
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]

    previous_z = 1.0
    previous_x = -13.0
    for line, x, y, z in _walk(block):
        if z < previous_z:
            assert x == previous_x, f"descended after moving in X: {line!r}"
            assert y == A1_MINI.y_forward or x == -13.0, f"descended mid-plate: {line!r}"
        previous_x, previous_z = x, z


def test_the_blade_crosses_the_plate_at_the_travel_height():
    code = _end_code([_part(34, 50), _part(146, 10)])
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]

    crossings = [(line, z) for line, x, _, z in _walk(block) if line.startswith("G0 X")]
    assert len(crossings) == 2, "one crossing per push line"
    for line, z in crossings:
        assert z == PUSH_MIN_Z, f"crossed the plate at Z{z}: {line!r}"


def test_the_bed_comes_back_at_the_push_height_and_drops_only_then():
    """The return retraces the band just swept, so it needs no clearance."""
    code = _end_code([_part(34, 50), _part(146, 10)])
    block = code[code.index(PUSH_PLAN_START) : code.index("G1 Y135")]

    moves = [line for line, *_ in _walk(block)]
    returns = [index for index, line in enumerate(moves) if line.startswith("G1 Y180")]
    assert len(returns) == 2, "one bed return per push line"
    for index in returns:
        assert moves[index - 1].startswith("G1 Y-0.5")  # the push it retraces
        assert moves[index + 1].startswith(f"G1 Z{PUSH_MIN_Z:.2f}")


def test_without_parts_the_push_falls_back_to_one_line():
    """A body with nothing measurable in it still has to be ejected."""
    code = _end_code()

    assert PUSH_PLAN_START not in code
    assert "{first_layer_center_no_wipe_tower[0]}" in code
    assert code.count("G1 Y-0.5 F300") == 1

"""Finding the separate parts on a plate, and the box each one occupies.

The count is the headline number, so the cases that could get it wrong are the
ones pinned here: parts standing close together, the skirt that loops around
every one of them, and travel moves crossing the gaps between them.
"""

from __future__ import annotations

import pytest

from pylooprint.core.parts import PART_GAP_TOLERANCE, find_parts
from pylooprint.core.placement import measure_extrusion_bounds
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode


def _square(x: float, y: float, size: float, *, z: float = 0.2) -> list[str]:
    """A closed square of extruding moves, reached by a travel move."""
    corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    lines = [f"G0 X{corners[0][0]} Y{corners[0][1]} Z{z}"]
    lines += [f"G1 X{corner_x} Y{corner_y} E0.5" for corner_x, corner_y in corners[1:]]
    return lines


def _body(*blocks: list[str]) -> str:
    return "\n".join(line for block in blocks for line in block)


def _print_body(project_path) -> str:
    return split_gcode(ThreeMfProject.open(project_path).gcode).print_body


def test_squares_further_apart_than_the_tolerance_are_separate_parts():
    parts = find_parts(_body(_square(10, 10, 10), _square(28, 10, 10), _square(100, 100, 10)))

    assert len(parts) == 3
    assert [(part.min_x, part.max_x) for part in parts] == [(10, 20), (28, 38), (100, 110)]
    assert [(part.min_y, part.max_y) for part in parts] == [(10, 20), (10, 20), (100, 110)]


def test_squares_closer_than_the_tolerance_are_one_part():
    """A gap the nozzle could not print through is not a gap worth reporting."""
    parts = find_parts(_body(_square(10, 10, 10), _square(21, 10, 10)))

    assert len(parts) == 1
    assert (parts[0].min_x, parts[0].max_x) == (10, 31)


def test_the_tolerance_can_be_tightened():
    parts = find_parts(_body(_square(10, 10, 10), _square(21, 10, 10)), gap=0.5)

    assert len(parts) == 2


def test_the_skirt_does_not_fuse_the_plate_into_one_part():
    """The skirt is a single loop drawn around everything on the plate."""
    body = _body(
        ["; FEATURE: Skirt"],
        _square(5, 5, 45),
        ["; FEATURE: Outer wall"],
        _square(10, 10, 10),
        _square(28, 10, 10),
    )
    parts = find_parts(body)

    assert len(parts) == 2
    # The skirt is not part of a box either.
    assert parts[0].min_x == 10


def test_travel_moves_between_parts_are_not_printed_plastic():
    body = _body(
        _square(10, 10, 10),
        ["G0 X100 Y100 F12000"],
        _square(100, 100, 10),
    )
    parts = find_parts(body)

    assert len(parts) == 2
    assert (parts[0].max_x, parts[1].min_x) == (20, 100)


def test_the_top_z_follows_the_layer_change_lines():
    """The slicer raises Z on a line of its own, without moving X or Y."""
    body = _body(_square(10, 10, 10, z=0.2), ["G1 Z2.4"], _square(10, 10, 10, z=2.4))
    parts = find_parts(body)

    assert len(parts) == 1
    assert parts[0].min_z == 0.2
    assert parts[0].max_z == 2.4
    assert parts[0].height == pytest.approx(2.2)


def test_a_body_with_nothing_extruded_has_no_parts():
    assert find_parts("") == []
    assert find_parts("G0 X10 Y10 Z0.2\nG0 X50 Y50") == []


def test_a_circle_drawn_as_an_arc_is_measured_round():
    """With arc fitting on, a round wall is one ``G3`` whose ends nearly meet.

    Read as a straight move it would be a hairline, and the whole part would go
    missing from the count.
    """
    body = _body(["G0 X0 Y0 Z0.2", "G3 X0 Y0 I5 J0 E1"])
    parts = find_parts(body)

    assert len(parts) == 1
    assert (parts[0].min_x, parts[0].max_x) == pytest.approx((0.0, 10.0))
    assert (parts[0].min_y, parts[0].max_y) == pytest.approx((-5.0, 5.0))


def test_arcs_and_lines_of_one_part_stay_together():
    """A cone: an arc wall closed by the short straight stitch beside it."""
    body = _body(["G0 X0 Y0 Z0.2", "G3 X0.2 Y0 I5 J0 E1", "G1 X0 Y0 E0.01"])
    assert len(find_parts(body)) == 1


def test_the_cone_plate_counts_the_touching_cones_once(cone_multi_project):
    """Four slicer objects, two of them overlapping - three parts on the plate."""
    parts = find_parts(_print_body(cone_multi_project))

    assert len(parts) == 3
    # The merged pair spans both cones; the other two are round and 27.7 / 50.8
    # mm across, which is the footprint of the cone itself.
    assert (parts[0].width, parts[0].depth) == pytest.approx((88.7, 67.0), abs=0.1)
    assert (parts[1].width, parts[1].depth) == pytest.approx((27.7, 27.7), abs=0.1)
    assert (parts[2].width, parts[2].depth) == pytest.approx((50.8, 50.8), abs=0.1)


def test_the_cone_plate_tops_out_at_the_tallest_printed_layer(cone_multi_project):
    """``top Z`` is measured, not read from the header.

    This plate's header says ``max_z_height: 77.40``, but the tip of the tallest
    cone is too thin to print: the last layer that lays plastic is at Z76.4.
    """
    parts = find_parts(_print_body(cone_multi_project))

    assert max(part.max_z for part in parts) == 76.4


@pytest.mark.parametrize("fixture", ["suitable_project", "trpaslik_project"])
def test_a_single_object_plate_reports_one_part(fixture, request):
    """Both sample plates hold one part, so its box is the whole model's box."""
    body = _print_body(request.getfixturevalue(fixture))
    parts = find_parts(body)
    bounds = measure_extrusion_bounds(body)

    assert len(parts) == 1
    part = parts[0]
    assert (part.min_x, part.max_x) == pytest.approx((bounds.min_x, bounds.max_x))
    assert (part.min_y, part.max_y) == pytest.approx((bounds.min_y, bounds.max_y))


def test_the_part_reaches_the_model_height_from_the_header(suitable_project):
    """A flat-topped part is printed all the way up, so ``top Z`` is the height.

    Only for a flat top: a pointed one stops short of the header's figure, which
    is what ``test_the_cone_plate_tops_out_at_the_tallest_printed_layer`` shows.
    """
    gcode = ThreeMfProject.open(suitable_project).gcode
    parts = find_parts(split_gcode(gcode).print_body)

    assert parts[0].max_z == 180.0
    assert "; max_z_height: 180" in gcode


def test_the_default_tolerance_is_four_millimetres():
    assert PART_GAP_TOLERANCE == 4.0

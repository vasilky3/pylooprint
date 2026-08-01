"""A1 Mini: refuse to build when the model blocks the head-descent zone.

The push-off parks the nozzle off the plate at X-13 / Y180 and then drops the
toolhead to Z1.  The nozzle clears the plate, but the toolhead body overhangs
the back-left corner, so a model printed in ``X 0-15, Y 150-180`` is struck on
the way down.

Only material actually laid down in that corner counts.  The check used to
compare the plate's *bounding box* with the keep-out rectangle, which refused
good plates: a model reaching the left edge at the front and the back edge in
the middle has a box covering a corner it never touches.  ``GNOME`` below is
exactly that shape, taken off a real project.

The two cube fixtures come from the user's own projects and bracket the rule:
``cube180_fullfield`` covers the whole plate and must be refused,
``cube160h180_sutable`` is shifted right to clear the toolhead and must build.
"""

from __future__ import annotations

import zipfile

import pytest

from pylooprint.core.placement import ExtrusionBounds, measure_extrusion_bounds
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode
from pylooprint.errors import UnsafeEjectZoneError
from pylooprint.pipeline import build_loops
from pylooprint.printers import get_profile
from pylooprint.settings import LoopSettings

A1_MINI = get_profile("a1mini")


def _square(x0: float, x1: float, y0: float, y1: float, rows: int = 9, cols: int = 12) -> str:
    """A raster fill of the rectangle, the way infill actually covers one."""
    lines = []
    for row in range(rows):
        y = y0 + (y1 - y0) * row / (rows - 1)
        xs = [x0 + (x1 - x0) * col / (cols - 1) for col in range(cols)]
        if row % 2:
            xs.reverse()
        lines += [f"G1 X{x:.2f} Y{y:.2f} E0.05" for x in xs]
    return "\n".join(lines)


def _apart(*shapes: str) -> str:
    """Join filled shapes with a travel, so nothing extrudes between them."""
    return "\nG0 X90 Y90 F9000\n".join(shapes)


#: Footprints computed from the mesh and plate transform in each project's
#: ``3D/3dmodel.model``.
FULLFIELD = _square(0.00, 180.00, 0.00, 180.00)
SUITABLE = _square(19.88, 179.88, 0.00, 160.00)

#: The gnome-and-pumpkin plate: one lobe reaches X14 at the front, the other
#: reaches Y170 in the middle.  Their combined box covers the keep-out corner
#: while no material is anywhere near it.
GNOME = _apart(_square(14.03, 173.17, 7.84, 86.25), _square(52.82, 104.84, 150.00, 169.64))


# ---------------------------------------------------------------------------
# the rule itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("cube180_fullfield: covers the whole plate", FULLFIELD),
        ("fully inside the keep-out", _square(0.0, 15.0, 150.0, 180.0)),
        ("only a corner of the model intrudes", _square(5.0, 60.0, 140.0, 175.0)),
        # Both ends sit outside the corner, but the line runs through it.  An
        # endpoint-only test would wave this one through.
        ("a single line crossing the corner", "G1 X20 Y152 E0.1\nG1 X5 Y148 E0.5"),
    ],
)
def test_model_in_the_keep_out_zone_is_refused(label, body):
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance(body)
    assert "Model cannot be ejected" in str(excinfo.value)


@pytest.mark.parametrize(
    ("label", "body"),
    [
        # The regression this check was rewritten for.
        ("gnome plate: box covers the corner, material does not", GNOME),
        # Reaches Y160, inside the keep-out Y band, but starts right of X15.
        ("cube160h180_sutable: clears the corner in X", SUITABLE),
        ("reaches the back but not the left", _square(86.0, 164.0, 85.0, 175.0)),
        ("reaches the left but not the back", _square(0.0, 15.0, 0.0, 100.0)),
        ("touching the corner without overlapping", _square(15.0, 60.0, 60.0, 150.0)),
        # Clips the corner point exactly, entering no part of the interior.
        ("a line grazing the corner vertex", "G1 X20 Y155 E0.1\nG1 X10 Y145 E0.5"),
        ("well clear of it", _square(60.0, 160.0, 60.0, 160.0)),
    ],
)
def test_model_clear_of_the_keep_out_zone_is_accepted(label, body):
    A1_MINI.check_eject_clearance(body)


def test_an_unmeasurable_model_is_refused():
    """Unknown is treated as unsafe rather than assumed clear."""
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance("; CHANGE_LAYER\nG1 X10 Y10 F600\n")
    assert "could not be verified" in str(excinfo.value)


def test_the_error_names_the_zone_and_where_the_model_intrudes():
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance(_square(5.0, 60.0, 140.0, 175.0))
    message = str(excinfo.value)
    assert "X 0.0-15.0, Y 150.0-180.0 mm" in message
    assert "the model prints inside it, at X " in message
    assert "re-slice" in message


@pytest.mark.parametrize("key", ["p1", "x1", "a1"])
def test_other_printers_do_not_apply_the_check(key):
    """Only the A1 Mini brings the toolhead down onto the plate."""
    get_profile(key).check_eject_clearance(FULLFIELD)
    get_profile(key).check_eject_clearance("")


# ---------------------------------------------------------------------------
# measuring the model
# ---------------------------------------------------------------------------
def test_bounds_are_measured_from_the_print_body(golden_project):
    structure = split_gcode(ThreeMfProject.open(golden_project).gcode)
    bounds = measure_extrusion_bounds(structure.print_body)
    assert (round(bounds.min_x, 2), round(bounds.max_x, 2)) == (86.21, 163.73)
    assert (round(bounds.min_y, 2), round(bounds.max_y, 2)) == (85.35, 164.63)


def test_bounds_are_none_when_nothing_extrudes():
    assert measure_extrusion_bounds("; CHANGE_LAYER\nG1 X10 Y10 F600\nG1 Z5\n") is None
    assert measure_extrusion_bounds("") is None


def test_travel_and_retraction_moves_are_not_model():
    body = (
        "; CHANGE_LAYER\n"
        "G1 X0.5 Y179 F9000\n"       # travel into the corner, no extrusion
        "G1 E-0.8 F1800\n"           # retract, no position
        "G1 X100 Y100 E0.5 F1200\n"  # the only real model move
    )
    bounds = measure_extrusion_bounds(body)
    assert bounds == ExtrusionBounds(100.0, 100.0, 100.0, 100.0)


def test_extruding_away_from_a_travel_inside_the_corner_still_counts():
    """The travel lays nothing, but the move leaving it draws from that point."""
    body = "; CHANGE_LAYER\nG1 X5 Y170 F9000\nG1 X100 Y100 E0.5 F1200\n"
    with pytest.raises(UnsafeEjectZoneError):
        A1_MINI.check_eject_clearance(body)


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------
def _plate_3mf(path, print_body: str):
    """Minimal sliced-plate container - all the eject check needs."""
    plate = (
        "; HEADER_BLOCK_START\n; max_z_height: 20.00\n; HEADER_BLOCK_END\n"
        "; CONFIG_BLOCK_START\n; nozzle_temperature_initial_layer = 220\n; CONFIG_BLOCK_END\n"
        "; EXECUTABLE_BLOCK_START\nM73 P0\n; FEATURE: Custom\nT0\nM109 S220\n"
        "; CHANGE_LAYER\n" + print_body + "\n"
        ";===== date: 20240101 =====\nM104 S0\n; EXECUTABLE_BLOCK_END\n"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/plate_1.gcode", plate)
    return path


def test_pipeline_refuses_a_model_in_the_corner(tmp_path):
    """Proves the check is actually wired into build_loops."""
    source = _plate_3mf(tmp_path / "corner.gcode.3mf", _square(2.0, 40.0, 155.0, 178.0))
    project = ThreeMfProject.open(source)
    with pytest.raises(UnsafeEjectZoneError):
        build_loops(project, A1_MINI, LoopSettings(loops=1), source_name=source.name)


def test_the_gnome_plate_survives_the_split_the_pipeline_hands_over(tmp_path):
    """The regression on the body ``build_loops`` actually passes to the check.

    It stops here rather than running the whole build, because the minimal
    container has none of the start-code anchors the A1 Mini patches.
    """
    source = _plate_3mf(tmp_path / "gnome.gcode.3mf", GNOME)
    structure = split_gcode(ThreeMfProject.open(source).gcode)
    A1_MINI.check_eject_clearance(structure.print_body)


def test_pipeline_accepts_a_model_clear_of_the_corner(golden_project):
    """The real sample reaches Y164.6 - past Y150 - but starts at X86."""
    project = ThreeMfProject.open(golden_project)
    result = build_loops(project, A1_MINI, LoopSettings(loops=1, cooldown_temp=28), source_name="x.3mf")
    assert result.gcode


# --- the user's own projects, once sliced -----------------------------------
def test_fullfield_cube_is_refused(fullfield_project):
    project = ThreeMfProject.open(fullfield_project)
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        build_loops(project, A1_MINI, LoopSettings(loops=1), source_name=fullfield_project.name)
    assert "safe head-descent zone is occupied" in str(excinfo.value)


def test_suitable_cube_is_accepted(suitable_project):
    project = ThreeMfProject.open(suitable_project)
    result = build_loops(
        project, A1_MINI, LoopSettings(loops=1, cooldown_temp=28), source_name=suitable_project.name
    )
    assert result.gcode


def test_trpaslik_plate_is_accepted(trpaslik_project):
    """The real plate the bounding-box check used to refuse.

    Its box genuinely covers the keep-out corner - that is asserted here, so the
    test still means something if anyone reaches for a bounding box again - but
    the material above Y150 sits at X53-105, nowhere near it.
    """
    project = ThreeMfProject.open(trpaslik_project)
    body = split_gcode(project.gcode).print_body

    bounds = measure_extrusion_bounds(body)
    assert bounds.overlaps(0.0, 15.0, 150.0, 180.0), "the box no longer spans the corner"

    result = build_loops(
        project, A1_MINI, LoopSettings(loops=1, cooldown_temp=28), source_name=trpaslik_project.name
    )
    assert result.gcode

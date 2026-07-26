"""A1 Mini: refuse to build when the model blocks the head-descent zone.

The push-off parks the nozzle off the plate at X-13 / Y180 and then drops the
toolhead to Z1.  The nozzle clears the plate, but the toolhead body overhangs
the back-left corner, so a model printed in ``X 0-15, Y 150-180`` is struck on
the way down.

The two cube fixtures come from the user's own projects and bracket the rule:
``cube180_fullfield`` covers the whole plate and must be refused,
``cube160h180_sutable`` is shifted right to clear the toolhead and must build.
Their footprints are also used directly as unit-test data, so the rule is
pinned even before the projects have been sliced.
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

#: Plate footprints computed from the mesh and plate transform in each project's
#: ``3D/3dmodel.model``.
FULLFIELD_BOUNDS = ExtrusionBounds(min_x=0.00, max_x=180.00, min_y=0.00, max_y=180.00)
SUITABLE_BOUNDS = ExtrusionBounds(min_x=19.88, max_x=179.88, min_y=0.00, max_y=160.00)

A1_MINI = get_profile("a1mini")


# ---------------------------------------------------------------------------
# the rule itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "bounds"),
    [
        ("cube180_fullfield: covers the whole plate", FULLFIELD_BOUNDS),
        ("fully inside the keep-out", ExtrusionBounds(0.0, 15.0, 150.0, 180.0)),
        # The heuristic detector reports the fallback for this one, which is why
        # the check measures the print body instead.
        ("only a corner of the model intrudes", ExtrusionBounds(5.0, 60.0, 140.0, 175.0)),
    ],
)
def test_model_in_the_keep_out_zone_is_refused(label, bounds):
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance(bounds)
    assert "Model cannot be ejected" in str(excinfo.value)


@pytest.mark.parametrize(
    ("label", "bounds"),
    [
        # Reaches Y160, inside the keep-out Y band, but starts right of X15.
        # An OR instead of an AND would wrongly reject the user's good file.
        ("cube160h180_sutable: clears the corner in X", SUITABLE_BOUNDS),
        ("reaches the back but not the left", ExtrusionBounds(86.0, 164.0, 85.0, 175.0)),
        ("reaches the left but not the back", ExtrusionBounds(0.0, 15.0, 0.0, 100.0)),
        ("touching the corner without overlapping", ExtrusionBounds(15.0, 60.0, 60.0, 150.0)),
        ("well clear of it", ExtrusionBounds(60.0, 160.0, 60.0, 160.0)),
    ],
)
def test_model_clear_of_the_keep_out_zone_is_accepted(label, bounds):
    A1_MINI.check_eject_clearance(bounds)


def test_an_unmeasurable_model_is_refused():
    """Unknown is treated as unsafe rather than assumed clear."""
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance(None)
    assert "could not be verified" in str(excinfo.value)


def test_the_error_names_the_zone_and_the_model():
    with pytest.raises(UnsafeEjectZoneError) as excinfo:
        A1_MINI.check_eject_clearance(ExtrusionBounds(5.0, 60.0, 140.0, 175.0))
    message = str(excinfo.value)
    assert "X 0.0-15.0, Y 150.0-180.0 mm" in message
    assert "X 5.00-60.00, Y 140.00-175.00 mm" in message
    assert "re-slice" in message


@pytest.mark.parametrize("key", ["p1", "x1", "a1"])
def test_other_printers_do_not_apply_the_check(key):
    """Only the A1 Mini brings the toolhead down onto the plate."""
    get_profile(key).check_eject_clearance(FULLFIELD_BOUNDS)
    get_profile(key).check_eject_clearance(None)


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


def _square(x0: float, x1: float, y0: float, y1: float) -> str:
    return "\n".join(
        f"G1 X{x0 + (x1 - x0) * (i % 8) / 7:.2f} Y{y0 + (y1 - y0) * (i % 5) / 4:.2f} E0.05"
        for i in range(60)
    )


def test_pipeline_refuses_a_model_in_the_corner(tmp_path):
    """Proves the check is actually wired into build_loops."""
    source = _plate_3mf(tmp_path / "corner.gcode.3mf", _square(2.0, 40.0, 155.0, 178.0))
    project = ThreeMfProject.open(source)
    with pytest.raises(UnsafeEjectZoneError):
        build_loops(project, A1_MINI, LoopSettings(loops=1), source_name=source.name)


def test_pipeline_accepts_a_model_clear_of_the_corner(golden_project):
    """The real sample reaches Y164.6 - past Y150 - but starts at X86."""
    project = ThreeMfProject.open(golden_project)
    result = build_loops(project, A1_MINI, LoopSettings(loops=1, cooldown_temp=28), source_name="x.3mf")
    assert result.gcode


# --- the user's own cube projects, once sliced ------------------------------
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

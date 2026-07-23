"""Equivalence with the original Looprint web tool, for the A1 Mini.

``2b_LP.gcode`` was produced by the JavaScript tool from ``2b_base.gcode``
(1 loop, 58 degree cool-down).  Reproducing it byte for byte pins down the whole
pipeline: end-code stripping, the start/end templates, variable substitution,
placement detection and the loop assembly.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone

from pylooprint.core.placement import determine_model_placement
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode, strip_slicer_end_code
from pylooprint.core.template import centre_coordinates, resolve_max_layer_z, substitute_first_layer_centre
from pylooprint.core.variables import extract_variable_values
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.settings import LoopSettings

from conftest import GOLDEN_LOOPS, GOLDEN_TEMP

#: The timestamp recorded in the golden file's banner.
GOLDEN_STAMP = datetime(2026, 7, 8, 12, 44, 25, 740000, tzinfo=timezone.utc)


def _build(project_path, **overrides):
    project = ThreeMfProject.open(project_path)
    profile = detect_printer(project)
    settings = LoopSettings(loops=GOLDEN_LOOPS, cooldown_temp=GOLDEN_TEMP, **overrides)
    return project, build_loops(
        project,
        profile,
        settings,
        source_name="test 2 blocks.gcode.3mf",
        generated_at=GOLDEN_STAMP,
    )


def test_printer_is_detected_from_plate_metadata(golden_project):
    assert detect_printer(ThreeMfProject.open(golden_project)).key == "a1mini"


def test_output_matches_the_web_tool_byte_for_byte(golden_project, golden_expected):
    _, result = _build(golden_project)
    assert result.gcode == golden_expected


def test_model_placement_matches_the_web_tool(golden_project):
    _, result = _build(golden_project)
    # The A1 Mini push-off aligns to this centre; the golden file says X124.97 Y124.99.
    assert round((result.placement.min_x + result.placement.max_x) / 2, 2) == 124.97
    assert round((result.placement.min_y + result.placement.max_y) / 2, 2) == 124.99


def test_model_height_comes_from_the_header(golden_project):
    _, result = _build(golden_project)
    assert result.max_layer_z_from_header
    assert result.max_layer_z == 18.12


def test_end_code_matches_the_one_embedded_in_result_3mf(result_3mf):
    """``result.gcode.3mf`` carries a Looprint A1 Mini end code for 58 degrees."""
    gcode = zipfile.ZipFile(result_3mf).read("Metadata/plate_1.gcode").decode("utf-8")
    expected = gcode[gcode.index(";===== A1 Mini PRESET") : gcode.index("; >>> END OF PRINT LOOPS <<<")]
    expected = expected.rstrip("\n")

    profile = get_profile("a1mini")
    structure = split_gcode(strip_slicer_end_code(gcode))
    bed = profile.bed_bounds
    placement = determine_model_placement(gcode, bed.min_x, bed.max_x, bed.min_y, bed.max_y)
    values = extract_variable_values(gcode, structure.config, placement.as_bounds())
    centre_x, centre_y = centre_coordinates(values["first_layer_center_no_wipe_tower"])

    context = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=GOLDEN_TEMP))
    produced = substitute_first_layer_centre(profile.end_code(context), centre_x, centre_y)
    produced = resolve_max_layer_z(produced, 18.12)

    assert produced == expected

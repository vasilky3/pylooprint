"""The Factorian fallback, used for printers without an in-place implementation.

Every profile except the A1 Mini falls back to Factorian Designs' start/end
templates - the same logic the original web tool uses - until an in-place
implementation is added for it.  Two things are pinned here:

* the bed-slinger end code is a faithful port (compared against a real looped
  A1 Mini file), and
* an unsupported printer actually takes the fallback path and says so.
"""

from __future__ import annotations

import zipfile

import pytest

from pylooprint.core.placement import determine_model_placement
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode
from pylooprint.core.template import centre_coordinates, resolve_max_layer_z, substitute_first_layer_centre
from pylooprint.core.variables import extract_variable_values
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.printers import EndCodeContext, PrinterProfile, get_profile
from pylooprint.settings import LoopSettings

from conftest import GOLDEN_TEMP


def test_bedslinger_end_code_matches_a_real_looped_file(result_3mf):
    """``result.gcode.3mf`` embeds a Looprint A1 Mini end code for 58 degrees."""
    gcode = zipfile.ZipFile(result_3mf).read("Metadata/plate_1.gcode").decode("utf-8")
    expected = gcode[gcode.index(";===== A1 Mini PRESET") : gcode.index("; >>> END OF PRINT LOOPS <<<")]
    expected = expected.rstrip("\n")

    profile = get_profile("a1mini")
    structure = split_gcode(gcode)
    bed = profile.bed_bounds
    placement = determine_model_placement(gcode, bed.min_x, bed.max_x, bed.min_y, bed.max_y)
    values = extract_variable_values(gcode, structure.config, placement.as_bounds())
    centre_x, centre_y = centre_coordinates(values["first_layer_center_no_wipe_tower"])

    context = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=GOLDEN_TEMP))
    produced = substitute_first_layer_centre(profile.end_code(context), centre_x, centre_y)
    produced = resolve_max_layer_z(produced, 18.12)

    assert produced == expected


def test_unsupported_printer_takes_the_fallback_and_warns(result_3mf):
    """A CoreXY profile has no in-place patches yet, so it uses Factorian's."""
    project = ThreeMfProject.open(result_3mf)
    result = build_loops(
        project,
        get_profile("p1"),
        LoopSettings(loops=1, cooldown_temp=18),
        source_name=result_3mf.name,
        force=True,
    )
    assert any("no in-place machine G-code" in w for w in result.warnings)
    assert "; --- PUSH LANE 1: CENTER" in result.gcode


def test_a1_mini_does_not_take_the_fallback(golden_project):
    """The one printer with an in-place implementation must not warn."""
    project = ThreeMfProject.open(golden_project)
    result = build_loops(
        project, detect_printer(project), LoopSettings(loops=1, cooldown_temp=28), source_name="x.3mf"
    )
    assert not any("no in-place" in w for w in result.warnings)


@pytest.mark.parametrize("key", ["p1", "x1", "a1"])
def test_profiles_awaiting_an_inplace_port_use_the_default(key):
    """Not overriding ``build_machine_code`` is what selects the fallback.

    Porting a printer means overriding that one method - there is no flag to
    keep in step with it.
    """
    assert type(get_profile(key)).build_machine_code is PrinterProfile.build_machine_code
    assert type(get_profile("a1mini")).build_machine_code is not PrinterProfile.build_machine_code

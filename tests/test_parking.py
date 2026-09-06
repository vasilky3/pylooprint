"""Parking the head where an ordinary print of the same plate leaves it.

The slicer's end code lifts clear of the part and parks - on the A1 Mini at
X-13 / Y180, having raised Z to the part's height plus 100 mm.  Looping replaces
that whole stretch with the eject sequence, so the moves are read back out of
the file and replayed after the last copy is off the plate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pylooprint.core.parking import PARK_AFTER, SlicerPark, lift_moves, read_slicer_park
from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.printers import EndCodeContext, get_profile
from pylooprint.printers.bedslinger import PARK_END, PARK_START
from pylooprint.settings import LoopSettings

#: The shape of a Bambu end code, down to the indentation of the lift.
END_CODE = """M400 ; wait all motion done
M17 S
M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom

    G1 Z141 F600
    G1 Z139

M400 P100
M17 R ; restore z current

G90
G1 X-13 Y180 F3600

G91
G1 Z-1 F600
G90
M83

M220 S100  ; Reset feedrate magnitude
M201.2 K1.0 ; Reset acc magnitude
"""


def _build(project_path: Path, loops: int = 1):
    project = ThreeMfProject.open(project_path)
    return build_loops(
        project,
        detect_printer(project),
        LoopSettings(loops=loops, cooldown_temp=26),
        source_name=project_path.name,
    ).gcode


def _park_block(gcode: str) -> str:
    return gcode[gcode.index(PARK_START) : gcode.index(PARK_END) + len(PARK_END)]


def test_the_lift_and_the_park_are_read_out_of_the_end_code():
    park = read_slicer_park(END_CODE)

    assert park.lift == "G1 Z141 F600\nG1 Z139"
    assert park.moves == "G90\nG1 X-13 Y180 F3600\nG91\nG1 Z-1 F600\nG90\nM83"


def test_the_lift_is_de_indented():
    """It sits in an ``{if}`` block in the template; the block is gone here."""
    assert not any(line.startswith(" ") for line in lift_moves(END_CODE).split("\n"))


def test_an_end_code_without_a_park_reads_as_none():
    """Better no park than a guessed one on a machine shaped differently."""
    assert read_slicer_park("G28\nM104 S0\n") is None
    assert read_slicer_park(END_CODE[: END_CODE.index(PARK_AFTER)]) is None


def test_a_park_with_nothing_to_lift_still_parks():
    without_lift = END_CODE[END_CODE.index(PARK_AFTER) :]
    park = read_slicer_park(without_lift)

    assert park.lift == ""
    assert park.moves.startswith("G90\nG1 X-13 Y180 F3600")


@pytest.mark.parametrize("loops", [1, 2, 3])
def test_only_the_last_copy_parks(cone_multi_project, loops):
    gcode = _build(cone_multi_project, loops)

    assert gcode.count(PARK_START) == 1
    # Everything before the park is the earlier loops; nothing comes after it
    # but the last loop's own reset tail.
    assert gcode.count("; >>> LOOP ", 0, gcode.index(PARK_START)) == loops


def test_the_park_carries_the_slicer_s_own_numbers(cone_multi_project):
    """The height follows the part - 76.4 mm printed, so the lift is Z176.4."""
    block = _park_block(_build(cone_multi_project))

    assert "G1 Z176.4 F600" in block
    assert "G1 X-13 Y180 F3600" in block
    assert "M83" in block


def test_the_lift_comes_before_the_relative_drop(cone_multi_project):
    """The sweep ends at Z1, where a relative ``G1 Z-1`` would hit the plate."""
    block = _park_block(_build(cone_multi_project))
    lines = [line for line in block.split("\n") if not line.startswith(";")]

    assert lines.index("G1 Z176.4 F600") < lines.index("G91") < lines.index("G1 Z-1 F600")


def test_the_park_runs_after_the_sweep_and_before_the_finish_sound(cone_multi_project):
    gcode = _build(cone_multi_project)

    assert gcode.rindex("G1 Y185 F2000 ;move bed forward one last time") < gcode.index(PARK_START)
    # The motors are still holding here: the sound block ends with the M18 that
    # drops them, so the park has to be in front of it.
    assert gcode.index(PARK_END) < gcode.rindex(";=====printer finish  sound=========")
    assert gcode.index(PARK_END) < gcode.rindex("M18 X Y Z")


def test_the_park_height_follows_the_plate(suitable_project):
    """A 180 mm part is already at the ceiling, so the slicer lifts to Z180."""
    block = _park_block(_build(suitable_project))

    assert "G1 Z180 F600" in block


def test_the_template_path_parks_too():
    """The A1 has no in-place patches yet, but its end code still parks."""
    park = SlicerPark(lift="G1 Z131.8 F600", moves="G90\nG1 X-48 Y262 F3600\nM83")
    settings = LoopSettings(loops=1, cooldown_temp=23)
    profile = get_profile("a1")

    parked = profile.final_end_code(EndCodeContext(settings=settings, slicer_park=park))
    assert "G1 X-48 Y262 F3600" in parked
    assert parked.index(PARK_START) < parked.index(";=====printer finish  sound=========")


def test_without_a_park_the_last_loop_ends_like_the_others():
    settings = LoopSettings(loops=1, cooldown_temp=23)
    profile = get_profile("a1mini")
    context = EndCodeContext(settings=settings)

    assert profile.final_end_code(context) is None
    assert PARK_START not in profile.end_code(context)


def test_the_park_is_not_in_the_other_loops(cone_multi_project):
    """The copies before the last one end exactly as they always did."""
    gcode = _build(cone_multi_project, 3)
    first_loop = gcode[gcode.index("; >>> LOOP 1 / 3") : gcode.index("; >>> LOOP 2 / 3")]

    assert PARK_START not in first_loop
    assert "G1 Y185 F2000 ;move bed forward one last time" in first_loop


def test_the_slicer_park_is_read_from_the_plate_being_built(cone_multi_project):
    """The pipeline hands the profile what this very file would have done."""
    end_code = split_gcode(ThreeMfProject.open(cone_multi_project).gcode).slicer_end_code

    assert read_slicer_park(end_code).lift == "G1 Z176.4 F600\nG1 Z174.4"

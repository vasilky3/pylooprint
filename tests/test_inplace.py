"""The default ``inplace`` strategy, for the A1 Mini.

Reference: ``Gcode/test 2 blocks gcode/test 2 blocks mymod/Metadata/plate_1.gcode``
- the slicer output in ``test 2 blocks/`` with the purge lines turned into air
purges and the eject sequence spliced into the machine end code by hand.

pylooprint has to produce the same *machine G-code* from the same slicer output.
It does not reproduce the reference file byte for byte, because the loops are
assembled by the same code the Factorian strategy uses: that adds the Looprint
banner, the per-loop markers and Looprint's speed handling around the machine
G-code.  These tests therefore compare the machine start and end code, which is
where all the modifications live.
"""

from __future__ import annotations

import re

import pytest

from pylooprint.core.constants import END_CODE_START_MARKER, FEATURE_CUSTOM
from pylooprint.core.patching import PatchError
from pylooprint.core.project import ThreeMfProject
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.printers import get_profile
from pylooprint.settings import LoopSettings

from conftest import INPLACE_TEMP, with_current_push_block, without_release_hold

_EXECUTABLE_END = "; EXECUTABLE_BLOCK_END"
#: The loop assembler appends this after the start code; the reference file,
#: being a single hand-made copy, has no loop scaffolding.
_SPEED_SCAFFOLD_RE = re.compile(r"\n+M220 S\d+ ; Set speed mode\s*$")


def _build(project_path, loops=1, **overrides):
    project = ThreeMfProject.open(project_path)
    settings = LoopSettings(loops=loops, cooldown_temp=INPLACE_TEMP, **overrides)
    return build_loops(
        project, detect_printer(project), settings, source_name="test 2 blocks.gcode.3mf"
    )


def _machine_start_code(gcode: str) -> str:
    """Everything between ``; FEATURE: Custom`` and the first layer."""
    start = gcode.index(FEATURE_CUSTOM, gcode.index("; EXECUTABLE_BLOCK_START")) + len(FEATURE_CUSTOM)
    block = gcode[start : gcode.index("; CHANGE_LAYER", start)].strip()
    return _SPEED_SCAFFOLD_RE.sub("", block)


def _machine_end_code(gcode: str) -> str:
    """The machine end code, up to the end of the executable block."""
    start = gcode.rindex(END_CODE_START_MARKER, 0, gcode.index(_EXECUTABLE_END))
    return gcode[start : gcode.index(_EXECUTABLE_END, start) + len(_EXECUTABLE_END)]


def test_one_copy_is_the_default():
    assert LoopSettings().loops == 1


def test_printer_and_model_are_detected(golden_project):
    result = _build(golden_project)
    assert result.profile.key == "a1mini"
    assert result.max_layer_z_from_header
    assert result.max_layer_z == 18.12
    # The A1 Mini push-off aligns to this centre (X124.97 / Y124.99 in the file).
    assert round((result.placement.min_x + result.placement.max_x) / 2, 2) == 124.97


def test_machine_end_code_matches_the_reference(golden_project, inplace_reference):
    """The cool-down, push-off and sweep are the reference file's, byte for byte.

    Apart from two blocks: the reference predates the 70% Z-drop rule and the
    comments that came with it, and it knows nothing about the hold and the
    push-off beep, which ``test_release_hold.py`` pins instead.
    """
    produced = _build(golden_project).gcode
    expected = with_current_push_block(_machine_end_code(inplace_reference))
    assert without_release_hold(_machine_end_code(produced)) == without_release_hold(expected)


def test_machine_start_code_matches_the_reference(golden_project, inplace_reference):
    """The patched start code is the reference file's, apart from Looprint's marker."""
    produced = _machine_start_code(_build(golden_project).gcode)
    expected = _machine_start_code(inplace_reference)
    # Looprint tags the feedrate reset it owns; the hand-made reference has no tag.
    assert produced.replace(" ;Reset Feedrate (Looprint: 100% speed)", " ;Reset Feedrate") == expected


def test_the_print_itself_is_untouched(golden_project, inplace_reference):
    start = inplace_reference.index("; CHANGE_LAYER")
    end = inplace_reference.rindex(END_CODE_START_MARKER)
    expected = inplace_reference[start:end].strip()
    assert expected in _build(golden_project).gcode


def test_slicer_start_code_is_kept(golden_project):
    """Unlike the Factorian strategy, the machine start code survives."""
    gcode = _build(golden_project).gcode
    assert "M983 F8.39793 A0.3 H0.4; cali dynamic extrusion compensation" in gcode
    assert "; build plate detect" in gcode
    assert "FactorianDesigns" not in gcode


def test_purge_lines_become_air_purges(golden_project):
    gcode = _build(golden_project).gcode
    assert gcode.count("G0 E50 F100") == 2
    body = gcode[gcode.index("; EXECUTABLE_BLOCK_START") :]
    # The line that used to be drawn across the front of the plate is gone.
    assert "G0 X88 E10" not in body
    assert "G0 X113 E.3742" not in body


def test_slicer_end_code_is_kept_around_the_eject_sequence(golden_project):
    gcode = _build(golden_project).gcode
    body = gcode[gcode.index("; EXECUTABLE_BLOCK_START") :]
    # kept: the slicer's timelapse block, filament unload and finish sound
    assert "M991 S0 P-1 ;end timelapse at safe pos" in body
    assert "; pull back filament to AMS" in body
    assert ";=====printer finish  sound=========" in body
    # spliced in: cool down, push off, sweep
    assert body.count("M190 S24") == 50
    assert "G1 Y-0.5 F300" in body
    assert ";====== Safety clear complete =======" in body


def test_align_move_is_slow(golden_project):
    """The in-place strategy crawls to the model centre instead of a rapid."""
    gcode = _build(golden_project).gcode
    assert "F300 ; Align nozzle with model center for push" in gcode
    assert "F12000 ; Align nozzle with model center for push" not in gcode


def test_slicer_z_lift_is_carried_over(golden_project):
    gcode = _build(golden_project).gcode
    # max_z_height is 18.12, so the slicer lifted to +100 / +98.
    assert "\nG1 Z118.12 F600\nG1 Z116.12\n" in gcode


@pytest.mark.parametrize("loops", [1, 2, 4])
def test_each_loop_repeats_the_whole_plate(golden_project, loops):
    gcode = _build(golden_project, loops).gcode
    for index in range(1, loops + 1):
        assert gcode.count(f"; >>> LOOP {index} / {loops} <<<") == 1
    assert gcode.count("; EXECUTABLE_BLOCK_START") == loops
    assert gcode.count("G1 Y-0.5 F300") == loops
    assert gcode.count("G0 E50 F100") == 2 * loops
    # Header and settings dump only once.
    assert gcode.count("; HEADER_BLOCK_START") == 1
    assert gcode.count("; CONFIG_BLOCK_START") == 1
    assert gcode.count("M400 ; Looprint safety: Wait for buffer clear before next loop") == loops - 1


def test_a_missing_anchor_is_reported_not_ignored():
    profile = get_profile("a1mini")
    with pytest.raises(PatchError):
        profile.start_code_patches()[0].apply("G28\nG1 X10 Y10\n")

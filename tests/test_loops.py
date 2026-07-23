"""Multi-loop assembly, using the file the user supplied for testing.

``result.gcode.3mf`` already carries a Looprint marker, so it only goes through
the pipeline with ``force=True`` - which is exactly what makes it a useful test
of the "strip whatever end code is there and re-wrap it" behaviour.

Counting has to skip the ``CONFIG_BLOCK``: the slicer stores the machine start
and end G-code there as escaped one-liners, so markers such as
``;===== machine: A1 mini`` occur inside it as data.
"""

from __future__ import annotations

import pytest

from pylooprint.core.constants import CONFIG_BLOCK_END
from pylooprint.core.project import ThreeMfProject
from pylooprint.errors import AlreadyLoopedError
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.settings import LoopSettings


def _build(path, loops, **overrides):
    project = ThreeMfProject.open(path)
    profile = detect_printer(project)
    settings = LoopSettings(loops=loops, cooldown_temp=18, **overrides)
    return build_loops(project, profile, settings, source_name=path.name, force=True)


def _executable_part(gcode: str) -> str:
    """Everything after the slicer's settings dump."""
    return gcode[gcode.index(CONFIG_BLOCK_END) + len(CONFIG_BLOCK_END) :]


def test_already_looped_input_is_refused_without_force(result_3mf):
    project = ThreeMfProject.open(result_3mf)
    with pytest.raises(AlreadyLoopedError):
        build_loops(project, detect_printer(project), LoopSettings(loops=2), source_name=result_3mf.name)


def test_forcing_an_already_looped_input_reports_a_warning(result_3mf):
    assert any("already been looped" in warning for warning in _build(result_3mf, 2).warnings)


def test_detects_a1_mini(result_3mf):
    assert detect_printer(ThreeMfProject.open(result_3mf)).key == "a1mini"


@pytest.mark.parametrize("loops", [1, 2, 5])
def test_every_loop_is_emitted_once(result_3mf, loops):
    gcode = _build(result_3mf, loops).gcode
    for index in range(1, loops + 1):
        assert gcode.count(f"; >>> LOOP {index} / {loops} <<<") == 1
    assert gcode.count("; >>> END OF PRINT LOOPS <<<") == 1


@pytest.mark.parametrize("loops", [1, 2, 5])
def test_one_push_off_per_loop(result_3mf, loops):
    body = _executable_part(_build(result_3mf, loops).gcode)
    assert body.count("; Align nozzle with model center for push") == loops
    assert body.count("G1 Y-0.5 F300") == loops
    assert body.count(";====== Safety clear complete =======") == loops


@pytest.mark.parametrize("loops", [1, 2, 5])
def test_one_start_code_per_loop(result_3mf, loops):
    body = _executable_part(_build(result_3mf, loops).gcode)
    assert body.count(";===== machine: A1 mini =========================") == loops
    assert body.count("; EXECUTABLE_BLOCK_START") == loops


def test_header_and_config_appear_only_in_the_first_loop(result_3mf):
    gcode = _build(result_3mf, 3).gcode
    assert gcode.count("; CONFIG_BLOCK_START") == 1
    assert gcode.count("; HEADER_BLOCK_START") == 1
    # Later loops open with a buffer-drain wait instead.
    assert gcode.count("M400 ; Looprint safety: Wait for buffer clear before next loop") == 2


def test_speed_mode_is_applied_to_every_loop_and_reset_at_the_end(result_3mf):
    gcode = _build(result_3mf, 2, speed_mode=124).gcode
    assert gcode.count("M220 S124 ; Set speed mode") == 2
    assert "M220 S124 ;Reset Feedrate (Looprint: 124% speed)" in gcode
    assert gcode.rstrip().endswith("; ===== Looprint Loop File (End) =====")
    assert "M220 S100 ; Reset to standard speed" in gcode


def test_the_source_end_code_does_not_survive_inside_a_loop(result_3mf):
    """Only the freshly generated cool-down may appear, once per loop."""
    body = _executable_part(_build(result_3mf, 2).gcode)
    assert body.count("M18 X Y Z") == 2
    # 18 C requested, floored to the 15 C minimum, repeated 50x per cool-down.
    assert body.count("M190 S15") == 2 * 50


def test_output_can_be_repacked_as_a_3mf(result_3mf, tmp_path):
    project = ThreeMfProject.open(result_3mf)
    result = _build(result_3mf, 2)
    destination = tmp_path / "looped.gcode.3mf"
    project.save_as(destination, result.gcode)

    repacked = ThreeMfProject.open(destination)
    assert repacked.gcode == result.gcode
    # Every other member survives untouched.
    assert set(repacked.members) == set(project.members)
    assert repacked.text("Metadata/slice_info.config") == project.text("Metadata/slice_info.config")

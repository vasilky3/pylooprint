"""The printer registry, detection, and what each profile contributes."""

from __future__ import annotations

import pytest

from pylooprint.cli import main
from pylooprint.core.structure import GcodeStructure
from pylooprint.errors import LooprintError
from pylooprint.printers import EndCodeContext, PrinterProfile, available_profiles, get_profile
from pylooprint.printers.detection import (
    detect_from_gcode_header,
    detect_from_model_id,
    detect_from_project_settings,
)
from pylooprint.settings import LoopSettings

from conftest import a1mini_end_code

CONTEXT = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=18))


def test_the_registry_holds_the_a1_mini_and_the_a1_stub():
    assert sorted(available_profiles()) == ["a1", "a1mini"]
    for profile in available_profiles().values():
        assert isinstance(profile, PrinterProfile)
        assert profile.key and profile.name and profile.model_ids


@pytest.mark.parametrize(("model_id", "key"), [("N1", "a1mini"), ("N2S", "a1")])
def test_model_ids_map_to_profiles(model_id, key):
    slice_info = f'<metadata key="printer_model_id" value="{model_id}"/>'
    assert detect_from_model_id(slice_info).key == key


def test_an_unknown_model_id_is_not_guessed():
    assert detect_from_model_id('<metadata key="printer_model_id" value="C11"/>') is None
    assert detect_from_project_settings("@BBL P1S") is None
    assert detect_from_gcode_header(";===== machine: P1S =====") is None


def test_the_a1_mini_is_told_apart_from_the_a1():
    assert detect_from_gcode_header(";===== machine: A1 mini =====").key == "a1mini"
    assert detect_from_gcode_header(";===== machine: A1 =====").key == "a1"
    assert detect_from_project_settings("PLP Bambu PLA Matte @BBL A1M").key == "a1mini"
    assert detect_from_project_settings("Bambu Lab A1 0.4 nozzle @BBL A1").key == "a1"


def test_the_cooldown_wait_is_repeated_often_enough():
    assert get_profile("a1mini").cooldown_block(18).count("M190") == 50


def test_the_bed_sensor_offset_is_compensated():
    assert get_profile("a1mini").apply_temp_offset(58) == 54
    assert get_profile("a1mini").apply_temp_offset(18) == 15  # the floor


def test_the_a1_mini_pushes_along_y_and_sweeps_inside_its_bed():
    code = a1mini_end_code(CONTEXT)
    assert "G1 Y-0.5 F300" in code
    assert "G1 X180 F800" in code and "G1 X-13\tF2000" in code
    assert "X256" not in code


def test_the_a1_stub_refuses_to_build():
    """Registered and detected, so an A1 plate is refused by name, not mangled."""
    structure = GcodeStructure(header="", config="", setup="", print_body="")
    with pytest.raises(LooprintError, match="A1: the eject sequence has not been written yet"):
        get_profile("a1").build_machine_code(structure, CONTEXT)


def test_the_a1_stub_is_refused_from_the_command_line(cone_multi_project, tmp_path, capsys):
    exit_code = main([str(cone_multi_project), "-p", "a1", "--dry-run", "-o", str(tmp_path / "x.3mf")])
    assert exit_code == 1
    assert "A1: the eject sequence has not been written yet" in capsys.readouterr().err

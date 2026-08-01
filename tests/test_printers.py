"""What each profile contributes on top of the common pipeline."""

from __future__ import annotations

import pytest

from pylooprint.printers import EndCodeContext, available_profiles, get_profile
from pylooprint.printers.detection import detect_from_gcode_header, detect_from_model_id
from pylooprint.settings import LoopSettings

CONTEXT = EndCodeContext(settings=LoopSettings(loops=1, cooldown_temp=18))


@pytest.mark.parametrize(
    ("model_id", "key"),
    [("N1", "a1mini"), ("N2S", "a1"), ("C11", "p1"), ("BL-P001", "x1")],
)
def test_model_ids_map_to_profiles(model_id, key):
    slice_info = f'<metadata key="printer_model_id" value="{model_id}"/>'
    assert detect_from_model_id(slice_info).key == key


def test_gcode_header_detection_prefers_a1_mini_over_a1():
    assert detect_from_gcode_header(";===== machine: A1 mini =====").key == "a1mini"


@pytest.mark.parametrize("key", sorted(available_profiles()))
def test_every_profile_produces_a_start_and_end_code(key):
    profile = get_profile(key)
    assert profile.start_code().strip()
    assert profile.end_code(CONTEXT).strip()


@pytest.mark.parametrize(("key", "expected"), [("a1", 45), ("a1mini", 50), ("p1", 30), ("x1", 30)])
def test_cooldown_wait_is_repeated_often_enough(key, expected):
    profile = get_profile(key)
    assert profile.cooldown_block(18).count("M190") == expected


def test_bed_slingers_compensate_the_bed_sensor_offset():
    assert get_profile("a1mini").apply_temp_offset(58) == 54
    assert get_profile("a1").apply_temp_offset(18) == 15
    assert get_profile("p1").apply_temp_offset(18) == 18


def test_bed_slinger_pushes_along_y_and_corexy_along_x():
    a1_mini = get_profile("a1mini").end_code(CONTEXT)
    assert "G1 Y-0.5 F300" in a1_mini
    assert "PUSH LANE" not in a1_mini

    p1 = get_profile("p1").end_code(CONTEXT)
    assert "; --- PUSH LANE 1: CENTER" in p1
    assert "G1 Y-0.5 F300" not in p1


def test_a1_mini_wiggle_stays_inside_its_smaller_bed():
    code = get_profile("a1mini").end_code(CONTEXT)
    assert "G1 X180 F800" in code and "G1 X-13\tF2000" in code
    assert "X256" not in code

    a1 = get_profile("a1").end_code(CONTEXT)
    assert "G1 X256 F800" in a1 and "G1 X-48\tF2000" in a1


def test_push_lanes_follow_the_detected_model():
    context = EndCodeContext(
        settings=LoopSettings(loops=1, cooldown_temp=18),
        model_min_x=100.0,
        model_max_x=140.0,
    )
    lanes = get_profile("p1").push_lanes(context)
    assert (lanes.centre_x, lanes.left_x, lanes.right_x) == ("120.0", "90.0", "150.0")


def _lane_offset_context() -> EndCodeContext:
    """A model close enough to the left edge that the 30 mm offset cannot fit."""
    return EndCodeContext(
        settings=LoopSettings(loops=1, cooldown_temp=18),
        model_min_x=20.0,
        model_max_x=40.0,
    )


def test_push_lanes_are_pulled_back_from_the_bed_edge():
    profile = get_profile("p1")
    lanes = profile.push_lanes(_lane_offset_context())
    # Centre 30, bed starts at 10, so only 20 mm of offset fits.
    assert (lanes.left_x, lanes.centre_x, lanes.right_x) == ("10.0", "30.0", "50.0")
    assert float(lanes.left_x) >= profile.bed_bounds.min_x
    assert lanes.warning is not None


def test_an_adjusted_lane_offset_is_reported():
    """The auto-adjustment changes the push geometry, so the user hears about it."""
    warnings = get_profile("p1").end_code_warnings(_lane_offset_context())
    assert any("auto-adjusted" in warning for warning in warnings)
    assert get_profile("p1").end_code_warnings(EndCodeContext(settings=LoopSettings())) == ()

"""Unit tests for the printer-independent steps."""

from __future__ import annotations

from pylooprint.core.config_block import config_value, parse_config_block
from pylooprint.core.jsnum import number_to_string, to_fixed
from pylooprint.core.placement import determine_model_placement
from pylooprint.core.structure import extract_original_tool_command, split_gcode
from pylooprint.core.template import render_start_code, resolve_max_layer_z
from pylooprint.core.variables import extract_variable_values

CONFIG = """; CONFIG_BLOCK_START
; curr_bed_type = Textured PEI Plate
; filament_type = PLA
; initial_extruder = 0
; nozzle_temperature_initial_layer = 220
; filament_max_volumetric_speed = 21
; bed_temperature_initial_layer_single = 60
; CONFIG_BLOCK_END"""


def test_parse_config_block_splits_comma_separated_lists():
    config = parse_config_block('; a = 1,2,3\n; c = 7\n; d[1] = 9\n; e = say "hi", ok')
    assert config["a"] == ["1", "2", "3"]
    assert config["c"] == "7"
    assert config["d"] == ["", "9"]
    # A value carrying a quote is never split - that is how the slicer stores
    # whole G-code snippets on one line.
    assert config["e"] == 'say "hi", ok'


def test_config_value_resolves_the_extruder_index():
    config = parse_config_block("; nozzle_temperature = 200,230")
    assert config_value(config, "nozzle_temperature", None, "1") == "230"
    assert config_value(config, "nozzle_temperature", None, "0") == "200"


def test_split_gcode_separates_every_piece_a_loop_is_built_from():
    gcode = (
        "; HEADER_BLOCK_START\n; max_z_height: 10\n; HEADER_BLOCK_END\n"
        + CONFIG
        + "\n; EXECUTABLE_BLOCK_START\nM73 P0\n; FEATURE: Custom\nT0\nM109 S220\n"
        "; CHANGE_LAYER\nG1 X1 Y1 E1\n"
        ";===== date: 20240101 =====\nM104 S0\nM18 X Y Z\n"
    )
    structure = split_gcode(gcode)
    assert structure.setup.endswith("; FEATURE: Custom")
    assert structure.print_body.startswith("; CHANGE_LAYER")
    assert structure.print_body.rstrip().endswith("G1 X1 Y1 E1")
    assert "; CONFIG_BLOCK_START" in structure.config
    assert "; CONFIG_BLOCK_START" not in structure.header
    assert structure.original_tool_command == "0"
    # The machine start/end code is kept for the in-place strategy to patch.
    assert structure.slicer_start_code == "T0\nM109 S220"
    assert structure.slicer_end_code.startswith(";===== date: 20240101")
    assert "M18 X Y Z" in structure.slicer_end_code


def test_extract_original_tool_command_ignores_temperatures_and_t255():
    executable = "; FEATURE: Custom\nG28 Z P0 T300\nM620 S255\nT1\n; CHANGE_LAYER\n"
    assert extract_original_tool_command(executable) == "1"


def test_variables_fall_back_to_safe_defaults():
    values = extract_variable_values("", "")
    assert values["nozzle_temperature_initial_layer"] == "220"
    assert values["bed_temperature_initial_layer_single"] == "60"
    assert values["initial_extruder"] == "0"


def test_variables_read_the_config_block():
    values = extract_variable_values("", CONFIG)
    assert values["filament_type"] == "PLA"
    assert values["curr_bed_type"] == "Textured PEI Plate"
    assert values["nozzle_temperature_range_high"] == "240"


def test_start_code_substitution_covers_all_three_notations():
    values = extract_variable_values("", CONFIG)
    template = (
        "M104 S[nozzle_temperature_initial_layer]\n"
        "T[initial_extruder]\n"
        "M109 S{nozzle_temperature_initial_layer[initial_extruder]-20}\n"
        "M620.1 E F{filament_max_volumetric_speed[initial_extruder]/2.4053*60}\n"
        '{if filament_type[initial_extruder]=="PLA"}\nM106 P3 S180\n{endif}\n'
        'M220 S100 ;Reset Feedrate'
    )
    rendered = render_start_code(template, values)
    assert "M104 S220" in rendered
    assert "T0" in rendered
    assert "M109 S200" in rendered
    assert "M620.1 E F524" in rendered
    assert "M106 P3 S180" in rendered
    assert "M220 S100 ;Reset Feedrate (Looprint: 100% speed)" in rendered


def test_pla_block_is_dropped_for_other_filaments():
    values = extract_variable_values("", CONFIG.replace("filament_type = PLA", "filament_type = PETG"))
    rendered = render_start_code(
        '{if filament_type[initial_extruder]=="PLA"}\nM106 P3 S180\n{endif}', values
    )
    assert "M106 P3 S180" not in rendered


#: The push-off Z-drop, as ``a1_push.gcode`` spells it once the A1 Mini's push
#: constants are substituted in.
_Z_DROP = "{if (max_layer_z ) >= 6}\n    G1 Z{max_layer_z * 0.7} F600\n{else}\n    G1 Z0.2 F600\n{endif}"


def test_z_drop_aims_at_seventy_percent_of_the_model_height():
    """The nozzle lands high on the side wall, where the push tips the part over."""
    assert "G1 Z12.68 F600" in resolve_max_layer_z(_Z_DROP, 18.12)
    assert "G1 Z42.00 F600" in resolve_max_layer_z(_Z_DROP, 60.0)
    assert "G1 Z140.00 F600" in resolve_max_layer_z(_Z_DROP, 200.0)


def test_z_drop_keeps_the_nozzle_off_the_plate_below_six_millimetres():
    """Under 6 mm there is no useful height to aim at, so the nozzle drops to Z0.2."""
    assert "G1 Z0.2 F600" in resolve_max_layer_z(_Z_DROP, 5.9)
    # 6 mm itself takes the 70% branch: the conditional is `>=`.
    assert "G1 Z4.20 F600" in resolve_max_layer_z(_Z_DROP, 6.0)


def test_corexy_keeps_the_fixed_offset_rule():
    """P1 and X1 still raise the bed to 30 mm under the top, or Z1 when short.

    Their toolhead carries the part cooling fans and the LIDAR, so it needs the
    clearance above the model that a push at 70% of its height would give away.
    """
    template = "{if (max_layer_z ) > 31}\n    G1 Z{max_layer_z - 30} F600\n{else}\n    G1 Z1 F600\n{endif}"
    assert "G1 Z1 F600" in resolve_max_layer_z(template, 18.12)
    assert "G1 Z30.00 F600" in resolve_max_layer_z(template, 60.0)


def test_max_layer_z_arithmetic_uses_two_decimals():
    assert resolve_max_layer_z("G1 Z{max_layer_z + 0.5}", 18.12) == "G1 Z18.62"
    assert resolve_max_layer_z("G1 Z{max_layer_z - 40}", 60.0) == "G1 Z20.00"
    assert resolve_max_layer_z("G1 Z{max_layer_z * 0.75}", 18.12) == "G1 Z13.59"


def test_placement_finds_a_centred_model():
    lines = [f"G1 X{110 + i % 20} Y{110 + i % 20} Z5 E0.1" for i in range(200)]
    placement = determine_model_placement("\n".join(lines), -13, 180, 0, 185)
    assert placement.direction == "center"
    assert placement.min_x == 110
    assert placement.max_x == 129


def test_placement_ignores_purge_and_wipe_moves():
    """Prime lines at the bed edge and the nozzle wipe at X100 are not the model."""
    lines = [f"G1 X{110 + i % 20} Y{110 + i % 20} Z5 E0.1" for i in range(200)]
    lines += ["G1 X100 Y264 Z5 E0.1"] * 50  # wipe sequence
    lines += ["G1 X20 Y10 Z0.2 E0.5"] * 50  # purge line at the edge
    placement = determine_model_placement("\n".join(lines), -13, 180, 0, 185)
    assert (placement.min_x, placement.max_x) == (110, 129)


def test_javascript_number_formatting():
    assert to_fixed(18.615, 2) == "18.62"
    assert to_fixed(1.0, 1) == "1.0"
    assert number_to_string(200.0) == "200"
    assert number_to_string(2000) == "2000"

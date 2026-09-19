"""The looping Orca profile: the purge wall lives there, not in pylooprint.

``profiles/a1mini/source/start.gcode`` is the readable start G-code; the JSON
Orca imports is built from it.  What these tests pin is that the two agree, and
that the source says what the rest of the code assumes about the wall - where it
stands, how tall, and that the nozzle is at temperature before it is extruded.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "profiles"))

from build_profile import PRINTERS, build, render  # noqa: E402

from pylooprint.core.constants import EXECUTABLE_BLOCK_START, FEATURE_CUSTOM, LAYER_MARKER_RE  # noqa: E402
from pylooprint.core.structure import split_gcode  # noqa: E402
from pylooprint.printers.a1mini.profile import PURGE_SWEEP_Y, PURGE_WALL_X  # noqa: E402

A1MINI = PRINTERS["a1mini"]
WALL_START = ";===== LOOPRINT PURGE WALL ====="
WALL_END = ";===== LOOPRINT PURGE WALL END ====="


@pytest.fixture(scope="module")
def source() -> str:
    return A1MINI.source.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def profile() -> dict:
    return json.loads(A1MINI.machine.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wall(source: str) -> list[str]:
    """The commands of the purge-wall block, comments dropped."""
    block = source[source.index(WALL_START) + len(WALL_START) : source.index(WALL_END)]
    commands = [line.split(";")[0].strip() for line in block.split("\n")]
    return [command for command in commands if command]


def test_the_json_is_built_from_the_source(profile, source):
    """Edit the .gcode, run build_profile.py - never the JSON by hand."""
    assert A1MINI.machine.read_text(encoding="utf-8") == render(build(profile, source, A1MINI.name))
    assert profile["machine_start_gcode"] == source


def test_the_profile_is_the_user_s_own_not_the_system_one(profile):
    """Same name as the stock preset and Orca refuses it as a duplicate."""
    assert profile["name"] == A1MINI.name
    assert profile["from"] == "User"
    assert profile["inherits"] == "Bambu Lab A1 mini 0.4 nozzle"


def test_the_stock_purge_draws_are_gone(source):
    """The stock profile draws two calibration lines on the strip in front of the plate."""
    assert "G0 X68 Y-4 F30000" not in source
    assert "G0 X68 Y-2.5 F30000" not in source
    assert "G0 X88 E10" not in source


def test_the_calibration_still_gets_its_prime(source):
    """The draw inside M622 J1 became an air purge; M983 measures pressure, not a line."""
    block = source[source.index("M900 K0.0 L1000.0 M1.0") : source.index("M983", source.index("M900 K0.0"))]
    assert re.search(r"^\s*G1 E\d+ F\d+", block, flags=re.MULTILINE)
    assert "G0 X68" not in block


def test_the_wall_waits_for_the_nozzle_before_extruding(wall):
    temperature = next(i for i, c in enumerate(wall) if c.startswith("M109 S{nozzle_temperature_initial_layer"))
    first_extrusion = next(i for i, c in enumerate(wall) if re.match(r"G1 .*E\d", c))
    assert temperature < first_extrusion


def test_the_wall_is_nine_layers_to_1_8_mm(wall):
    """1.8 mm in millimetres: 0.2 mm layers, whatever print profile is chosen."""
    heights = [float(m.group(1)) for c in wall if (m := re.match(r"G1 Z([\d.]+) F3000$", c))]
    assert heights == [pytest.approx(0.2 * n) for n in range(1, 10)]


def test_the_wall_stands_where_the_stock_purge_lines_were(wall):
    """Two lines along X68..98, between the stock draws' Y-4 and Y-2.5."""
    xs = {m.group(1) for c in wall if (m := re.match(r"G1 X(\d+) E", c))}
    ys = {m.group(1) for c in wall if (m := re.match(r"G1 Y(-[\d.]+) E", c))}
    assert xs == {"68", "98"}
    assert ys == {"-3.46", "-3.04"}
    assert -4 < -3.46 < -3.04 < -2.5


def test_the_sweep_constants_match_the_wall():
    """pylooprint shoves the wall at its middle; the profile decides where that is."""
    assert PURGE_WALL_X == (68 + 98) / 2
    assert PURGE_SWEEP_Y < -3.46  # past the wall's front line, so it is hit broadside
    assert PURGE_SWEEP_Y >= -5.0  # and no further than the machine is known to reach


def test_nothing_in_the_start_code_looks_like_a_layer_marker(source):
    """pylooprint splits a plate at the first layer marker after the custom-feature line.

    A wall comment that reads like one ("; layer 1 ...") would end the start
    code mid-wall: the rest of the wall becomes print body and is reported as
    a part.
    """
    assert LAYER_MARKER_RE.search(source) is None

    plate = "\n".join(
        [
            "; HEADER",
            EXECUTABLE_BLOCK_START,
            "M73 P0 R10",
            FEATURE_CUSTOM,
            source,
            "; CHANGE_LAYER",
            "; Z_HEIGHT: 0.2",
            "G1 X10 Y10 E1",
            ";===== date: 20231229 =====================",
            "M400",
            "",
        ]
    )
    structure = split_gcode(plate)
    assert WALL_END in structure.slicer_start_code
    assert "X98" not in structure.print_body
    assert structure.print_body.startswith("; CHANGE_LAYER")

"""The looping machine profile: the purge wall lives there, not in pylooprint.

``profiles/source/a1mini_start.gcode`` is the readable start G-code; the JSON
Orca imports is built from it.  What these tests pin is that the two agree, and
that the source says what the rest of the code assumes about the wall - where it
is, how tall, and that the nozzle is at temperature before a millimetre of it is
extruded.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "profiles"))

from build_profile import PROFILE, PROFILE_NAME, SOURCE, build, render  # noqa: E402

from pylooprint.printers.a1_mini import PURGE_SWEEP_Y, PURGE_WALL_X  # noqa: E402

WALL_START = ";===== LOOPRINT PURGE WALL ====="
WALL_END = ";===== LOOPRINT PURGE WALL END ====="


@pytest.fixture(scope="module")
def source() -> str:
    return SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wall(source: str) -> list[str]:
    """The lines of the purge-wall block, markers excluded."""
    block = source[source.index(WALL_START) + len(WALL_START) : source.index(WALL_END)]
    return [line for line in block.strip().split("\n")]


def test_the_json_is_built_from_the_source(profile, source):
    """Edit the .gcode, run build_profile.py - never the JSON by hand."""
    assert PROFILE.read_text(encoding="utf-8") == render(build(profile, source))
    assert profile["machine_start_gcode"] == source


def test_the_profile_is_the_user_s_own_not_the_system_one(profile):
    """Same name as the stock preset and Orca refuses it as a duplicate."""
    assert profile["name"] == PROFILE_NAME
    assert profile["from"] == "User"
    assert profile["printer_model"] == "Bambu Lab A1 mini"


def test_the_stock_purge_draws_are_gone(source):
    """Both calibration lines used to be drawn on the strip in front of the plate."""
    assert "G0 X68 Y-4 F30000" not in source
    assert "G0 X68 Y-2.5 F30000" not in source
    assert "G0 X88 E10" not in source


def test_the_calibration_still_gets_its_prime(source):
    """The draw inside M622 J1 became an air purge; M983 measures pressure, not a line."""
    block = source[source.index("M900 K0.0 L1000.0 M1.0") : source.index("M983", source.index("M900 K0.0"))]
    assert "G1 E12 F300" in block
    assert "G0 X68" not in block


def test_the_wall_waits_for_the_nozzle_before_purging(wall):
    """Temperature first, then the air purge, then plastic on the plate."""
    commands = [line.split(";")[0].strip() for line in wall if not line.startswith(";")]
    temperature = next(i for i, c in enumerate(commands) if c.startswith("M109 S{nozzle_temperature_initial_layer"))
    air_purge = commands.index("G1 E12 F300")
    first_extrusion = next(i for i, c in enumerate(commands) if c.startswith("G1 X98 E"))
    assert temperature < air_purge < first_extrusion


def test_the_wall_is_nine_layers_to_1_8_mm(wall):
    """1.8 mm in millimetres: 0.2 mm layers, whatever print profile is chosen."""
    heights = [float(m.group(1)) for line in wall if (m := re.match(r"G1 Z([\d.]+) F3000", line))]
    assert heights == [pytest.approx(0.2 * n) for n in range(1, 10)]
    assert heights[-1] == pytest.approx(1.8)


def test_the_wall_stands_where_the_stock_purge_lines_were(wall):
    """Two lines along X68..98, between the stock draws' Y-4 and Y-2.5."""
    xs = {m.group(1) for line in wall if (m := re.match(r"G1 X(\d+) E", line))}
    ys = {m.group(1) for line in wall if (m := re.match(r"G1 Y(-[\d.]+) E", line))}
    assert xs == {"68", "98"}
    assert ys == {"-3.46", "-3.04"}
    assert -4 < -3.46 < -3.04 < -2.5


def test_the_sweep_constants_match_the_wall(wall):
    """pylooprint shoves the wall at its middle; the profile decides where that is."""
    assert PURGE_WALL_X == (68 + 98) / 2
    assert PURGE_SWEEP_Y < -3.46  # past the wall's front line, so it is hit broadside
    assert PURGE_SWEEP_Y >= -5.0  # and no further than the machine is known to reach


def test_every_line_is_extruded_for_the_0_2_profile(wall):
    """30 mm at 0.42 x 0.2 on 1.75 mm filament is E1.05; 0.5 wide on layer 1 is E1.25."""
    lines = [line.split(";")[0].split() for line in wall if re.match(r"G1 X(68|98) E", line)]
    assert len(lines) == 18  # two per layer
    assert [words[2] for words in lines[:2]] == ["E1.25", "E1.25"]
    assert all(words[2] == "E1.05" for words in lines[2:])


def test_the_wall_ends_with_a_wipe_not_a_lift(wall):
    """The last line is the front one, so the run to Y0 drags across the back one."""
    commands = [line.split(";")[0].strip() for line in wall if not line.startswith(";")]
    last_line = max(i for i, c in enumerate(commands) if c.startswith("G1 X68 E"))
    assert commands[last_line - 1] == "G1 Y-3.46 E0.01"
    assert commands[last_line + 1] == "G1 Y0 F18000"
    assert not any(c.startswith("G1 Z5") or c.startswith("G0 Z5") for c in commands[last_line:])

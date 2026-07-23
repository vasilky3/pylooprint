"""pylooprint must produce what the original web tool produces.

The fixtures in ``tests/golden/`` were captured by running the unmodified
``looprint/index.html`` in a browser on ``Gcode/test 2 blocks.gcode.3mf``.
Only the ``; Generated:`` banner may differ - it is a wall-clock timestamp.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from pylooprint.core.project import ThreeMfProject
from pylooprint.pipeline import build_loops, detect_printer
from pylooprint.settings import LoopSettings

from conftest import CONTAINER

GOLDEN_DIR = Path(__file__).parent / "golden"

#: fixture name -> the settings the web tool was driven with.
SCENARIOS = {
    "webtool_n3_t18.gcode.gz": LoopSettings(loops=3, cooldown_temp=18, speed_mode=100),
    "webtool_n5_t30_s124.gcode.gz": LoopSettings(loops=5, cooldown_temp=30, speed_mode=124),
    "webtool_n2_t25_s166.gcode.gz": LoopSettings(loops=2, cooldown_temp=25, speed_mode=166),
}


def _without_timestamp(gcode: str) -> list[str]:
    return [line for line in gcode.split("\n") if not line.startswith("; Generated: ")]


@pytest.mark.parametrize("fixture", sorted(SCENARIOS))
def test_matches_the_web_tool(fixture):
    golden_path = GOLDEN_DIR / fixture
    if not golden_path.exists() or not CONTAINER.exists():
        pytest.skip(f"sample not available: {fixture}")

    expected = gzip.decompress(golden_path.read_bytes()).decode("utf-8")

    project = ThreeMfProject.open(CONTAINER)
    result = build_loops(
        project, detect_printer(project), SCENARIOS[fixture], source_name=CONTAINER.name
    )

    assert _without_timestamp(result.gcode) == _without_timestamp(expected)


def test_only_the_timestamp_line_is_allowed_to_differ():
    """Guard the guard: the normalisation must not be hiding anything else."""
    golden_path = GOLDEN_DIR / "webtool_n3_t18.gcode.gz"
    if not golden_path.exists() or not CONTAINER.exists():
        pytest.skip("sample not available")

    expected = gzip.decompress(golden_path.read_bytes()).decode("utf-8")
    project = ThreeMfProject.open(CONTAINER)
    produced = build_loops(
        project, detect_printer(project), SCENARIOS["webtool_n3_t18.gcode.gz"], source_name=CONTAINER.name
    ).gcode

    differing = [
        (left, right)
        for left, right in zip(expected.split("\n"), produced.split("\n"))
        if left != right
    ]
    assert len(differing) == 1
    assert differing[0][0].startswith("; Generated: ")

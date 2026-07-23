"""Shared fixtures.

The golden files live in the sibling ``Gcode`` folder that ships with this
repository; tests that need them are skipped when it is not present.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GCODE_DIR = ROOT.parent / "Gcode"
SAMPLES = GCODE_DIR / "test 2 blocks gcode"

#: Plain sliced plate for an A1 Mini, and the file the original web tool
#: produced from it with loops=1 and a 58 degree cool-down.
GOLDEN_SOURCE = SAMPLES / "test 2 blocks" / "Metadata" / "2b_base.gcode"
GOLDEN_OUTPUT = SAMPLES / "test 2 blocks_Looprint" / "Metadata" / "2b_LP.gcode"
CONTAINER = GCODE_DIR / "test 2 blocks.gcode.3mf"
#: A hand-assembled A1 Mini file that already carries a Looprint end code.
RESULT_3MF = GCODE_DIR / "result.gcode.3mf"

GOLDEN_TEMP = 58
GOLDEN_LOOPS = 1


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"sample file not available: {path}")
    return path


@pytest.fixture(scope="session")
def golden_expected() -> str:
    return _require(GOLDEN_OUTPUT).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def golden_project(tmp_path_factory) -> Path:
    """The sliced plate that produced the golden output, packed as a 3MF."""
    _require(CONTAINER)
    _require(GOLDEN_SOURCE)
    destination = tmp_path_factory.mktemp("golden") / "golden_input.gcode.3mf"
    plate = GOLDEN_SOURCE.read_bytes()
    with zipfile.ZipFile(CONTAINER) as source, zipfile.ZipFile(
        destination, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            payload = plate if item.filename == "Metadata/plate_1.gcode" else source.read(item.filename)
            target.writestr(item, payload)
    return destination


@pytest.fixture(scope="session")
def result_3mf() -> Path:
    return _require(RESULT_3MF)

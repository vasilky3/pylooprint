"""Shared fixtures.

The sample files live in the sibling ``Gcode`` folder that ships with this
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

#: Plain sliced A1 Mini plate, and the 3MF it came out of.
GOLDEN_SOURCE = SAMPLES / "test 2 blocks" / "Metadata" / "2b_base.gcode"
CONTAINER = GCODE_DIR / "test 2 blocks.gcode.3mf"

#: An A1 Mini file that already carries a Looprint end code; used to check the
#: Factorian fallback against a real looped output.
RESULT_3MF = GCODE_DIR / "result.gcode.3mf"
#: Cool-down temperature baked into the end code embedded in RESULT_3MF.
GOLDEN_TEMP = 58

#: The hand-modified reference for the in-place strategy: the same slicer output
#: as GOLDEN_SOURCE, with the purge lines turned into air purges and the eject
#: sequence spliced into the machine end code. Built with a 28 C cool-down.
INPLACE_REFERENCE = SAMPLES / "test 2 blocks mymod" / "Metadata" / "plate_1.gcode"
INPLACE_TEMP = 28


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"sample file not available: {path}")
    return path


@pytest.fixture(scope="session")
def golden_project(tmp_path_factory) -> Path:
    """The plain sliced plate, packed as a 3MF - the in-place strategy's input."""
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


@pytest.fixture(scope="session")
def inplace_reference() -> str:
    return _require(INPLACE_REFERENCE).read_text(encoding="utf-8")

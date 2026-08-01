"""Shared fixtures.

Sample plates come from two places:

* ``tests/test gcode/`` - sliced plates that ship with the repository, used by
  the eject keep-out tests; and
* the sibling ``Gcode`` folder - the larger reference files the in-place and
  Factorian golden tests compare against.

Tests that need a file missing from either are skipped rather than failed.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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

#: Sliced A1 Mini plates that pin the eject keep-out rule.  The unsliced
#: projects they came from live in ``../orcaProj``.
PLATES = ROOT / "tests" / "test gcode"
#: 180 mm cube covering the whole plate - prints in the corner, must be refused.
FULLFIELD = PLATES / "A1mini_cube180_fullfield.gcode.3mf"
#: 160 mm cube shifted right - reaches past Y150 but stays clear of X15.
SUITABLE = PLATES / "A1mini_cube160h180_sutable.gcode.3mf"
#: The plate the bounding-box check used to refuse: it reaches X14 at the front
#: and Y169 in the middle, so its box covers the corner while no material does.
TRPASLIK = PLATES / "trpaslik+3mf.gcode.3mf"


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


@pytest.fixture(scope="session")
def fullfield_project() -> Path:
    """180 mm cube covering the whole plate - must be refused."""
    return _require(FULLFIELD)


@pytest.fixture(scope="session")
def suitable_project() -> Path:
    """160 mm cube shifted clear of the keep-out corner - must be accepted."""
    return _require(SUITABLE)


@pytest.fixture(scope="session")
def trpaslik_project() -> Path:
    """Wide plate that spans the keep-out corner without entering it."""
    return _require(TRPASLIK)

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
#: Four cones, two of them touching, sliced with arc fitting on - the plate that
#: pins both the part finder's merging and its handling of ``G2``/``G3``.
CONE_MULTI = PLATES / "A1mini_cone_multi.gcode.3mf"


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


@pytest.fixture(scope="session")
def cone_multi_project() -> Path:
    """Four cones drawn with arc moves, two of them touching each other."""
    return _require(CONE_MULTI)


def without_release_hold(code: str) -> str:
    """Drop the hold block, so a comparison cannot depend on its contents.

    ``result.gcode.3mf`` is a real output of the original web tool and the
    in-place reference is hand-made, so neither knows about the wait and the
    push-off beep this port adds between the cool-down and the push.  Those are
    pinned separately in ``test_release_hold.py``.
    """
    from pylooprint.printers.bedslinger import HOLD_END, HOLD_START

    if HOLD_START not in code:
        return code
    start = code.index(HOLD_START)
    end = code.index(HOLD_END) + len(HOLD_END)
    return code[:start].rstrip("\n") + "\n" + code[end:].lstrip("\n")


# --- the deliberate divergences from the reference files --------------------
# Both references were made when the push-off aimed a fixed 40 mm below the top
# of the model, which came out as Z1 for anything shorter than 41 mm.  Both
# models are 18.12 mm tall, so both show that Z1.  Looprint now pushes at 70% of
# the model height, and the comments around the push were rewritten with it, so
# these blocks differ while everything around them still has to match byte for
# byte.
#
# Every string is written out by hand.  Rendering the current template here
# instead would compare the template against itself and pin nothing.
_OLD_Z_DROP = (
    ";===== Z-Drop Logic (41mm Rule) =====\n"
    "; Factorian's exact conditional from End_A1.txt lines 175-179: "
    "IF (max_layer_z ) > 41 THEN Z = max_layer_z - 40 ELSE Z = 1.0\n"
    "; Note: Factorian uses conditional logic with space after max_layer_z - "
    "our regex handles this format\n"
    "\n"
    "    G1 Z1 F600\n"
    "\n"
    "\n"
)
_NEW_Z_DROP = (
    ";===== Z-Drop Logic =====\n"
    "; Push at 0.7 of the model height: high enough on the side wall to tip the part\n"
    "; over, and still below its top edge.\n"
    "; Under 6 mm there is no useful height left to aim at, so the nozzle\n"
    "; comes down to Z0.2 and shoves the part along the plate instead.\n"
    "G1 Z12.68 F600\n"
    "\n"
)

#: Each ``(old, new)`` pair is one region of the push block that a reference file
#: still carries in its previous wording.  ``18.12 * 0.7`` is ``12.68``, so a
#: reference that pushed at Z1 now pushes at Z12.68.
_PUSH_BLOCK_UPDATES = (
    (
        "; (This alignment move is not in End_A1.txt but is critical for push accuracy)\n",
        "",
    ),
    (_OLD_Z_DROP, _NEW_Z_DROP),
    (
        "; Factorian Speed: F300 (very slow to prevent tipping on moving bed) - "
        "End_A1.txt line 182, End_A1_Mini.txt line 186\n",
        "; F300 is deliberately slow: the bed is moving under the part, and a quick "
        "shove tips it over instead of sliding it off.\n",
    ),
    (
        "; Note: Factorian's End_A1.txt line 182 has no M400 after push, "
        "but we add it for safety\n",
        "",
    ),
)


#: What brackets the push-off, in a reference file (the old single line) and in
#: today's output (a run of lines planned from the parts).
_PUSH_SECTIONS = (
    (";======= LOOPRINT PUSH PLAN =======", ";======= END LOOPRINT PUSH PLAN ======="),
    (
        "M220 S100 ; Reset to standard speed for safe push-off",
        "G1 Z1 F600\t\t;move nozzle closer to the bed when using tall parts",
    ),
)


def without_final_park(code: str) -> str:
    """Cut the final park out, if this end code is the one that carries it.

    Only the last loop parks the head, and the reference files predate the park
    entirely; ``test_parking.py`` pins it instead.
    """
    start_marker = ";======= LOOPRINT FINAL PARK ======="
    end_marker = ";======= END LOOPRINT FINAL PARK ======="
    if start_marker not in code:
        return code
    start = code.index(start_marker)
    end = code.index(end_marker) + len(end_marker)
    return code[:start].rstrip("\n") + "\n" + code[end:].lstrip("\n")


def without_push_block(code: str) -> str:
    """Cut the push-off out, so a comparison cannot depend on its contents.

    The push is no longer one fixed block of text: it is a line per part, at a
    height per part, worked out from the plate in hand.  A reference file cannot
    pin that, so ``test_push_plan.py`` pins it instead and the golden tests
    compare everything around it - the cool-down, the hold, the sweep, the tail.
    """
    for start_marker, end_marker in _PUSH_SECTIONS:
        if start_marker in code and end_marker in code:
            start = code.index(start_marker)
            end = code.index(end_marker, start) + len(end_marker)
            return code[:start].rstrip("\n") + "\n" + code[end:].lstrip("\n")
    raise AssertionError("no push-off found to cut out")


def with_current_push_block(expected: str) -> str:
    """Bring a reference file's push block up to the current template.

    Raises rather than returning the text unchanged, so that a reference file
    that stops carrying one of the old regions is noticed instead of silently
    turning this into a no-op.
    """
    for old, new in _PUSH_BLOCK_UPDATES:
        if old not in expected:
            raise AssertionError(f"reference file no longer carries: {old.splitlines()[0]}")
        expected = expected.replace(old, new)
    return expected

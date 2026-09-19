"""Shared fixtures: the sliced A1 Mini plates in ``tests/test gcode/``."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pytest

from pylooprint.core.project import ThreeMfProject
from pylooprint.core.structure import split_gcode
from pylooprint.printers import EndCodeContext, get_profile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLATES = ROOT / "tests" / "test gcode"
#: 180 mm cube covering the whole plate - prints in the corner, must be refused.
FULLFIELD = PLATES / "A1mini_cube180_fullfield.gcode.3mf"
#: 160 mm cube shifted right - reaches past Y150 but stays clear of X15.
SUITABLE = PLATES / "A1mini_cube160h180_sutable.gcode.3mf"
#: Reaches X14 at the front and Y169 in the middle: its box covers the
#: keep-out corner while no material does.
TRPASLIK = PLATES / "trpaslik+3mf.gcode.3mf"
#: Four cones, two of them touching, sliced with arc fitting on.
CONE_MULTI = PLATES / "A1mini_cone_multi.gcode.3mf"

A1_MINI = get_profile("a1mini")


@pytest.fixture(scope="session")
def fullfield_project() -> Path:
    return FULLFIELD


@pytest.fixture(scope="session")
def suitable_project() -> Path:
    return SUITABLE


@pytest.fixture(scope="session")
def trpaslik_project() -> Path:
    return TRPASLIK


@pytest.fixture(scope="session")
def cone_multi_project() -> Path:
    return CONE_MULTI


@lru_cache(maxsize=None)
def stock_end_code() -> str:
    """The slicer's own A1 Mini end code, as exported - what the profile patches."""
    return split_gcode(ThreeMfProject.open(CONE_MULTI).gcode).slicer_end_code


def a1mini_end_code(context: EndCodeContext, park: str = "") -> str:
    """One loop's end code, built the way the pipeline builds it."""
    return A1_MINI.patch_slicer_end_code(stock_end_code(), context, park=park)

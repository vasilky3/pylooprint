"""The printer-independent steps: splitting the file, reading moves, assembling loops."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pylooprint.core.constants import SIGNATURE
from pylooprint.core.loop_builder import LoopPlan, build_looped_gcode
from pylooprint.core.numbers import to_fixed
from pylooprint.core.placement import iter_extrusion_segments
from pylooprint.core.structure import split_gcode

PLATE = (
    "; HEADER_BLOCK_START\n; max_z_height: 10\n; HEADER_BLOCK_END\n"
    "; CONFIG_BLOCK_START\n; filament_type = PLA\n; CONFIG_BLOCK_END"
    "\n; EXECUTABLE_BLOCK_START\nM73 P0\n; FEATURE: Custom\nT0\nM109 S220\n"
    "; CHANGE_LAYER\nG1 X1 Y1 E1\n"
    ";===== date: 20240101 =====\nM104 S0\nM18 X Y Z\n"
)


def test_split_gcode_separates_every_piece_a_loop_is_built_from():
    structure = split_gcode(PLATE)
    assert structure.setup.endswith("; FEATURE: Custom")
    assert structure.print_body.startswith("; CHANGE_LAYER")
    assert structure.print_body.rstrip().endswith("G1 X1 Y1 E1")
    assert "; CONFIG_BLOCK_START" in structure.config
    assert "; CONFIG_BLOCK_START" not in structure.header
    assert structure.slicer_start_code == "T0\nM109 S220"
    assert structure.slicer_end_code.startswith(";===== date: 20240101")
    assert "M18 X Y Z" in structure.slicer_end_code


def test_the_loops_are_assembled_in_order_and_signed():
    plan = LoopPlan(
        structure=split_gcode(PLATE),
        start_code="; start",
        end_code="; end",
        final_end_code="; final end",
        loops=2,
        source_name="plate.3mf",
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    gcode = build_looped_gcode(plan)

    assert gcode.startswith(f"; ===== {SIGNATURE} (start) =====\n; Source: plate.3mf\n; Loops: 2\n")
    assert "; Generated: 2026-01-02T03:04:05Z" in gcode
    assert gcode.index("; >>> LOOP 1 / 2 <<<") < gcode.index("; end") < gcode.index("; >>> LOOP 2 / 2 <<<")
    assert gcode.index("; >>> LOOP 2 / 2 <<<") < gcode.index("; final end")
    assert gcode.count("; CONFIG_BLOCK_START") == 1  # header and config once, on the first loop
    assert gcode.count("G1 X1 Y1 E1") == 2
    assert gcode.rstrip().endswith(f"; ===== {SIGNATURE} (end) =====")


def _extent(body: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """X and Y range covered by the extruding moves of a body."""
    points = [(x, y) for x0, y0, x1, y1, *_ in iter_extrusion_segments(body) for x, y in ((x0, y0), (x1, y1))]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), max(xs)), (min(ys), max(ys))


def test_an_arc_is_walked_around_its_bulge_not_across_its_chord():
    """``G3`` counter-clockwise from the left of the circle passes underneath."""
    x_range, y_range = _extent("G1 X0 Y0 Z0.2\nG3 X10 Y0 I5 J0 E1")
    assert x_range == pytest.approx((0.0, 10.0))
    assert y_range == pytest.approx((-5.0, 0.0))


def test_an_arc_the_other_way_round_bulges_the_other_way():
    _, y_range = _extent("G1 X0 Y0 Z0.2\nG2 X10 Y0 I5 J0 E1")
    assert y_range == pytest.approx((0.0, 5.0))


def test_an_arc_that_ends_where_it_started_is_a_full_circle():
    """Not a zero-length move - this is how a round wall is emitted."""
    x_range, y_range = _extent("G1 X0 Y0 Z0.2\nG3 X0 Y0 I5 J0 E1")
    assert x_range == pytest.approx((0.0, 10.0))
    assert y_range == pytest.approx((-5.0, 5.0))


def test_an_arc_without_a_centre_falls_back_to_its_chord():
    """``R`` arcs are not emitted by the slicers this reads; do not guess."""
    x_range, y_range = _extent("G1 X0 Y0 Z0.2\nG3 X10 Y0 R5 E1")
    assert (x_range, y_range) == (pytest.approx((0.0, 10.0)), pytest.approx((0.0, 0.0)))


def test_homing_and_retraction_are_not_moves():
    """``G28``/``G10`` start with a move's letter and number, but are neither."""
    assert list(iter_extrusion_segments("G28 X0 Y0\nG10\nG11")) == []


def test_halves_round_up():
    assert to_fixed(18.615, 2) == "18.62"
    assert to_fixed(1.0, 1) == "1.0"

"""Bambu Lab A1."""

from __future__ import annotations

from .base import BedBounds
from .bedslinger import BedSlingerProfile


class A1Profile(BedSlingerProfile):
    key = "a1"
    name = "A1"
    model_ids = ("N2S",)
    bed_bounds = BedBounds(min_x=-48, max_x=256, min_y=0, max_y=262)
    m190_repeat = 45

    #: Same push geometry as the A1 Mini - see ``a1_mini.PUSH_HEIGHT_FACTOR``.
    push_height_factor = 0.7
    push_min_model_height = 6.0
    push_min_z = 0.2
    #: Same toolhead shape as the A1 Mini - see ``a1_mini.BLADE_WIDTH``.
    blade_width = 55.0
    blade_overlap = 0.5

    y_forward = 262
    wiggle_x_left = -48
    wiggle_x_right = 256
    wiggle_y_positions = (210, 165, 120, 75, 30, 0)
    wiggle_final_line = "G1 Y262 F2000\t;push bed forward one last time\n"

    start_template_name = "start_a1.gcode"
    end_head_template_name = "end_a1_head.gcode"
    end_tail_template_name = "end_a1_tail.gcode"

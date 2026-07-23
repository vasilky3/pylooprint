"""Bambu Lab A1 Mini."""

from __future__ import annotations

from .base import BedBounds
from .bedslinger import BedSlingerProfile


class A1MiniProfile(BedSlingerProfile):
    key = "a1mini"
    name = "A1 Mini"
    model_ids = ("N1",)
    bed_bounds = BedBounds(min_x=-13, max_x=180, min_y=0, max_y=185)
    m190_repeat = 50

    y_forward = 180
    wiggle_x_left = -13
    wiggle_x_right = 180
    wiggle_y_positions = (135, 90, 45, 0)
    wiggle_final_line = "G1 Y185 F2000 ;move bed forward one last time\n"

    start_template_name = "start_a1_mini.gcode"
    end_head_template_name = "end_a1_mini_head.gcode"
    end_tail_template_name = "end_a1_mini_tail.gcode"

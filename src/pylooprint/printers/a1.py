"""Bambu Lab A1."""

from __future__ import annotations

from .base import BedBounds, EndCodeContext, load_template
from .bedslinger import BedSlingerProfile


class A1Profile(BedSlingerProfile):
    key = "a1"
    name = "A1"
    model_ids = ("N2S",)
    bed_bounds = BedBounds(min_x=-48, max_x=256, min_y=0, max_y=262)
    m190_repeat = 45

    y_forward = 262
    wiggle_x_left = -48
    wiggle_x_right = 256
    wiggle_y_positions = (210, 165, 120, 75, 30, 0)
    wiggle_final_line = "G1 Y262 F2000\t;push bed forward one last time\n"

    start_template_name = "start_a1.gcode"
    end_head_template_name = "end_a1_head.gcode"
    end_tail_template_name = "end_a1_tail.gcode"

    def extra_release_sequence(self, context: EndCodeContext) -> str:
        """Optional negative-Z release; only safe without a Z-axis stiffener mod."""
        if not context.settings.negative_z_enabled:
            return ""
        return "\n\n" + load_template("a1_negative_z.gcode")

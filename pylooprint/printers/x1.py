"""Bambu Lab X1 / X1C.

Same push kinematics as the P1, but the end code is assembled from the X1
template blocks rather than spliced into a stock template: the X1 has a filament
cutter and an auxiliary fan that have to be sequenced before the cool-down.
"""

from __future__ import annotations

from .base import BedBounds, EndCodeContext, load_template
from .corexy import PUSH_LANE_OFFSET, CoreXyProfile


class X1Profile(CoreXyProfile):
    key = "x1"
    name = "X1/X1C"
    model_ids = ("BL-P001", "BL-P002", "C12")
    bed_bounds = BedBounds(min_x=10, max_x=246, min_y=0, max_y=256)
    m190_repeat = 30

    start_template_name = "start_x1.gcode"

    def end_code(self, context: EndCodeContext) -> str:
        temp = context.settings.cooldown_temp
        lanes = self.push_lanes(context)

        code = load_template("end_x1_cutter.gcode")
        code += load_template("end_x1_timelapse.gcode")
        code += load_template("end_x1_motors.gcode")
        code += load_template("end_x1_cooldown.gcode")
        code += self.cooldown_block(temp) + "\n"
        code += load_template("end_x1_fans_off.gcode")
        code += self.release_beep() + "\n"
        code += load_template("end_x1_zoffset.gcode")
        code += self.push_gcode(lanes)

        code += "\n" + load_template("sound_x1.gcode")
        code += "\nM400\nM18 X Y Z ; Disable all motors"

        header = (
            f";===== X1 PRESET (Offset: {PUSH_LANE_OFFSET}mm, Temp: {temp}°C "
            f"actual: {self.apply_temp_offset(temp)}°C, DYNAMIC MULTI-LANE PUSH: "
            f"Center={lanes.centre_x}, Left={lanes.left_x}, Right={lanes.right_x}) ====="
        )
        return f"{header}\n{code}"

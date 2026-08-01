"""Bambu Lab P1 / P1S."""

from __future__ import annotations

import re

from .base import BedBounds, EndCodeContext, load_template
from .corexy import PUSH_LANE_OFFSET, CoreXyProfile

#: Where the stock Factorian push block starts and ends in the raw template.
_PUSH_BLOCK_START = "G1 X170 Y254 F600\t\t; move nozzle a little to the side for safety"
_SAFETY_CLEAR_START = ";====Push off complete, start safety clear ===="
_SAFETY_CLEAR_END = ";==== safety clear complete ===="
_MOTOR_DISABLE = "M17 X0.8 Y0.8 Z0.5 ; lower motor current to 45% power"
_TARGET_TEMP_RE = re.compile(r"(here the target temp is )[^)]*( °C)")


class P1Profile(CoreXyProfile):
    key = "p1"
    name = "P1/P1S"
    model_ids = ("C11",)
    bed_bounds = BedBounds(min_x=10, max_x=246, min_y=0, max_y=256)
    m190_repeat = 30

    start_template_name = "start_p1.gcode"

    def end_code(self, context: EndCodeContext) -> str:
        temp = context.settings.cooldown_temp
        lanes = self.push_lanes(context)

        code = load_template("end_p1_raw.gcode")
        code = code.replace("M190 S18", f"M190 S{temp}")
        code = _TARGET_TEMP_RE.sub(f"here the target temp is {temp + 5} °C", code, count=1)
        code = self._splice_push_block(code, self.push_gcode(lanes))
        code = self._insert_end_sound(code)
        header = (
            f";===== {context.direction.upper()} PRESET (Offset: {PUSH_LANE_OFFSET}mm, "
            f"Temp: {temp}C, DYNAMIC MULTI-LANE PUSH: Center={lanes.centre_x}, "
            f"Left={lanes.left_x}, Right={lanes.right_x}) ====="
        )
        return f"{header}\n{code}"

    def _splice_push_block(self, code: str, push: str) -> str:
        """Swap the template's fixed push block for the multi-lane version."""
        start = code.find(_PUSH_BLOCK_START)
        safety_start = code.find(_SAFETY_CLEAR_START)
        if start == -1 or safety_start == -1:
            return code
        safety_end = code.find(_SAFETY_CLEAR_END)
        if safety_end != -1:
            tail = code[safety_end + len(_SAFETY_CLEAR_END) :]
        else:
            tail = code[safety_start + len(_SAFETY_CLEAR_START) :]
        return code[:start] + push + tail

    def _insert_end_sound(self, code: str) -> str:
        sound = load_template("sound_p1.gcode")
        index = code.rfind(_MOTOR_DISABLE)
        if index == -1:
            return code + "\n" + sound
        return code[:index] + sound + code[index + len(_MOTOR_DISABLE) :]

"""Shared engine for the bed-slinger machines (A1 and A1 Mini).

Kinematics: the bed carries the part along Y while the toolhead stays put, so
the part is pushed off by driving the bed forward under a lowered nozzle, then
"wiggled" across X at bed level to sweep the part clear.

Nothing here may be reused by the CoreXY profiles - mixing the two push
directions would drive the gantry into the print.
"""

from __future__ import annotations

from ..settings import LoopSettings
from .base import EndCodeContext, PrinterProfile, load_template

#: Fixed X feedrate of the wiggle sweep.
WIGGLE_SPEED = 2000

#: Feedrate of the "move the nozzle over the model centre" travel that precedes
#: the push. The template end codes travel at rapid speed; the in-place strategy
#: crawls instead, so the toolhead cannot knock a tall part over on the way.
ALIGN_FEED_RAPID = 12000
ALIGN_FEED_SLOW = 300

#: Markers bracketing the block, so it can be located in a finished file.
HOLD_START = ";======= LOOPRINT RELEASE HOLD ======="
HOLD_END = ";======= END LOOPRINT RELEASE HOLD ======="


class BedSlingerProfile(PrinterProfile):
    """Common behaviour of the Y-axis push-off printers."""

    temp_offset = -4

    #: Y the bed returns to after the push.
    y_forward: float
    #: X travel limits of the wiggle sweep.
    wiggle_x_left: float
    wiggle_x_right: float
    #: Bed positions the sweep is repeated at.
    wiggle_y_positions: tuple[int, ...]
    #: Final "park the bed" line - the two machines word it differently.
    wiggle_final_line: str
    #: Push geometry: the fraction of the model height the nozzle drops to, and
    #: the fixed Z it uses instead for a model shorter than the threshold.
    push_height_factor: float
    push_min_model_height: float
    push_min_z: float

    def apply_temp_offset(self, temp: int) -> int:
        """The bed sensor reads ~4 degrees high, and 15 C is the floor."""
        return max(15, temp + self.temp_offset)

    def push_gcode(self, align_feed: int = ALIGN_FEED_RAPID) -> str:
        """Align the nozzle with the model centre, drop Z, drive the bed forward."""
        template = load_template("a1_push.gcode")
        return (
            template.replace("@Y_FORWARD@", _format_number(self.y_forward))
            .replace("@ALIGN_FEED@", str(align_feed))
            .replace("@PUSH_FACTOR@", _format_number(self.push_height_factor))
            .replace("@PUSH_MIN_HEIGHT@", _format_number(self.push_min_model_height))
            .replace("@PUSH_MIN_Z@", _format_number(self.push_min_z))
        )

    def wiggle_sweep(self) -> str:
        """Sweep the released part off the plate at bed level."""
        lines = []
        for y in self.wiggle_y_positions:
            lines.append(
                f"G1 Y{y} F2000\t;move bed back a little\n"
                f"G1 X{_format_number(self.wiggle_x_right)} F800\t;move to the right\n"
                f"G1 X{_format_number(self.wiggle_x_left)}\tF{_format_number(WIGGLE_SPEED)}\t;move back to the left\n"
            )
        lines.append(self.wiggle_final_line)
        return "".join(lines)

    def release_hold(self, settings: LoopSettings) -> str:
        """Wait at the park height, then beep once, before the push-off.

        Runs between the cool-down wait and the push-off.  Nothing in it moves
        the machine: the toolhead has to stay at the park height, because on a
        printer with the limit-switch fan mod that is what keeps the fan running
        for the whole hold, and the bed has to stay where the eject keep-out
        zone was measured for.

        The beep is unconditional; ``hold_seconds`` only controls the wait in
        front of it.
        """
        lines = [
            HOLD_START,
            "; Hold at the park height while the part keeps cooling, then sound the",
            "; push-off warning.  Nothing here moves the bed or the toolhead.",
            "M400 ; wait for all motion to complete",
        ]
        if settings.hold_seconds > 0:
            lines.append(f"G4 S{settings.hold_seconds} ; hold before the push-off")

        lines += ["", self.release_beep(), HOLD_END]
        return "\n".join(lines)

    def end_code(self, context: EndCodeContext) -> str:
        temp = context.settings.cooldown_temp
        body = (
            load_template(self.end_head_template_name)
            .replace("@M190@", self.cooldown_block(temp))
            .replace("@HOLD@", self.release_hold(context.settings))
            .replace("@PUSH@", self.push_gcode())
        )
        body += "\n" + self.wiggle_sweep()
        body += load_template(self.end_tail_template_name)
        return f"{self.preset_header(temp)}\n{body}"

    def preset_header(self, temp: int) -> str:
        actual = self.apply_temp_offset(temp)
        return f";===== {self.name} PRESET (Temp: {temp}°C actual: {actual}°C, Y-axis push-off) ====="

    # End-code template file names, supplied by the concrete profiles.
    end_head_template_name: str
    end_tail_template_name: str


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)

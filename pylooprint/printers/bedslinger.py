"""Shared engine for the bed-slinger machines (A1 and A1 Mini).

Kinematics: the bed carries the part along Y while the toolhead stays put, so
the part is pushed off by driving the bed forward under a lowered nozzle, then
"wiggled" across X at bed level to sweep the part clear.

Nothing here may be reused by the CoreXY profiles - mixing the two push
directions would drive the gantry into the print.
"""

from __future__ import annotations

from typing import Sequence

from ..core.jsnum import to_fixed
from ..core.parts import PartBounds
from ..core.push_plan import PushLine, plan_push_lines
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

#: The same, for the run of push lines.
PUSH_PLAN_START = ";======= LOOPRINT PUSH PLAN ======="
PUSH_PLAN_END = ";======= END LOOPRINT PUSH PLAN ======="

#: And for the park that closes the job, after the last copy is off the plate.
PARK_START = ";======= LOOPRINT FINAL PARK ======="
PARK_END = ";======= END LOOPRINT FINAL PARK ======="


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

    def push_plan(self, parts: Sequence[PartBounds]) -> list[PushLine]:
        """One line per part, or per group of parts sharing an X band."""
        return plan_push_lines(
            parts,
            blade_width=self.blade_width,
            overlap=self.blade_overlap,
            height_factor=self.push_height_factor,
            min_model_height=self.push_min_model_height,
            min_z=self.push_min_z,
        )

    def push_gcode(
        self, context: EndCodeContext | None = None, align_feed: int = ALIGN_FEED_RAPID
    ) -> str:
        """Run the blade down every push line, left to right.

        Falls back to the single line through the plate centre when the parts
        are unknown - a body with nothing measurable in it still has to be
        ejected, and the slicer's own centre is the best guess left.
        """
        lines = self.push_plan(context.parts) if context is not None else []
        if not lines:
            return self._single_push_gcode(align_feed)

        blocks = [self._push_plan_header(lines)]
        blocks += [
            self._push_line_gcode(line, index, len(lines), align_feed)
            for index, line in enumerate(lines, start=1)
        ]
        blocks.append(
            "G1 Z1 F600\t\t;move nozzle closer to the bed for the sweep\n"
            f"{PUSH_PLAN_END}\n"
        )
        return "\n".join(blocks)

    def _push_plan_header(self, lines: Sequence[PushLine]) -> str:
        """What the plan is, spelled out where the operator will read it."""
        reach = self.blade_width * self.blade_overlap
        header = [
            PUSH_PLAN_START,
            f"; {len(lines)} line(s), left to right.  Blade {_format_number(self.blade_width)} mm"
            f" x {_format_number(self.blade_overlap)} overlap = {to_fixed(reach, 2)} mm reach:"
            " a part is pushed by the line nearest its centre, within that.",
        ]
        for index, line in enumerate(lines, start=1):
            header.append(
                f"; line {index}: X {to_fixed(line.x, 2)}  Z {to_fixed(line.z, 2)}"
                f"  {_part_list(line)}"
            )
        header.append("M220 S100 ; Reset to standard speed for safe push-off")
        return "\n".join(header) + "\n"

    def _push_line_gcode(
        self, line: PushLine, index: int, total: int, align_feed: int
    ) -> str:
        return (
            load_template("a1_push_line.gcode")
            .replace("@INDEX@", str(index))
            .replace("@TOTAL@", str(total))
            .replace("@PART_LIST@", _part_list(line))
            .replace("@SAFE_Z@", to_fixed(line.safe_z, 2))
            .replace("@X@", to_fixed(line.x, 2))
            .replace("@Z@", to_fixed(line.z, 2))
            .replace("@ALIGN_FEED@", str(align_feed))
            .replace("@PUSH_FACTOR@", _format_number(self.push_height_factor))
            .replace("@Y_FORWARD@", _format_number(self.y_forward))
        )

    def _single_push_gcode(self, align_feed: int) -> str:
        """The one-line push: plate centre, one height, one pass."""
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

    def final_park(self, context: EndCodeContext) -> str:
        """Put the head back where an ordinary print of this plate leaves it.

        The slicer's own lift comes first: the sweep ends a millimetre above the
        plate, and the park it copies finishes with a *relative* Z move, which
        from there would drive the nozzle into the plate instead of down to just
        under the lift height.

        Empty when the file carries no park to copy - better to leave the head
        where the sweep put it than to invent a position for a machine whose end
        code is shaped differently.
        """
        park = context.slicer_park
        if park is None or not park.moves:
            return ""

        lines = [PARK_START, "; Back to where an ordinary print leaves the head."]
        if park.lift:
            lines += ["G90", park.lift]
        lines += [park.moves, PARK_END]
        return "\n".join(lines) + "\n"

    def final_end_code(self, context: EndCodeContext) -> str | None:
        """The last loop parks the head; the ones before it just carry on."""
        park = self.final_park(context)
        return self.end_code(context, park=park) if park else None

    def end_code(self, context: EndCodeContext, park: str = "") -> str:
        temp = context.settings.cooldown_temp
        body = (
            load_template(self.end_head_template_name)
            .replace("@M190@", self.cooldown_block(temp))
            .replace("@HOLD@", self.release_hold(context.settings))
            .replace("@PUSH@", self.push_gcode(context))
        )
        body += "\n" + self.wiggle_sweep()
        # Before the tail: that is where the slicer's resets, its finish sound
        # and the M18 that drops the motors live, and the park has to happen
        # while the motors are still holding.
        body += park
        body += load_template(self.end_tail_template_name)
        return f"{self.preset_header(temp)}\n{body}"

    def preset_header(self, temp: int) -> str:
        actual = self.apply_temp_offset(temp)
        return f";===== {self.name} PRESET (Temp: {temp}°C actual: {actual}°C, Y-axis push-off) ====="

    # End-code template file names, supplied by the concrete profiles.
    end_head_template_name: str
    end_tail_template_name: str


def _part_list(line: PushLine) -> str:
    """``part 3`` / ``parts 1, 2`` - the numbers the parts report uses."""
    label = "part" if len(line.parts) == 1 else "parts"
    return f"{label} {', '.join(str(number) for number in line.parts)}"


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)

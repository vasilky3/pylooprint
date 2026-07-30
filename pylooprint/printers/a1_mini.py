"""Bambu Lab A1 Mini."""

from __future__ import annotations

from typing import Mapping, Sequence

from ..core.patching import LineRangePatch, apply_patches, replace_between
from ..core.placement import ExtrusionBounds
from ..core.structure import GcodeStructure
from ..core.template import apply_speed_mode
from ..errors import UnsafeEjectZoneError
from .base import BedBounds, EndCodeContext, MachineCode, load_template
from .bedslinger import ALIGN_FEED_SLOW, BedSlingerProfile

#: Unique lines in the slicer's own end code that bracket the part it replaces.
#: Everything the slicer does before this (timelapse, filament unload, hotend
#: off) is kept; everything after it is the reset/finish-sound tail.
_END_SPLICE_AFTER = "M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom"
_END_SPLICE_BEFORE = "M220 S100  ; Reset feedrate magnitude"

#: Height the toolhead parks at while the bed cools.  Deliberately above the
#: 180 mm printable height: the gantry is driven up against the mechanical
#: switch at the top, which gives a repeatable reference to cool down from.
#: Do not "correct" this to 180.
PARK_Z = 184.5

#: Plate area the toolhead body covers while it parks at X-13 / Y180 and then
#: descends to Z1 for the push-off.  The nozzle itself clears the plate at
#: X-13, but the body overhangs the back-left corner by 15 mm in X and 30 mm in
#: Y, so anything printed inside this rectangle is struck on the way down.
EJECT_KEEPOUT_MIN_X = 0.0
EJECT_KEEPOUT_MAX_X = 15.0
EJECT_KEEPOUT_MIN_Y = 150.0
EJECT_KEEPOUT_MAX_Y = 180.0

_CANNOT_EJECT = "Model cannot be ejected. The safe head-descent zone is occupied."
_KEEPOUT_DESCRIPTION = (
    f"The toolhead descends onto the plate at the back-left corner "
    f"(X {EJECT_KEEPOUT_MIN_X:.1f}-{EJECT_KEEPOUT_MAX_X:.1f}, "
    f"Y {EJECT_KEEPOUT_MIN_Y:.1f}-{EJECT_KEEPOUT_MAX_Y:.1f} mm)"
)


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

    def check_eject_clearance(self, bounds: ExtrusionBounds | None) -> None:
        """Refuse the build if the model sits where the toolhead comes down.

        The push-off parks the nozzle off the plate at X-13 / Y180 and then
        drops to Z1.  The nozzle clears the plate, but the toolhead body
        overhangs the back-left corner, so a model printed there is hit on the
        way down - which damages both the print and the printer.
        """
        if bounds is None:
            raise UnsafeEjectZoneError(
                "Model cannot be ejected. The safe head-descent zone could not be "
                "verified - no extruding moves were found to measure. "
                f"{_KEEPOUT_DESCRIPTION}; check the model is clear of it."
            )

        if bounds.overlaps(
            EJECT_KEEPOUT_MIN_X, EJECT_KEEPOUT_MAX_X, EJECT_KEEPOUT_MIN_Y, EJECT_KEEPOUT_MAX_Y
        ):
            raise UnsafeEjectZoneError(
                f"{_CANNOT_EJECT} {_KEEPOUT_DESCRIPTION}; the model occupies "
                f"X {bounds.min_x:.2f}-{bounds.max_x:.2f}, "
                f"Y {bounds.min_y:.2f}-{bounds.max_y:.2f} mm. "
                "Move the model clear of that corner and re-slice."
            )

    def build_machine_code(
        self,
        structure: GcodeStructure,
        context: EndCodeContext,
        values: Mapping[str, object],
    ) -> MachineCode:
        """Keep the slicer's machine G-code and patch only what looping breaks.

        Everything the printer profile configured - flow calibration, bed
        levelling, build-plate detection, timelapse - survives, so only the
        purge lines and the tail of the end code are rewritten.
        """
        start_code = apply_patches(structure.slicer_start_code, self.start_code_patches())
        return MachineCode(
            start_code=apply_speed_mode(start_code),
            end_code=self.patch_slicer_end_code(structure.slicer_end_code, context),
        )

    def start_code_patches(self) -> Sequence[LineRangePatch]:
        """Purge into the air instead of drawing a line on the plate.

        The slicer draws its extrusion-calibration line across the front of the
        bed.  On the second and later loops that area is where the previous part
        was ejected from, and a drawn line would also be printed on top of the
        plate the next part has to stick to, so both calibration draws become an
        in-air purge.
        """
        return (
            LineRangePatch(
                name="extrusion calibration purge",
                # inside "M622 J1" / extrude_cali_flag:
                #   G0 X68 Y-4 F30000 ... G0 Y0 Z0 F20000 / M400 / <blank>
                after=r"^M900 K[\d.]+ L[\d.]+ M[\d.]+$",
                first=r"^G0 X\d+(?:\.\d+)? Y-?[\d.]+ F30000$",
                last=r"^G0 Y0 Z0 F20000$",
                extra_lines=2,
                replacement=("G0 E50 F100", "M400", "G0 X80  F20000"),
            ),
            LineRangePatch(
                name="extrusion calibration test purge",
                # inside ";===== extrude cali test":
                #   G0 X68 Y-2.5 F30000 ... G0 X115 Z0 F20000 / G0 Z5
                after=r"^;===== extrude cali test",
                first=r"^G0 X\d+(?:\.\d+)? Y-?[\d.]+ F30000$",
                last=r"^G0 Z5$",
                replacement=("G0 E50 F100",),
            ),
        )

    def patch_slicer_end_code(self, end_code: str, context: EndCodeContext) -> str:
        """Cool down, push the part off and sweep, inside the slicer's end code.

        The slicer's own Z-lift is carried over (de-indented, since the ``{if}``
        block it came from is gone) and the eject sequence takes the place of
        the moves that would otherwise just park the head and finish.
        """
        head = (
            load_template("end_a1_mini_inplace_head.gcode")
            .replace("@PARK_Z@", str(PARK_Z))
            .replace("@M190@", self.cooldown_block(context.settings.cooldown_temp))
        )
        push = self.push_gcode(align_feed=ALIGN_FEED_SLOW)
        sweep = self.wiggle_sweep()

        def build(replaced: str) -> str:
            lift = "\n".join(move.strip() for move in _lift_moves(replaced))
            return (
                f"\n\n{lift}\n\n{head}{push}\n{sweep}"
                ";====== Safety clear complete =======\nM17 R ; restore z current\n"
            )

        return replace_between(end_code, _END_SPLICE_AFTER, _END_SPLICE_BEFORE, build)


def _lift_moves(replaced: str) -> list[str]:
    """The ``G1 Z...`` moves the slicer emitted to lift clear of the print."""
    moves = []
    for line in replaced.split("\n"):
        stripped = line.strip()
        if stripped.startswith("G1 Z"):
            moves.append(line)
        elif moves and stripped:
            break
    return moves
